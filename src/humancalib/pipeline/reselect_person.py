"""Geometric person re-selection: keep, in every camera, the person the others see.

Extraction keeps the largest detection per frame per camera. A bystander close
to one camera -- BioCV P06 and P10, camera 08 -- is then "the subject" in that
camera for the whole trial, and the calibration of that camera fails while the
others are fine. This step uses that: given a first calibration, it

1. triangulates the subject in each frame from the current selection, dropping
   cameras that disagree (camera-level outlier rejection, the rule of the
   outlier-frame step: error above max(abs_px, x_median x the others' median));
2. in every camera, re-selects the detection whose keypoints lie closest to the
   subject's reprojection, among the detections extraction would accept;
3. rewrites the pose files through the extractors' own post-processing.

The pipeline then calibrates again from the corrected poses (cli.py,
--person_selection geometric). Frames seen by fewer than min_cams cameras keep
their original selection. The dropped-frame sidecars written by the outlier
step are removed: they were computed on the wrong person and are recomputed.

Needs the candidates saved at extraction (pose/candidates.py).
"""
import argparse
import json
import os
import shutil
from itertools import combinations

import numpy as np

from humancalib.core import load_eldersim_camera
from humancalib.core.log import get_logger, setup_logging
from humancalib.core.sidecars import SIDECAR_DIRNAME
from humancalib.pose import candidates as cand

log = get_logger(__name__)

MIN_JOINTS = 4
IMAGE_MARGIN = 10          # px, as the MeTRAbs extractor's out-of-image penalty


# --- geometry ------------------------------------------------------------------------------------

def dlt_batch(pts, weights, Ps):
    """Homogeneous DLT for J points at once. pts (C, J, 2), weights (C, J), Ps (C, 3, 4).

    Returns (J, 3), NaN where fewer than two views have weight or the point is at infinity."""
    pts = np.nan_to_num(np.asarray(pts, float))
    w = np.asarray(weights, float)
    Ps = np.asarray(Ps, float)
    C, J = w.shape
    A = np.empty((J, 2 * C, 4))
    wT = w.T[:, :, None]                                      # (J, C, 1)
    A[:, 0::2] = (pts[:, :, 0].T[:, :, None] * Ps[None, :, 2] - Ps[None, :, 0]) * wT
    A[:, 1::2] = (pts[:, :, 1].T[:, :, None] * Ps[None, :, 2] - Ps[None, :, 1]) * wT
    Xh = np.linalg.svd(A)[2][:, -1]
    ok = ((w > 0).sum(axis=0) >= 2) & (np.abs(Xh[:, 3]) > 1e-10)
    X = np.full((J, 3), np.nan)
    X[ok] = Xh[ok, :3] / Xh[ok, 3:4]
    return X


def project(P, X):
    Xh = np.hstack([X, np.ones((len(X), 1))]) @ np.asarray(P, float).T
    return Xh[:, :2] / Xh[:, 2:3]


def mean_reprojection(pts, valid, X, P):
    """(n,) mean pixel distance between n detections (n, J, 2) and the projection of X (J, 3),
    over joints valid in the detection and solved in X; inf with fewer than MIN_JOINTS."""
    with np.errstate(invalid="ignore"):
        err = np.linalg.norm(np.asarray(pts, float) - project(P, X)[None], axis=2)
    ok = np.asarray(valid, bool) & np.isfinite(err)
    count = ok.sum(axis=1)
    total = np.where(ok, err, 0.0).sum(axis=1)
    return np.where(count >= MIN_JOINTS, total / np.maximum(count, 1), np.inf)


def robust_triangulate(pts, valid, Ps, abs_px, x_median, min_cams):
    """Triangulate one skeleton from the cameras that agree with each other.

    Dropping the worst camera from an all-camera solution fails with few cameras:
    one camera on the wrong person drags the whole solution, and every camera
    then looks wrong. Instead every subset of min_cams cameras is triangulated,
    the subset whose own reprojection error is smallest is kept (least median of
    squares), and every camera within max(abs_px, x_median x that error) of it
    joins the final solution. Returns (X (J, 3), cameras used (C,) bool)."""
    pts = np.asarray(pts, float)
    valid = np.asarray(valid, bool)
    Ps = np.asarray(Ps, float)
    C, J = valid.shape
    usable = np.flatnonzero(valid.sum(axis=1) >= MIN_JOINTS)
    if len(usable) < min_cams:
        return np.full((J, 3), np.nan), np.zeros(C, dtype=bool)

    combos = np.array(list(combinations(usable, min_cams)))            # (T, k)
    T = len(combos)
    X = np.stack([dlt_batch(pts[cb], valid[cb], Ps[cb]) for cb in combos])   # (T, J, 3)
    Xh = np.concatenate([X, np.ones((T, J, 1))], axis=2)
    proj = np.einsum("cab,tjb->tcja", Ps, Xh)                          # (T, C, J, 3)
    with np.errstate(invalid="ignore", divide="ignore"):
        err = np.linalg.norm(pts[None] - proj[..., :2] / proj[..., 2:3], axis=3)
    ok = valid[None] & np.isfinite(err)
    count = ok.sum(axis=2)
    cam_err = np.where(count >= MIN_JOINTS, np.where(ok, err, 0).sum(axis=2) / np.maximum(count, 1), np.inf)
    own = np.array([np.median(cam_err[t, combos[t]]) for t in range(T)])
    if not np.isfinite(own).any():
        return np.full((J, 3), np.nan), np.zeros(C, dtype=bool)
    best = int(np.argmin(own))
    use = np.zeros(C, dtype=bool)
    use[usable] = cam_err[best, usable] <= max(abs_px, x_median * own[best])
    use[combos[best]] = True
    return dlt_batch(pts, valid & use[:, None], Ps), use


def select_by_geometry(cameras, Ps, current, abs_px=50.0, x_median=5.0, min_cams=3, iterations=2):
    """New selection (C, F) from per-camera candidates on common frames, and the
    reprojection cost (C, F) of each kept detection (NaN where not evaluated).

    cameras[c][f] = (pts (n, J, 2), valid (n, J), acceptable (n,)); current (C, F) holds the
    index extraction kept, -1 for none."""
    new = np.array(current, dtype=int, copy=True)
    C, F = new.shape
    kept_cost = np.full((C, F), np.nan)
    J = next(p.shape[1] for cam in cameras for p, _, _ in cam if len(p))
    for f in range(F):
        for _ in range(iterations):
            pts = np.zeros((C, J, 2))
            valid = np.zeros((C, J), dtype=bool)
            for c in range(C):
                k = new[c, f]
                if k >= 0:
                    pts[c], valid[c] = cameras[c][f][0][k], cameras[c][f][1][k]
            if ((valid.sum(axis=1) >= MIN_JOINTS).sum()) < min_cams:
                break
            X, use = robust_triangulate(pts, valid, Ps, abs_px, x_median, min_cams)
            if use.sum() < min_cams or not np.isfinite(X).any():
                break
            changed = False
            for c in range(C):
                p, v, acceptable = cameras[c][f]
                if len(p) == 0:
                    continue
                cost = mean_reprojection(p, v, X, Ps[c])
                cost[~np.asarray(acceptable, bool)] = np.inf
                if np.isfinite(cost).any():
                    k = int(np.argmin(cost))
                    kept_cost[c, f] = cost[k]
                    if k != new[c, f]:
                        new[c, f] = k
                        changed = True
            if not changed:
                break
    return new, kept_cost


def drop_unmatched(selection, kept_cost, abs_px=50.0, x_median=5.0):
    """No person where even the best detection is far from the subject.

    When the subject is not detected in a camera -- out of view, occluded -- the
    closest detection is still someone else: the operator at the back of BioCV
    camera 05. Such a frame is marked as having no person when its cost exceeds
    max(abs_px, x_median x that camera's median cost), the outlier-frame rule,
    here measured against the consensus subject rather than the camera's own
    possibly wrong calibration."""
    new = np.array(selection, dtype=int, copy=True)
    for c in range(new.shape[0]):
        rated = np.isfinite(kept_cost[c]) & (new[c] >= 0)
        if not rated.any():
            continue
        limit = max(abs_px, x_median * float(np.median(kept_cost[c][rated])))
        new[c][rated & (kept_cost[c] > limit)] = -1
    return new


# --- files ---------------------------------------------------------------------------------------

def matching_points(engine, c, row, K, dist, conf_threshold):
    """(pts (n, 26, 2), valid (n, 26)) of one frame's detections, in the pixel space the
    calibration uses, on the Halpe26 joints both engines share."""
    s, e = c["start"][row], c["start"][row + 1]
    if e == s:
        return np.zeros((0, 26, 2)), np.zeros((0, 26), dtype=bool)
    h, w = c["imshape"]
    if engine == "metrabs":
        from humancalib.pose.metrabs_outputs import bml87_to_halpe26, undistort_points
        pts, valid = [], []
        for i in range(s, e):
            p2d = c["pose2d"][i]
            if np.any(dist != 0):
                p2d = undistort_points(p2d, K, dist)
            halpe = bml87_to_halpe26(p2d)
            score = np.full(26, float(c["box"][i][4]))
            oob = ((halpe[:, 0] < IMAGE_MARGIN) | (halpe[:, 0] > w - IMAGE_MARGIN) |
                   (halpe[:, 1] < IMAGE_MARGIN) | (halpe[:, 1] > h - IMAGE_MARGIN))
            score[oob] *= 0.1
            pts.append(halpe)
            valid.append(score > conf_threshold)
        return np.array(pts, float), np.array(valid)
    return c["pose2d"][s:e].astype(float), c["score2d"][s:e] > conf_threshold


def rewrite_metrabs(prefix, subset, base_name, c, chosen, K, dist):
    from humancalib.pose.metrabs_outputs import write_camera_outputs
    poses3d, poses2d, confs = [], [], []
    for row, k in enumerate(chosen):
        if k < 0 or c["status"][row] != cand.STATUS_OK:
            poses3d.append(None)
            poses2d.append(None)
            confs.append(0.0)
            continue
        i = c["start"][row] + k
        poses3d.append(c["pose3d"][i].astype(np.float32))
        poses2d.append(c["pose2d"][i].astype(np.float32))
        confs.append(float(c["box"][i][4]))
    h, w = c["imshape"]
    d = os.path.join(prefix, subset)
    return write_camera_outputs(list(c["frames"]), poses3d, poses2d, confs, K, dist, int(w), int(h),
                                os.path.join(d, "2d_joint"), os.path.join(d, "3d_joint"),
                                os.path.join(d, "2d_joint_halpe26"), base_name)


def rewrite_rtmpose(prefix, subset, base_name, c, chosen):
    from humancalib.pose.rtmlib_inference import halpe26_to_op25
    op25, halpe = [], []
    for row, k in enumerate(chosen):
        kp, sc = np.zeros((26, 2)), np.zeros(26)
        if k >= 0:
            i = c["start"][row] + k
            kp, sc = c["pose2d"][i], c["score2d"][i]
        kp_op, sc_op = halpe26_to_op25(kp, sc)
        frame = int(c["frames"][row])
        op25.append({"frame_index": frame, "skeleton": [{"pose": kp_op.flatten().tolist(), "score": sc_op.tolist()}]})
        halpe.append({"frame_index": frame, "skeleton": [{"pose": np.asarray(kp).flatten().tolist(),
                                                           "score": np.asarray(sc).tolist()}]})
    for sub, data in (("2d_joint", op25), ("2d_joint_halpe26", halpe)):
        with open(os.path.join(prefix, subset, sub, base_name), "w") as f:
            json.dump({"data": data}, f, indent=2, ensure_ascii=True)


def write_selection(args, cands, names, selections, K, dist):
    """Rewrite every camera's pose files for one selection (index per frame, -1 for none)."""
    skeleton_ref = None
    for ci, (c, name, chosen) in enumerate(zip(cands, names, selections)):
        if args.engine == "metrabs":
            full3d = rewrite_metrabs(args.prefix, args.subset, name, c, chosen, K[ci], dist[ci])
            if skeleton_ref is None:
                skeleton_ref = (list(c["frames"]), full3d)
        else:
            rewrite_rtmpose(args.prefix, args.subset, name, c, chosen)
    if skeleton_ref is not None:
        from humancalib.pose.metrabs_outputs import save_skeleton_w
        save_skeleton_w(os.path.join(args.prefix, args.subset, f"skeleton_w_G{args.gid:03d}.json"), *skeleton_ref)


def main(argv=None):
    """Re-select persons and rewrite the pose files. Returns how many (camera, frame) selections changed."""
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prefix", required=True)
    p.add_argument("--subset", default="noise_1_0")
    p.add_argument("--aid", type=int, default=1)
    p.add_argument("--pid", type=int, default=1)
    p.add_argument("--gid", type=int, default=1)
    p.add_argument("--calib", default="linear_1_0_ba", help="calibration used to triangulate the subject")
    p.add_argument("--engine", required=True, choices=("metrabs", "rtmpose"))
    p.add_argument("--conf_threshold", type=float, default=0.5)
    p.add_argument("--abs_px", type=float, default=50.0)
    p.add_argument("--x_median", type=float, default=5.0)
    p.add_argument("--min_cams", type=int, default=3)
    p.add_argument("--reset_to_largest", action="store_true",
                   help="only rewrite the pose files with extraction's own selection (largest box), "
                        "so a run reusing cached poses starts where extraction left it")
    args = p.parse_args(argv)

    CAMID, K, _, _, dist = load_eldersim_camera(os.path.join(args.prefix, args.subset, f"cameras_G{args.gid:03d}.json"))

    names = [f"A{args.aid:03d}_P{args.pid:03d}_G{args.gid:03d}_C{int(cid):03d}.json" for cid in CAMID]
    cands = []
    for name in names:
        path = cand.candidates_path(args.prefix, args.subset, name)
        if not os.path.isfile(path):
            raise SystemExit(f"no candidate detections at {path}: re-run pose extraction")
        cands.append(cand.load_candidates(path))

    # Largest-box selection, exactly as extraction made it, on every frame of every camera.
    current = []
    for c in cands:
        sel = np.full(len(c["frames"]), -1)
        for row in range(len(c["frames"])):
            s, e = c["start"][row], c["start"][row + 1]
            if c["status"][row] == cand.STATUS_OK and e > s:
                sel[row] = cand.largest(args.engine, c["box"][s:e], c["pose2d"][s:e], c["imshape"])
        current.append(sel)

    if args.reset_to_largest:
        write_selection(args, cands, names, current, K, dist)
        sidecars = os.path.join(args.prefix, args.subset, SIDECAR_DIRNAME)
        if os.path.isdir(sidecars):
            shutil.rmtree(sidecars)
        log.info("Pose files reset to the largest-box selection")
        return 0

    CAMID_c, _, R, t, _ = load_eldersim_camera(os.path.join(args.prefix, "results", f"{args.calib}.json"))
    if list(CAMID_c) != list(CAMID):
        raise SystemExit(f"camera ids differ between {args.calib} and cameras_G{args.gid:03d}.json")
    Ps = np.array([K[i] @ np.hstack([R[i], t[i].reshape(3, 1)]) for i in range(len(CAMID))])

    common = sorted(set.intersection(*(set(c["frames"].tolist()) for c in cands)))
    rows = [{f: i for i, f in enumerate(c["frames"].tolist())} for c in cands]
    cameras = []
    for ci, c in enumerate(cands):
        per_frame = []
        for f in common:
            row = rows[ci][f]
            s, e = c["start"][row], c["start"][row + 1]
            pts, valid = matching_points(args.engine, c, row, K[ci], dist[ci], args.conf_threshold)
            ok = (cand.plausible(args.engine, c["box"][s:e], c["pose2d"][s:e], c["imshape"])
                  if c["status"][row] == cand.STATUS_OK else np.zeros(e - s, dtype=bool))
            per_frame.append((pts, valid, ok))
        cameras.append(per_frame)
    cur_common = np.array([[current[ci][rows[ci][f]] for f in common] for ci in range(len(cands))])

    log.info(f"Re-selecting persons on {len(common)} frames, {len(cands)} cameras "
             f"(calibration {args.calib}, gate max({args.abs_px:g}px, {args.x_median:g}x median))")
    new_common, kept_cost = select_by_geometry(cameras, Ps, cur_common, args.abs_px, args.x_median, args.min_cams)
    matched = new_common >= 0
    new_common = drop_unmatched(new_common, kept_cost, args.abs_px, args.x_median)
    unmatched = matched & (new_common < 0)

    report, total = {"calib": args.calib, "frames": len(common), "cameras": {}}, 0
    selections = []
    for ci, (c, name) in enumerate(zip(cands, names)):
        chosen = current[ci].copy()
        for j, f in enumerate(common):
            chosen[rows[ci][f]] = new_common[ci, j]
        selections.append(chosen)
        changed = int((chosen != current[ci]).sum())
        total += changed
        multi = int(sum(1 for row in range(len(c["frames"])) if c["start"][row + 1] - c["start"][row] > 1))
        n_none = int(unmatched[ci].sum())
        report["cameras"][str(int(CAMID[ci]))] = {"changed": changed, "no_person": n_none,
                                                   "frames_with_several_people": multi}
        log.info(f"  Cam {int(CAMID[ci])}: {changed} frames changed, of which {n_none} now without a person "
                 f"({multi} frames with several people)")
    write_selection(args, cands, names, selections, K, dist)

    sidecars = os.path.join(args.prefix, args.subset, SIDECAR_DIRNAME)
    if os.path.isdir(sidecars):
        shutil.rmtree(sidecars)
        log.info("  Removed the outlier-frame drops of the first pass; they are recomputed")

    report["changed_total"] = total
    report["changed_fraction"] = total / max(1, sum(len(c["frames"]) for c in cands))
    with open(os.path.join(args.prefix, "results", "person_selection.json"), "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"PERSON_RESELECTED={total}")
    return total


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(0 if main() is not None else 1)
