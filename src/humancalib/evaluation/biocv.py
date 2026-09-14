"""BioCV (University of Bath): gold calibration reader and session preparation.

Layout of the dataset, as used here:

    <root>/participantData.csv                        stature in metres
    <root>/Pxx/Pxx/Pxx_<TRIAL>/0N.mp4                  9 synchronised cameras
    <root>/Pxx/Pxx/0N.mp4-mocAligned.calib            original calibration
    <root>/calibrationUpdate/Pxx/0N.mp4-mocAligned2.calib   refined alignment

A .calib file is plain text: width, height, the 3x3 K, a 4x4 world-to-camera
matrix L in millimetres, then k1 k2 p1 p2 k3. The world is the motion-capture
frame, Z up.

The 3x3 block of L is not a rotation: it is s*R with s slightly below 1 (about
0.998). A projection matrix is defined up to scale, so [s*R | t] and
[R | t/s] project every point identically; the camera is read as the latter.
Taking the block as R directly would leave t unscaled and misplace the camera
centre, and orthonormalising it without dividing t would do the same.

Usage:
    python -m humancalib.evaluation.biocv prepare --root <BioCV> --participant P03 \\
        --trial WALK_01 --out <work>/P03_WALK_01
"""
import argparse
import csv
import json
import os

import numpy as np

from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation.rig import Camera, orthonormalize, write_pose2sim_toml

log = get_logger(__name__)

N_CAMERAS = 9


def parse_calib(text, name):
    """(Camera, s) from the text of a .calib file; s is the scale removed from L."""
    values = [float(v) for v in text.split()]
    if len(values) < 2 + 9 + 16 + 4:
        raise ValueError(f"{name}: {len(values)} numbers, expected at least 31")
    width, height = values[0], values[1]
    K = np.array(values[2:11]).reshape(3, 3)
    L = np.array(values[11:27]).reshape(4, 4)
    dist = np.array(values[27:])
    M, t_mm = L[:3, :3], L[:3, 3]
    s = np.cbrt(np.linalg.det(M))
    if s <= 0:
        raise ValueError(f"{name}: the rotation block has a non-positive determinant")
    R = orthonormalize(M / s)
    return Camera(name=name, size=(width, height), K=K, dist=dist, R=R, t=t_mm / s / 1000.0), s


def calib_path(root, participant, cam_index, updated=True):
    if updated:
        return os.path.join(root, "calibrationUpdate", participant, f"{cam_index:02d}.mp4-mocAligned2.calib")
    return os.path.join(root, participant, participant, f"{cam_index:02d}.mp4-mocAligned.calib")


def read_rig(root, participant, updated=True):
    """The 9 gold cameras, named 00..08 like their videos."""
    cameras = []
    for i in range(N_CAMERAS):
        with open(calib_path(root, participant, i, updated)) as f:
            cam, _ = parse_calib(f.read(), f"{i:02d}")
        cameras.append(cam)
    return cameras


def stature(root, participant):
    with open(os.path.join(root, "participantData.csv"), newline="") as f:
        for row in csv.DictReader(f):
            if row["Participant Code"].strip() == participant:
                return float(row["Stature (m)"])
    raise KeyError(f"{participant} not in participantData.csv")


def trial_dir(root, participant, trial):
    return os.path.join(root, participant, participant, f"{participant}_{trial}")


def prepare(root, participant, trial, out, updated=True):
    """HumanCalib's input for one trial, plus the gold calibration.

    HumanCalib reads the videos in place: the trial folder holds only 00..08.mp4
    as videos, and the cameras are named after them.

    <out>/input/Calib_scene.toml gold intrinsics only (HumanCalib's input)
    <out>/gold/Calib_gold.toml   gold intrinsics and extrinsics (Pose2Sim)
    <out>/gold/meta.json         where it all came from
    """
    src = trial_dir(root, participant, trial)
    inp, gold = os.path.join(out, "input"), os.path.join(out, "gold")
    os.makedirs(inp, exist_ok=True)
    os.makedirs(gold, exist_ok=True)

    cameras = read_rig(root, participant, updated)
    for cam in cameras:
        video = os.path.join(src, f"{cam.name}.mp4")
        if not os.path.isfile(video):
            raise FileNotFoundError(video)

    write_pose2sim_toml(cameras, os.path.join(inp, "Calib_scene.toml"), extrinsics=False)
    write_pose2sim_toml(cameras, os.path.join(gold, "Calib_gold.toml"), extrinsics=True)
    meta = {
        "dataset": "BioCV", "participant": participant, "trial": trial,
        "stature_m": stature(root, participant), "video_dir": src,
        "calibration": [calib_path(root, participant, i, updated) for i in range(N_CAMERAS)],
        "world": "motion-capture frame, Z up, metres",
        "up": [0.0, 0.0, 1.0],
    }
    with open(os.path.join(gold, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Prepared {participant}_{trial} in {out} (stature {meta['stature_m']} m)")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="input folder and gold calibration for one trial")
    p.add_argument("--root", required=True, help="BioCV dataset root")
    p.add_argument("--participant", required=True, help="e.g. P03")
    p.add_argument("--trial", required=True, help="e.g. WALK_01")
    p.add_argument("--out", required=True)
    p.add_argument("--original", action="store_true", help="use the original, not the updated, calibration")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.root, args.participant, args.trial, args.out, updated=not args.original)
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
