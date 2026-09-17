"""LBMC markerless benchmark (Muller & Robert 2025, doi:10.57745/LQI2MJ): gold rig and trials.

Layout of the dataset, as used here::

    <root>/Video_Data/calibration/Calib.toml               upright rig, OpenCV notation
    <root>/Video_RawData/calibration/Calib.qca.txt         Qualisys export of the same calibration
    <root>/Video_Data/participant_0N/<task>/videos/<serial>/<serial>.avi   9 cameras, 60 Hz

Two participants (157 and 174 cm), tasks gait (treadmill), sit-stand, mmh, exotic, and a
dance performed together. 9 Qualisys Miqus Video cameras, hardware-synchronised, mounted on
their side: the pre-processed videos are portrait 1088x1920.

One thing decides this reader: `Calib.toml` has the right K, R and t for the upright videos,
but its distortion coefficients are wrong. Compared with the Qualisys export, every one of
them is divided by 64 -- the factor Qualisys uses for its subpixel intrinsics, which does not
apply to dimensionless coefficients -- and the tangential pair was not turned with the image.
The coefficients are therefore taken from `Calib.qca.txt` and turned here. Which way each
camera was turned is read from its principal point, since the cameras were not all mounted
the same way round.

Usage::

    python -m humancalib.evaluation.lbmc prepare --root <LBMC> --participant 2 --task gait \\
        --out <work>/lbmc_p2_gait
"""
import argparse
import json
import os
import re
import shutil

import numpy as np

from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation.rig import Camera, write_pose2sim_toml

log = get_logger(__name__)

UP = [0.0, 0.0, 1.0]
FPS = 60.0
SUBPIXEL = 64.0                               # Qualisys intrinsics are stored in 1/64 pixel
STATURE_M = {1: 1.57, 2: 1.74}                # README, table "Participants"


def _attr(text, key):
    m = re.search(rf'\b{key}="([-\d.eE+]+)"', text)
    if m is None:
        raise ValueError(f"attribute {key} missing")
    return float(m.group(1))


def read_raw(text):
    """{serial: dict(fx, fy, cx, cy, W, H, dist=[k1, k2, p1, p2, k3])} from the Qualisys export,
    in pixels of the unrotated sensor."""
    out = {}
    for m in re.finditer(r'<camera [^>]*serial="(\d+)".*?<intrinsic ([^/]*)/>', text, re.S):
        it = m.group(2)
        out[m.group(1)] = dict(
            fx=_attr(it, "focalLengthU") / SUBPIXEL, fy=_attr(it, "focalLengthV") / SUBPIXEL,
            cx=_attr(it, "centerPointU") / SUBPIXEL, cy=_attr(it, "centerPointV") / SUBPIXEL,
            W=(_attr(it, "sensorMaxU") + 1) / SUBPIXEL, H=(_attr(it, "sensorMaxV") + 1) / SUBPIXEL,
            dist=[_attr(it, "radialDistortion1"), _attr(it, "radialDistortion2"),
                  _attr(it, "tangentalDistortion1"), _attr(it, "tangentalDistortion2"),
                  _attr(it, "radialDistortion3")])
    return out


def rotated_distortion(raw, K):
    """The raw coefficients turned the way the image was, decided by the upright principal point.

    Clockwise, (u, v) -> (H-v, u): cx' = H - cy. Counter-clockwise, (u, v) -> (v, W-u): cx' = cy."""
    k1, k2, p1, p2, k3 = raw["dist"]
    clockwise = abs(K[0, 2] - (raw["H"] - raw["cy"])) < abs(K[0, 2] - raw["cy"])
    if clockwise:
        return np.array([k1, k2, p2, -p1, k3]), True
    return np.array([k1, k2, -p2, p1, k3]), False


def read_rig(root):
    import cv2
    import toml
    cal = toml.load(os.path.join(root, "Video_Data", "calibration", "Calib.toml"))
    with open(os.path.join(root, "Video_RawData", "calibration", "Calib.qca.txt"), errors="ignore") as f:
        raw = read_raw(f.read())
    cameras = []
    for key in sorted((k for k in cal if k.startswith("cam")), key=lambda k: int(k.split("_")[1])):
        c = cal[key]
        serial = str(c["name"])
        K = np.asarray(c["matrix"], float)
        if not np.isclose(K[0, 0], raw[serial]["fy"], rtol=1e-4):
            raise ValueError(f"camera {serial}: Calib.toml and Calib.qca.txt do not describe the same calibration")
        dist, _ = rotated_distortion(raw[serial], K)
        cameras.append(Camera(name=serial, size=tuple(float(v) for v in c["size"]), K=K, dist=dist,
                              R=cv2.Rodrigues(np.asarray(c["rotation"], float))[0],
                              t=np.asarray(c["translation"], float)))
    return cameras


def video_path(root, participant, task, serial):
    return os.path.join(root, "Video_Data", f"participant_{int(participant):02d}", task, "videos",
                        serial, f"{serial}.avi")


def prepare(root, participant, task, out):
    inp, gold, vids = os.path.join(out, "input"), os.path.join(out, "gold"), os.path.join(out, "_videos")
    for d in (inp, gold, vids):
        os.makedirs(d, exist_ok=True)
    cameras = read_rig(root)
    for cam in cameras:
        src = video_path(root, participant, task, cam.name)
        if not os.path.isfile(src):
            raise FileNotFoundError(src)
        dst = os.path.join(vids, f"{cam.name}.avi")
        if not os.path.isfile(dst):
            shutil.copyfile(src, dst)
    write_pose2sim_toml(cameras, os.path.join(inp, "Calib_scene.toml"), extrinsics=False)
    write_pose2sim_toml(cameras, os.path.join(gold, "Calib_gold.toml"), extrinsics=True)
    meta = {"dataset": "LBMC", "participant": f"participant_{int(participant):02d}", "trial": task,
            "stature_m": STATURE_M[int(participant)], "video_dir": vids, "fps": FPS,
            "world": "Qualisys frame, Z up, metres", "up": UP,
            "distortion": "Calib.qca.txt, turned with the image (Calib.toml's are divided by 64)"}
    with open(os.path.join(gold, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Prepared LBMC participant {participant} {task} in {out}: {len(cameras)} cameras, "
             f"stature {meta['stature_m']} m")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--root", required=True)
    p.add_argument("--participant", required=True, type=int, choices=(1, 2))
    p.add_argument("--task", default="gait")
    p.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    prepare(args.root, args.participant, args.task, args.out)
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
