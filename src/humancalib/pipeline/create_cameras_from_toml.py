"""
create_cameras_from_toml.py
----------------------------
Build cameras_G{gid}.json -- and, when the pose step wrote none, a placeholder
skeleton_w_G{gid}.json -- from a calibration TOML (Pose2Sim / AniPose format).

Looks up the TOML sections whose names match the given video names.

Usage:
    python -m humancalib.pipeline.create_cameras_from_toml \
        --toml       ./Calibration.toml \
        --output_dir ./data/A001_P001_G001/raw_rtm \
        --gid 1 \
        --cam_names "video1" "video2" "video3"

The TOML needs one [video_name] section per camera with:
    matrix       = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
    rotation     = [rx, ry, rz]   <- Rodrigues vector
    translation  = [tx, ty, tz]
    size         = [width, height]
"""

import argparse
import json
import os
import sys
import glob

import numpy as np
import cv2

from humancalib.core.toml_io import load_toml
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert a calibration TOML into cameras_G{gid}.json"
    )
    parser.add_argument("--toml", required=True, help="Path to the .toml file")
    parser.add_argument("--output_dir", required=True, help="Output directory")
    parser.add_argument("--gid", type=int, default=1, help="Group/Scene ID")
    parser.add_argument("--cam_names", nargs='+', required=True, help="Video base names without extension, in camera order")
    args = parser.parse_args(argv)

    # ---- Read the TOML -------------------------------------------------------
    data = load_toml(args.toml)

    log.info(f"Looking up TOML sections for cameras: {args.cam_names}")

    # ---- Extract K, R, t for each camera --------------------------------
    cam_ids, K_list, R_list, t_list, dist_list = [], [], [], [], []

    for i, cam_name in enumerate(args.cam_names, start=1):
        if cam_name not in data:
            log.error(f"section '[{cam_name}]' not found in TOML file {args.toml}")
            sys.exit(1)

        sec = data[cam_name]
        cam_ids.append(i)

        K = np.array(sec["matrix"], dtype=np.float64)
        K_list.append(K)

        rvec = np.array(sec["rotation"], dtype=np.float64)
        R, _ = cv2.Rodrigues(rvec)
        R_list.append(R)

        t = np.array(sec["translation"], dtype=np.float64)
        t_list.append(t)

        dist = np.array(sec.get("distortions", [0, 0, 0, 0, 0]), dtype=np.float64)
        dist_list.append(dist)

        log.info(f"  -> Found '{cam_name}' (Cam ID {i})")

    # ---- Save cameras_G{gid}.json ------------------------------------
    os.makedirs(args.output_dir, exist_ok=True)
    cam_path = os.path.join(args.output_dir, f"cameras_G{args.gid:03d}.json")

    out = {
        "CAMID": cam_ids,
        "K": [k.tolist() for k in K_list],
        "R_w2c": [R.tolist() for R in R_list],
        "t_w2c": [t.tolist() for t in t_list],
        "dist_coeffs": [d.tolist() for d in dist_list],
    }
    with open(cam_path, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=True)
    log.info(f"\nSaved: {cam_path}")

    # ---- skeleton_w_G{gid}.json ---------------------------------------------
    #
    # Only a placeholder, and only when nothing real is there. The MeTRAbs step
    # writes a genuine world skeleton before this script runs; overwriting it
    # threw that away on every run. Nothing reads the coordinates today
    # (load_eldersim returns them as p3d_w, which calib_linear discards and ba
    # slices but never uses), so this mattered less than it looks -- but the
    # file has to exist for load_eldersim, and the RTMPose backend writes none.
    #
    # The frame indices are 0-based, matching the pose files. They used to
    # start at 1, and load_eldersim intersects the two index lists
    # (humancalib/core/poses_io.py), so frame 0 was discarded from every calibration
    # without a word. See B7 in docs/REFACTOR_PLAN.md for the measured effect.
    skel_path = os.path.join(args.output_dir, f"skeleton_w_G{args.gid:03d}.json")
    if os.path.exists(skel_path):
        log.info(f"Kept:  {skel_path} (already written by the pose step)")
    else:
        joint_files = glob.glob(os.path.join(args.output_dir, "2d_joint", "*.json"))
        n_frames = 100
        frame_indices = None
        if joint_files:
            with open(sorted(joint_files)[0]) as jf:
                jdata = json.load(jf)
            n_frames = len(jdata["data"])
            # Take the pose files' own indices rather than assuming a range:
            # dropped frames leave gaps, and an assumed range would reintroduce
            # exactly the mismatch this replaces.
            frame_indices = [int(fr["frame_index"]) for fr in jdata["data"]]
        if frame_indices is None:
            frame_indices = list(range(n_frames))

        skel_out = {
            "skeleton": np.zeros((n_frames, 25, 3), dtype=np.float64).tolist(),
            "frame_indices": frame_indices,
        }
        with open(skel_path, "w") as f:
            json.dump(skel_out, f, indent=2, ensure_ascii=True)
        log.info(f"Saved: {skel_path} (placeholder, {n_frames} frames)")

if __name__ == "__main__":
    setup_logging()
    main()
