#!/usr/bin/env python3
"""Geometry-based correction of person-association (re-ID) swaps for Pose2Sim.

Given a Pose2Sim project with a GOOD calibration and an existing (mostly-correct)
person association, this fixes the residual identity swaps — frames where the
wrong person was labelled as subject S in a given camera. It does NOT re-associate
from scratch; it trusts the majority of cameras and re-matches each camera's
detections to subjects by reprojection consistency.

Per frame:
  1. Robustly triangulate each subject's 3D from its currently-assigned detections
     (per-joint DLT with iterative reprojection-outlier rejection — swapped cameras
     are the outliers and get dropped, so the 3D stays anchored on the good ones).
  2. For each camera, build a cost matrix (mean reprojection error of each detected
     person vs each subject's 3D) and solve the optimal assignment (Hungarian),
     gated by --reproj_gate so a bad match leaves the subject unseen (zeros) rather
     than forcing a wrong identity.
  3. Optionally iterate (re-triangulate from the corrected assignment).

Outputs corrected per-camera JSONs (same Pose2Sim format, slot s = subject s) and
prints a per-subject reprojection BEFORE vs AFTER report.

Usage:
    python scripts/fix_person_association.py \\
        --project "/mnt/c/Users/fdela/Documents/These Flo/Stage M2/pose2sim_project" \\
        --pose_dir pose-associated --out_dir pose-associated-fixed
"""
import argparse, ast, glob, json, os, re, sys
import numpy as np
import cv2
from scipy.optimize import linear_sum_assignment

N_KPT = 26


def parse_args():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--project", required=True, help="Pose2Sim project directory.")
    p.add_argument("--calib", default=None, help="Calib toml (default <project>/calibration/Calib.toml).")
    p.add_argument("--pose_dir", default="pose-associated", help="Input pose dir (relative to project).")
    p.add_argument("--out_dir", default="pose-associated-fixed", help="Output pose dir (relative to project).")
    p.add_argument("--conf_threshold", type=float, default=0.3, help="Min keypoint confidence to use.")
    p.add_argument("--reproj_gate", type=float, default=40.0,
                   help="Max reproj error (px) to (a) keep a camera in triangulation and "
                        "(b) accept a detection<->subject match.")
    p.add_argument("--min_cams", type=int, default=3, help="Min cameras to triangulate a joint.")
    p.add_argument("--iterations", type=int, default=2, help="Triangulate/re-match passes per frame.")
    p.add_argument("--step", type=int, default=1, help="Process every Nth frame (1=all; >1 for a quick test).")
    p.add_argument("--dry_run", action="store_true", help="Report before/after only, write nothing.")
    return p.parse_args()


def load_calib(path):
    txt = open(path).read()
    cams = []
    for s in re.split(r'\n\[', txt):
        if 'matrix' not in s:
            continue
        name = s.split(']')[0].strip('[').strip()
        if name in ('metadata',):
            continue
        g = lambda k: ast.literal_eval(re.search(k + r'\s*=\s*(\[.*?\])\s*\n', s, re.S).group(1))
        K = np.array(g('matrix'), float)
        rot = np.array(g('rotation'), float)
        tr = np.array(g('translation'), float)
        P = K @ np.hstack([cv2.Rodrigues(rot)[0], tr.reshape(3, 1)])
        cams.append({'name': name, 'serial': name.split('_')[0], 'P': P})
    return cams


def triangulate(Ps, pts, ws):
    A = []
    for P, (x, y), w in zip(Ps, pts, ws):
        A.append(w * (x * P[2] - P[0]))
        A.append(w * (y * P[2] - P[1]))
    _, _, Vt = np.linalg.svd(np.array(A))
    X = Vt[-1]
    return X / X[3]


def reproj(P, X):
    p = P @ X
    return p[:2] / p[2]


def triangulate_subject(kps_by_cam, Ps, conf_thr, gate, min_cams):
    """kps_by_cam: dict cam_idx -> kp[26,3]. Returns X[26,4] (nan where unsolved)."""
    X = np.full((N_KPT, 4), np.nan)
    for j in range(N_KPT):
        obs = [(ci, kp[j, :2], kp[j, 2]) for ci, kp in kps_by_cam.items() if kp[j, 2] > conf_thr]
        if len(obs) < min_cams:
            continue
        cur = list(range(len(obs)))
        while True:
            Xj = triangulate([Ps[obs[c][0]] for c in cur],
                             [obs[c][1] for c in cur], [obs[c][2] for c in cur])
            errs = [np.linalg.norm(obs[c][1] - reproj(Ps[obs[c][0]], Xj)) for c in cur]
            w = int(np.argmax(errs))
            if errs[w] > gate and len(cur) > min_cams:
                cur.pop(w)
            else:
                break
        X[j] = Xj
    return X


def match_cost(det_kp, X_subj, P, conf_thr):
    """Mean reproj error between a detection and a subject 3D, over commonly-valid joints."""
    valid = (det_kp[:, 2] > conf_thr) & ~np.isnan(X_subj[:, 0])
    if valid.sum() < 4:
        return np.inf
    errs = [np.linalg.norm(det_kp[j, :2] - reproj(P, X_subj[j])) for j in range(N_KPT) if valid[j]]
    return float(np.mean(errs))


def main():
    args = parse_args()
    calib_path = args.calib or os.path.join(args.project, "calibration", "Calib.toml")
    cams = load_calib(calib_path)
    C = len(cams)
    Ps = [c['P'] for c in cams]

    base = os.path.join(args.project, args.pose_dir)
    posedirs = sorted([d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d))])
    if len(posedirs) != C:
        print(f"WARN: {len(posedirs)} pose dirs vs {C} calib cameras", file=sys.stderr)
    # map camera index -> pose dir by serial prefix
    cam_dir = []
    for c in cams:
        d = next((d for d in posedirs if d.startswith(c['serial'])), None)
        cam_dir.append(d)
    files = [sorted(glob.glob(os.path.join(base, d, "*.json"))) for d in cam_dir]
    nfr = min(len(f) for f in files)
    frames = list(range(0, nfr, args.step))
    NS = 0
    probe = frames[::max(1, len(frames) // 60)]  # spread probes across the whole sequence
    for fi in probe:
        for ci in range(C):
            NS = max(NS, len(json.load(open(files[ci][fi])).get('people', [])))
    print(f"Cameras: {C}  Frames: {nfr} (processing {len(frames)})  Subjects: {NS}")
    print(f"conf>{args.conf_threshold}, reproj_gate {args.reproj_gate}px, {args.iterations} passes\n")

    out_base = os.path.join(args.project, args.out_dir)
    if not args.dry_run:
        for d in cam_dir:
            os.makedirs(os.path.join(out_base, d), exist_ok=True)

    # before/after accounting
    err_before = {s: [] for s in range(NS)}
    err_after = {s: [] for s in range(NS)}
    n_changed = 0
    n_cells = 0

    def get_kp(people, s):
        if s < len(people):
            return np.array(people[s]['pose_keypoints_2d'], float).reshape(-1, 3)
        return np.zeros((N_KPT, 3))

    for fi in frames:
        raw = [json.load(open(files[ci][fi])) for ci in range(C)]
        people = [r.get('people', []) for r in raw]
        # all detections per camera (nonzero)
        dets = []  # per cam: list of (orig_slot, kp)
        for ci in range(C):
            lst = []
            for s in range(len(people[ci])):
                kp = get_kp(people[ci], s)
                if (kp[:, 2] > args.conf_threshold).sum() >= 4:
                    lst.append((s, kp))
            dets.append(lst)

        # initial subject 3D from current assignment
        assign = {ci: {s: get_kp(people[ci], s) for s in range(NS)
                       if (get_kp(people[ci], s)[:, 2] > args.conf_threshold).sum() >= 4}
                  for ci in range(C)}

        # BEFORE error
        for s in range(NS):
            kbc = {ci: assign[ci][s] for ci in range(C) if s in assign[ci]}
            if len(kbc) >= args.min_cams:
                Xs = triangulate_subject(kbc, Ps, args.conf_threshold, args.reproj_gate, args.min_cams)
                for ci, kp in kbc.items():
                    c = match_cost(kp, Xs, Ps[ci], args.conf_threshold)
                    if np.isfinite(c):
                        err_before[s].append(c)

        # iterative correction
        new_assign = {ci: dict(assign[ci]) for ci in range(C)}
        for _ in range(args.iterations):
            # triangulate each subject from current assignment
            X = {}
            for s in range(NS):
                kbc = {ci: new_assign[ci][s] for ci in range(C) if s in new_assign[ci]}
                if len(kbc) >= args.min_cams:
                    X[s] = triangulate_subject(kbc, Ps, args.conf_threshold, args.reproj_gate, args.min_cams)
            # re-match per camera
            for ci in range(C):
                if not dets[ci] or not X:
                    continue
                subj_ids = list(X.keys())
                cost = np.full((len(dets[ci]), len(subj_ids)), 1e6)
                for di, (_, kp) in enumerate(dets[ci]):
                    for sj, s in enumerate(subj_ids):
                        c = match_cost(kp, X[s], Ps[ci], args.conf_threshold)
                        cost[di, sj] = c if np.isfinite(c) else 1e6
                ri, cj = linear_sum_assignment(cost)
                am = {}
                for di, sj in zip(ri, cj):
                    if cost[di, sj] <= args.reproj_gate:
                        am[subj_ids[sj]] = dets[ci][di][1]
                new_assign[ci] = am

        # AFTER error + count changes + write
        for ci in range(C):
            # detect changes vs original slot mapping
            orig = {s: tuple(np.round(assign[ci][s][:, :2].ravel(), 1)) for s in assign[ci]}
            new = {s: tuple(np.round(new_assign[ci][s][:, :2].ravel(), 1)) for s in new_assign[ci]}
            for s in set(orig) | set(new):
                n_cells += 1
                if orig.get(s) != new.get(s):
                    n_changed += 1
        for s in range(NS):
            kbc = {ci: new_assign[ci][s] for ci in range(C) if s in new_assign[ci]}
            if len(kbc) >= args.min_cams:
                Xs = triangulate_subject(kbc, Ps, args.conf_threshold, args.reproj_gate, args.min_cams)
                for ci, kp in kbc.items():
                    c = match_cost(kp, Xs, Ps[ci], args.conf_threshold)
                    if np.isfinite(c):
                        err_after[s].append(c)

        if not args.dry_run:
            for ci in range(C):
                ppl = []
                for s in range(NS):
                    kp = new_assign[ci].get(s, np.zeros((N_KPT, 3)))
                    ppl.append({'pose_keypoints_2d': kp.ravel().tolist()})
                out = dict(raw[ci])
                out['people'] = ppl
                fn = os.path.basename(files[ci][fi])
                json.dump(out, open(os.path.join(out_base, cam_dir[ci], fn), 'w'))

    print("Per-subject reprojection (mean px)   BEFORE -> AFTER")
    for s in range(NS):
        b = np.mean(err_before[s]) if err_before[s] else float('nan')
        a = np.mean(err_after[s]) if err_after[s] else float('nan')
        flag = "  *FIXED*" if (err_before[s] and err_after[s] and b - a > 15) else ""
        print(f"  Subj {s}:  {b:7.1f} -> {a:7.1f}{flag}")
    allb = [e for v in err_before.values() for e in v]
    alla = [e for v in err_after.values() for e in v]
    print(f"\n  GLOBAL mean:  {np.mean(allb):.1f} -> {np.mean(alla):.1f} px   "
          f"median {np.median(allb):.1f} -> {np.median(alla):.1f} px")
    print(f"  Reassigned (subject,camera) cells: {n_changed}/{n_cells} ({100*n_changed/max(n_cells,1):.1f}%)")
    if not args.dry_run:
        print(f"\n  Corrected poses written to: {out_base}")


if __name__ == "__main__":
    main()
