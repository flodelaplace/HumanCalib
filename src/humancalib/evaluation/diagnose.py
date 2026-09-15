"""Why a calibration failed: per-camera diagnosis of the poses, using the gold rig as an oracle.

    python -m humancalib.evaluation.diagnose --work <trial folder> --run metrabs

For diagnosis only -- nothing here feeds the method. With the gold cameras, the
subject is triangulated in each frame by camera consensus (the re-selection
step's robust triangulation), and in every camera the pose HumanCalib kept is
compared with the subject's reprojection:

* correct  -- within `ok_px` of it: the subject, with this much keypoint noise;
* wrong    -- beyond `wrong_px`: another person, or a pose far off the subject;
* truncated-- some Halpe26 joint outside the image: the subject partly out of view.

Reads the Halpe26 poses (undistorted for MeTRAbs, so they match the gold pinhole
projection). Writes <work>/eval/<run>/diagnosis.csv, one row per camera, with the
calibration's own per-camera error from cameras.csv alongside.
"""
import argparse
import csv
import os

import numpy as np

from humancalib.cli import SUBSET
from humancalib.core import load_poses
from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation.rig import read_pose2sim_toml
from humancalib.pipeline.reselect_person import MIN_JOINTS, mean_reprojection, robust_triangulate

log = get_logger(__name__)


def diagnose(work, run, step=4, conf_threshold=0.5, ok_px=30.0, wrong_px=100.0, margin=10):
    gold = read_pose2sim_toml(os.path.join(work, "gold", "Calib_gold.toml"))
    Ps = np.array([g.projection() for g in gold])
    C = len(gold)
    d = os.path.join(work, run, SUBSET, "2d_joint_halpe26")
    names = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    if len(names) != C:
        raise ValueError(f"{len(names)} pose files, {C} gold cameras")
    frames, pts, sc = [], [], []
    for n in names:
        fi, p, s = load_poses(os.path.join(d, n))
        frames.append({int(f): i for i, f in enumerate(fi)})
        pts.append(p.reshape(len(fi), -1, 2))
        sc.append(s)
    common = sorted(set.intersection(*(set(f) for f in frames)))[::step]
    w, h = gold[0].size

    stats = {k: np.zeros(C) for k in ("seen", "correct", "wrong", "truncated")}
    noise = [[] for _ in range(C)]
    n_frames = 0
    for f in common:
        P2 = np.array([pts[c][frames[c][f]] for c in range(C)])
        V = np.array([sc[c][frames[c][f]] > conf_threshold for c in range(C)])
        seen = V.sum(axis=1) >= MIN_JOINTS
        if seen.sum() < 3:
            continue
        X, _ = robust_triangulate(P2, V, Ps, abs_px=50.0, x_median=5.0, min_cams=3)
        if not np.isfinite(X).any():
            continue
        n_frames += 1
        for c in range(C):
            if not seen[c]:
                continue
            stats["seen"][c] += 1
            e = mean_reprojection(P2[c:c + 1], V[c:c + 1], X, Ps[c])[0]
            if e <= ok_px:
                stats["correct"][c] += 1
                noise[c].append(e)
            elif e > wrong_px:
                stats["wrong"][c] += 1
            p = P2[c][V[c]]
            if ((p[:, 0] < margin) | (p[:, 0] > w - margin) | (p[:, 1] < margin) | (p[:, 1] > h - margin)).any():
                stats["truncated"][c] += 1

    est = {}
    cams_csv = os.path.join(work, "eval", run, "cameras.csv")
    if os.path.isfile(cams_csv):
        est = {r["cam"]: float(r["pair_rot_median_deg"]) for r in csv.DictReader(open(cams_csv))}
    rows = []
    for c in range(C):
        seen = max(stats["seen"][c], 1)
        rows.append({
            "cam": gold[c].name,
            "seen_pct": 100 * stats["seen"][c] / max(n_frames, 1),
            "correct_pct_of_seen": 100 * stats["correct"][c] / seen,
            "wrong_pct_of_seen": 100 * stats["wrong"][c] / seen,
            "truncated_pct_of_seen": 100 * stats["truncated"][c] / seen,
            "noise_px_median": float(np.median(noise[c])) if noise[c] else float("nan"),
            "calib_pair_rot_median_deg": est.get(gold[c].name, float("nan")),
        })
    return rows, n_frames


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", required=True)
    p.add_argument("--run", default="metrabs")
    p.add_argument("--step", type=int, default=4, help="use one frame in N")
    args = p.parse_args(argv)
    rows, n = diagnose(args.work, args.run, args.step)
    out = os.path.join(args.work, "eval", args.run, "diagnosis.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows(rows)
    log.info(f"{n} frames diagnosed -> {out}")
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
