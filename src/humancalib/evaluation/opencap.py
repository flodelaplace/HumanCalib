"""OpenCap (Uhlrich et al. 2023): gold calibration reader and session preparation.

Layout of the dataset, as used here::

    <root>/_RAW_WINDOWS.json                          synchronisation of every raw video
    <root>/subjectN/sessionMetadata.yaml              height_m, mass_kg
    <root>/subjectN/VideoData/Session1/CamM/cameraIntrinsicsExtrinsics.pickle
    <root>/subjectN/VideoData/Session1/CamM/<trial>/<trial>.avi

Five iPhone cameras, and only Session1 holds the walking trials: walking1-3
(natural) and walkingTS1-4 (with a trunk-sway gait modification, which moves the
trunk more and so excites the calibration better).

Three things differ from BioCV and decide this reader:

* the cameras are **not synchronised**. The same trial is 601 frames on one
  camera and 595 on another, and each starts at its own moment -- `raw_start`
  spreads over 2.2 s. `_RAW_WINDOWS.json` gives that offset per camera, so the
  videos are re-cut here around it. The `<trial>_syncdWithMocap.avi` clips the
  dataset ships are aligned but last 1.4 s; re-cutting the raw videos keeps
  7.2 s on average, five times more.
* `imageSize` is stored as [1280, 720] while the videos are portrait 720x1280.
  The principal point settles it (cx = 366 ~ 720/2, cy = 639 ~ 1280/2), so the
  size is taken from the intrinsics, not from that field.
* the world is the video frame, **Y pointing down**: on 15 cameras the image's
  own downward axis (R[1]) projects on +Y at 0.997, and the optical centres sit
  at y = -0.90 m, i.e. 0.90 m above the floor. Hence up = [0, -1, 0].

The marker files (MarkerData) are in the motion-capture frame, not this one, and
`mocapToVideoTransform.yaml` is degenerate for Session1 on all nine subjects
(zero determinant), so markers cannot be reprojected into these images. That
costs nothing here: comparing a calibration with the gold one only uses cameras.

Usage::

    python -m humancalib.evaluation.opencap prepare --root <OpenCap> \\
        --subject subject2 --trial walking1 --out <work>/subject2_walking1
"""
import argparse
import json
import os
import pickle
import shutil
import subprocess
import sys

import numpy as np
import yaml

from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation.rig import Camera, write_pose2sim_toml

log = get_logger(__name__)

N_CAMERAS = 5
SESSION = "Session1"          # the only session with walking trials
WINDOWS_FILE = "_RAW_WINDOWS.json"
UP = [0.0, -1.0, 0.0]


def camera_dir(root, subject, cam, session=SESSION):
    return os.path.join(root, subject, "VideoData", session, f"Cam{cam}")


def image_size(K, stored):
    """(width, height) in pixels.

    `imageSize` is stored as [1280, 720] for portrait 720x1280 videos, so it is
    read in whichever order agrees with the principal point.
    """
    if stored is None:
        return (2.0 * K[0, 2], 2.0 * K[1, 2])
    a, b = (float(v) for v in np.asarray(stored, dtype=float).ravel()[:2])
    wide_image, wide_principal = a > b, K[0, 2] > K[1, 2]
    return (a, b) if wide_image == wide_principal else (b, a)


def parse_calib(path, name):
    """One Camera from a cameraIntrinsicsExtrinsics.pickle.

    The stored rotation and translation are world-to-camera (OpenCV's
    convention, det(R) = 1) and the translation is in millimetres.
    """
    with open(path, "rb") as f:
        d = pickle.load(f)
    K = np.asarray(d["intrinsicMat"], dtype=float)
    dist = np.asarray(d["distortion"], dtype=float).ravel()
    R = np.asarray(d["rotation"], dtype=float)
    t = np.asarray(d["translation"], dtype=float).ravel() / 1000.0
    if not np.isclose(np.linalg.det(R), 1.0, atol=1e-3):
        raise ValueError(f"{name}: det(R) = {np.linalg.det(R):.4f}, not a rotation")
    return Camera(name=name, size=image_size(K, d.get("imageSize")), K=K, dist=dist, R=R, t=t)


def read_rig(root, subject, session=SESSION):
    """The 5 gold cameras, named Cam0..Cam4 like their folders."""
    cameras = []
    for i in range(N_CAMERAS):
        path = os.path.join(camera_dir(root, subject, i, session), "cameraIntrinsicsExtrinsics.pickle")
        cameras.append(parse_calib(path, f"Cam{i}"))
    return cameras


def stature(root, subject):
    with open(os.path.join(root, subject, "sessionMetadata.yaml")) as f:
        return float(yaml.safe_load(f)["height_m"])


def read_windows(root):
    with open(os.path.join(root, WINDOWS_FILE)) as f:
        return json.load(f)


def common_window(windows, subject, trial, session=SESSION):
    """(length, {camera: first frame}) of the longest window the 5 cameras share.

    Every camera has its own `raw_start` for the same instant, so the window is
    measured relative to it: as many frames before as the earliest camera allows,
    as many after as the shortest one does.
    """
    entries = {}
    for cam in range(N_CAMERAS):
        key = f"{subject}/{session}/Cam{cam}/{trial}"
        if key not in windows:
            raise KeyError(f"{key} missing from {WINDOWS_FILE}")
        entries[cam] = windows[key]
    before = min(e["raw_start"] for e in entries.values())
    after = min(e["raw_frames"] - e["raw_start"] for e in entries.values())
    if before + after <= 0:
        raise ValueError(f"{subject}/{trial}: no common window")
    return before + after, {cam: e["raw_start"] - before for cam, e in entries.items()}


def raw_video(root, subject, trial, cam, session=SESSION):
    return os.path.join(camera_dir(root, subject, cam, session), trial, f"{trial}.avi")


def cut_videos(root, subject, trial, dest, session=SESSION, windows=None):
    """The 5 raw videos, re-cut to their common window so they are synchronised.

    Frames are selected by number, never by timestamp, so the alignment computed
    from `_RAW_WINDOWS.json` is exactly what ends up in the files.
    """
    windows = windows if windows is not None else read_windows(root)
    length, starts = common_window(windows, subject, trial, session)
    os.makedirs(dest, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or os.path.join(os.path.dirname(sys.executable), "ffmpeg")
    for cam in range(N_CAMERAS):
        src = raw_video(root, subject, trial, cam, session)
        if not os.path.isfile(src):
            raise FileNotFoundError(src)
        first, last = starts[cam], starts[cam] + length - 1
        out = os.path.join(dest, f"Cam{cam}.avi")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src,
                        "-vf", f"select='between(n\\,{first}\\,{last})',setpts=N/FRAME_RATE/TB",
                        # MJPEG for the same reason as the BioCV copies: it is in every
                        # ffmpeg build, near-lossless, and these files are temporary.
                        "-c:v", "mjpeg", "-q:v", "2", "-pix_fmt", "yuvj420p", out],
                       check=True)
    log.info(f"Cut {N_CAMERAS} videos of {subject}/{trial} to {length} common frames")
    return dest, length


def prepare(root, subject, trial, out, session=SESSION):
    """HumanCalib's input for one trial, plus the gold calibration.

    <out>/_videos/CamN.avi       the raw videos re-cut to a common window
    <out>/input/Calib_scene.toml gold intrinsics only (HumanCalib's input)
    <out>/gold/Calib_gold.toml   gold intrinsics and extrinsics
    <out>/gold/meta.json         where it all came from
    """
    inp, gold = os.path.join(out, "input"), os.path.join(out, "gold")
    os.makedirs(inp, exist_ok=True)
    os.makedirs(gold, exist_ok=True)

    cameras = read_rig(root, subject, session)
    video_dir, length = cut_videos(root, subject, trial, os.path.join(out, "_videos"), session)

    write_pose2sim_toml(cameras, os.path.join(inp, "Calib_scene.toml"), extrinsics=False)
    write_pose2sim_toml(cameras, os.path.join(gold, "Calib_gold.toml"), extrinsics=True)
    meta = {
        "dataset": "OpenCap", "participant": subject, "trial": trial, "session": session,
        "stature_m": stature(root, subject), "video_dir": video_dir, "frames": length,
        "calibration": [os.path.join(camera_dir(root, subject, i, session),
                                     "cameraIntrinsicsExtrinsics.pickle") for i in range(N_CAMERAS)],
        "world": "video frame, Y down, metres",
        "up": UP,
    }
    with open(os.path.join(gold, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Prepared {subject}/{trial} in {out} (stature {meta['stature_m']} m, {length} frames)")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="input folder and gold calibration for one trial")
    p.add_argument("--root", required=True, help="OpenCap dataset root")
    p.add_argument("--subject", required=True, help="e.g. subject2")
    p.add_argument("--trial", required=True, help="e.g. walking1 or walkingTS2")
    p.add_argument("--out", required=True)
    p.add_argument("--session", default=SESSION)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare(args.root, args.subject, args.trial, args.out, args.session)
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
