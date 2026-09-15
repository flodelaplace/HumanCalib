#!/usr/bin/env python3
"""Detect per-camera outlier frames after linear calibration.

For each camera, computes the mean per-frame reprojection error and flags
frames whose error exceeds BOTH ``--abs_px`` AND ``--x_median * median``.
Outliers are appended to the per-video sidecar ``<video>.dropped.json`` and
their scores are zeroed in the saved 2D/3D pose JSONs so an immediate
re-run of the linear calibration sees them as drops without re-running
MeTRAbs.

Prints ``NEW_DROPS=<n>`` on the last line for shell consumption.

Usage:
    python -m humancalib.pipeline.detect_outlier_frames \\
        --prefix ./output/my_session \\
        --subset noise_1_0 --aid 1 --pid 1 --gid 1 \\
        --calib linear_1_0 \\
        --video_dir ./input/my_session \\
        --abs_px 50 --x_median 5
"""
import argparse
import json
import os
import sys

import numpy as np


from humancalib.postprocessing.evaluate_calibration import triangulate_skeleton, reproject_points
from humancalib.core import load_poses, load_eldersim_camera
from humancalib.core.sidecars import write_dropped
from humancalib.core.videos import list_videos
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prefix", required=True)
    p.add_argument("--subset", default="noise_1_0")
    p.add_argument("--aid", type=int, default=1)
    p.add_argument("--pid", type=int, default=1)
    p.add_argument("--gid", type=int, default=1)
    p.add_argument("--calib", default="linear_1_0")
    p.add_argument("--video_dir", required=True)
    p.add_argument("--abs_px", type=float, default=50.0)
    p.add_argument("--x_median", type=float, default=5.0)
    p.add_argument("--conf_threshold", type=float, default=0.5)
    return p.parse_args(argv)


def load_camera_poses(prefix, subset, aid, pid, gid, n_cams):
    """Load per-camera 2D poses, restricted to the frames every camera has.

    Synchronised videos can still differ by a frame or two in decoded length
    (BioCV: 1302 frames on most cameras, 1301 on two). The calibration steps
    already truncate to the shortest camera; stacking ragged arrays here
    instead crashed the whole run after pose extraction.
    """
    loaded = []
    for cid in range(1, n_cams + 1):
        fname = f"A{aid:03d}_P{pid:03d}_G{gid:03d}_C{cid:03d}.json"
        f2d, p2d, s2d = load_poses(os.path.join(prefix, subset, "2d_joint", fname))
        loaded.append(([int(f) for f in f2d], p2d, s2d))

    common = set(loaded[0][0])
    for frames, _, _ in loaded[1:]:
        common &= set(frames)
    frame_indices = sorted(common)
    if any(len(frames) != len(frame_indices) for frames, _, _ in loaded):
        log.warning(f"cameras differ in frame count ({[len(f) for f, _, _ in loaded]}); "
                    f"using the {len(frame_indices)} frames they share")

    p2d_all, s2d_all = [], []
    for frames, p2d, s2d in loaded:
        row = {f: i for i, f in enumerate(frames)}
        keep = [row[f] for f in frame_indices]
        n_joints = s2d.shape[1]
        p2d_all.append(p2d.reshape(-1, n_joints, 2)[keep])
        s2d_all.append(s2d[keep])
    return frame_indices, np.array(p2d_all), np.array(s2d_all)


def per_frame_reproj_errors(p2d, s2d, X3d_world, K, R_w2c, t_w2c, conf_threshold):
    """Mean reprojection error per camera per frame. Returns (C, N), NaN if no visible joints."""
    p2d_reproj = reproject_points(X3d_world, K, R_w2c, t_w2c)
    err = np.linalg.norm(p2d_reproj - p2d, axis=-1)
    valid = (s2d > conf_threshold) & ~np.isnan(err)
    with np.errstate(invalid='ignore', all='ignore'):
        err_masked = np.where(valid, err, np.nan)
        return np.nanmean(err_masked, axis=2)


def detect_outliers(frame_errors, abs_px, x_median):
    """Per-camera outlier indices into the frame_indices array."""
    C, _ = frame_errors.shape
    outliers = []
    for c in range(C):
        errs = frame_errors[c]
        with np.errstate(invalid='ignore', all='ignore'):
            med = np.nanmedian(errs)
        if np.isnan(med):
            outliers.append(set())
            continue
        thr = max(abs_px, x_median * med)
        bad = np.where((errs > thr) & ~np.isnan(errs))[0]
        outliers.append({int(i) for i in bad})
    return outliers



def zero_scores_in_json(json_path, dropped_frames):
    """Set score and pose to zeros for entries whose frame_index is in dropped_frames."""
    with open(json_path) as f:
        d = json.load(f)
    n_changed = 0
    for entry in d['data']:
        if int(entry['frame_index']) in dropped_frames:
            for sk in entry['skeleton']:
                n_joints = len(sk['score'])
                pose_dim = len(sk['pose']) // n_joints if n_joints else 0
                sk['score'] = [0.0] * n_joints
                sk['pose'] = [0.0] * (n_joints * pose_dim)
                n_changed += 1
    if n_changed > 0:
        with open(json_path, 'w') as f:
            json.dump(d, f, indent=2)
    return n_changed


def main(argv=None):
    """Detect and drop outlier frames. Returns how many frames were newly dropped."""
    args = parse_args(argv)

    calib_path = os.path.join(args.prefix, "results", f"{args.calib}.json")
    CAMID, K, R_w2c, t_w2c, _ = load_eldersim_camera(calib_path)
    n_cams = len(CAMID)

    frame_indices, p2d, s2d = load_camera_poses(
        args.prefix, args.subset, args.aid, args.pid, args.gid, n_cams
    )

    X3d = triangulate_skeleton(p2d, s2d, K, R_w2c, t_w2c, args.conf_threshold)
    frame_errors = per_frame_reproj_errors(p2d, s2d, X3d, K, R_w2c, t_w2c, args.conf_threshold)
    outliers = detect_outliers(frame_errors, args.abs_px, args.x_median)

    video_files = list_videos(args.video_dir)
    if len(video_files) != n_cams:
        log.error(f"found {len(video_files)} videos in {args.video_dir} "
              f"but calib has {n_cams} cams")
        sys.exit(1)

    log.info(f"Thresholds: error > {args.abs_px}px AND error > {args.x_median}x median")
    total_added = 0
    for c in range(n_cams):
        cid = int(CAMID[c])
        with np.errstate(invalid='ignore', all='ignore'):
            med = float(np.nanmedian(frame_errors[c]))
            mx = float(np.nanmax(frame_errors[c])) if np.any(~np.isnan(frame_errors[c])) else float('nan')

        bad_idx = outliers[c]
        if not bad_idx:
            log.info(f"  Cam {cid}: 0 outliers (median {med:.1f}px, max {mx:.1f}px)")
            continue

        bad_frames = {frame_indices[i] for i in bad_idx}
        worst = float(np.nanmax([frame_errors[c, i] for i in bad_idx]))
        log.info(f"  Cam {cid}: {len(bad_frames)} outliers (median {med:.1f}px, "
              f"worst-outlier {worst:.1f}px)")

        added = write_dropped(args.prefix, args.subset, video_files[c], bad_frames)
        total_added += added

        fname = f"A{args.aid:03d}_P{args.pid:03d}_G{args.gid:03d}_C{cid:03d}.json"
        for sub in ("2d_joint", "3d_joint", "2d_joint_halpe26"):
            jp = os.path.join(args.prefix, args.subset, sub, fname)
            if os.path.exists(jp):
                zero_scores_in_json(jp, bad_frames)

    log.info(f"NEW_DROPS={total_added}")
    return total_added


if __name__ == "__main__":
    setup_logging()
    main()
