"""
create_cameras_from_toml.py
----------------------------
Crée cameras_G{gid}.json et skeleton_w_G{gid}.json à partir d'un fichier
de calibration au format TOML (ex: Pose2Sim / AniPose).

Ce script recherche des sections dans le TOML qui correspondent aux noms
des vidéos fournies.

Usage:
    python create_cameras_from_toml.py \
        --toml       ./Calibration.toml \
        --output_dir ./data/A001_P001_G001/raw_rtm \
        --gid 1 \
        --cam_names "video1" "video2" "video3"

Le fichier TOML doit avoir des sections [video_name] avec:
    matrix       = [[fx, 0, cx], [0, fy, cy], [0, 0, 1]]
    rotation     = [rx, ry, rz]   <- vecteur de Rodrigues
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


def main():
    parser = argparse.ArgumentParser(
        description="Convertit un fichier TOML de calibration en cameras_G{gid}.json"
    )
    parser.add_argument("--toml", required=True, help="Chemin vers le fichier .toml")
    parser.add_argument("--output_dir", required=True, help="Dossier de sortie")
    parser.add_argument("--gid", type=int, default=1, help="Group/Scene ID")
    parser.add_argument("--cam_names", nargs='+', required=True, help="Liste des noms de base des vidéos (sans extension)")
    args = parser.parse_args()

    # ---- Lire le TOML -------------------------------------------------------
    data = load_toml(args.toml)

    print(f"Recherche des sections pour les caméras: {args.cam_names}")

    # ---- Extraire K, R, t pour chaque caméra --------------------------------
    cam_ids, K_list, R_list, t_list, dist_list = [], [], [], [], []

    for i, cam_name in enumerate(args.cam_names, start=1):
        if cam_name not in data:
            print(f"ERROR: La section '[{cam_name}]' n'a pas été trouvée dans le fichier TOML {args.toml}", file=sys.stderr)
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

        print(f"  -> Trouvé '{cam_name}' (Cam ID {i})")

    # ---- Sauvegarder cameras_G{gid}.json ------------------------------------
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
    print(f"\nSaved: {cam_path}")

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
        print(f"Kept:  {skel_path} (already written by the pose step)")
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
        print(f"Saved: {skel_path} (placeholder, {n_frames} frames)")

if __name__ == "__main__":
    main()
