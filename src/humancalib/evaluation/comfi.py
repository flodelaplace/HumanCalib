"""COMFI (LAAS-CNRS, Toulouse): gold rig and trials.

Layout of the dataset, as used here::

    <cam_root>/<participant>/intrinsics/camera_N_intrinsics.yaml
        OpenCV FileStorage: K (3x3), D (1x5), reproj -- board calibration, ~0.25 px
    <cam_root>/<participant>/extrinsics/cam_to_world/camera_N/camera_N_extrinsics.yaml
        camera -> world rotation_matrix and translation_vector (metres), rms_error --
        each camera registered to the motion-capture frame through an ArUco board
        whose corners also carry mocap markers (Soderkvist fit, rms ~1 mm)
    <video_root>/videos*/<participant>/<trial>/camera_N.mp4            1280x720, 40 Hz
    <video_root>/videos*/<participant>/<trial>/camera_N_timestamps.csv frame_index, ISO timestamp
    <video_root>/metadata/metadata/<participant>.yaml                  height (m), weight, gender

Four USB cameras (0, 2, 4, 6) in two facing stereo pairs 5.2 m apart, 0.8 m within a
pair, 1.1 m high; world Z up. The rig is recalibrated per session and cameras 4 and 6
swap places between sessions, so the gold is per participant. Each participant walks
a circle (CircularWalking, 65-130 s) and a straight line (StraightWalking, ~8 s).

The cameras are not hardware-synchronised: each has software timestamps. Frame counts
are identical and start/end times agree within ~20-40 ms, so there is no drift; the
videos are re-cut here by picking, for every timestamp of camera 0, the nearest frame
of each other camera -- dataset information only, at most one frame (25 ms) of
correction.

Usage::

    python -m humancalib.evaluation.comfi prepare --cam_root <E:/.../cam_params> \\
        --video_root <E:/.../Toulouse> --participant 1012 --trial CircularWalking --out <work>/comfi_1012_circ
"""
import argparse
import csv
import datetime
import glob
import json
import os

import numpy as np

from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation.rig import Camera, write_pose2sim_toml

log = get_logger(__name__)

CAMERAS = (0, 2, 4, 6)
UP = [0.0, 0.0, 1.0]
FPS = 40.0
MAX_MISMATCH_S = 0.030          # a frame farther than this from the reference instant is not a match


def read_intrinsics(path):
    """(K, dist[5], reproj_px) from an OpenCV FileStorage yaml."""
    import cv2
    fs = cv2.FileStorage(path, cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        raise FileNotFoundError(path)
    K = fs.getNode("K").mat()
    dist = fs.getNode("D").mat().ravel()
    reproj = fs.getNode("reproj").real() if not fs.getNode("reproj").empty() else float("nan")
    fs.release()
    return np.asarray(K, float), np.asarray(dist, float), reproj


def read_extrinsics(path):
    """(R_w2c, t_w2c, rms) from a cam_to_world yaml, whose R and t are camera -> world."""
    import yaml
    with open(path) as f:
        e = yaml.safe_load(f)["camera_extrinsics"]
    if not str(e.get("frame_from", "")).startswith("camera") or e.get("frame_to") != "world":
        raise ValueError(f"{path}: expected a camera -> world transform, got {e.get('frame_from')} -> {e.get('frame_to')}")
    R_c2w = np.asarray(e["rotation_matrix"], float)
    C = np.asarray(e["translation_vector"], float)
    if not np.isclose(np.linalg.det(R_c2w), 1.0, atol=1e-3):
        raise ValueError(f"{path}: det(R) = {np.linalg.det(R_c2w):.4f}, not a rotation")
    R = R_c2w.T
    return R, -R @ C, float(e.get("rms_error", float("nan")))


def read_rig(cam_root, participant, size=(1280.0, 720.0)):
    """The 4 gold cameras of one participant's session, named camera_N like the videos."""
    cameras = []
    for n in CAMERAS:
        K, dist, _ = read_intrinsics(os.path.join(cam_root, str(participant), "intrinsics", f"camera_{n}_intrinsics.yaml"))
        R, t, _ = read_extrinsics(os.path.join(cam_root, str(participant), "extrinsics", "cam_to_world",
                                               f"camera_{n}", f"camera_{n}_extrinsics.yaml"))
        cameras.append(Camera(name=f"camera_{n}", size=size, K=K, dist=dist, R=R, t=t))
    return cameras


def stature(video_root, participant):
    import yaml
    with open(os.path.join(video_root, "metadata", "metadata", f"{participant}.yaml")) as f:
        return float(yaml.safe_load(f)["height"])


def trial_dir(video_root, participant, trial):
    hits = glob.glob(os.path.join(video_root, "videos*", str(participant), trial))
    if not hits:
        raise FileNotFoundError(os.path.join(video_root, "videos*", str(participant), trial))
    return hits[0]


def read_timestamps(path):
    """Seconds (float) per frame index, in file order."""
    with open(path) as f:
        rows = list(csv.DictReader(f))
    return np.array([datetime.datetime.fromisoformat(r["timestamp"]).timestamp() for r in rows])


def align(ts_ref, ts_other, max_mismatch=MAX_MISMATCH_S):
    """For every reference instant, the index of the nearest frame of the other camera,
    or -1 when none lies within `max_mismatch`. Monotonic by construction (sorted search)."""
    j = np.searchsorted(ts_other, ts_ref)
    lo = np.clip(j - 1, 0, len(ts_other) - 1)
    hi = np.clip(j, 0, len(ts_other) - 1)
    pick = np.where(np.abs(ts_other[hi] - ts_ref) < np.abs(ts_other[lo] - ts_ref), hi, lo)
    ok = np.abs(ts_other[pick] - ts_ref) <= max_mismatch
    return np.where(ok, pick, -1)


MAX_FRAMES = 1000               # 25 s at 40 Hz: more frames do not improve the calibration and cost minutes


def common_window(ts, max_frames=MAX_FRAMES):
    """{camera: frame indices} of the longest run of reference frames every camera matches,
    cut to its first `max_frames`. ts: {camera: timestamps}; the reference is the first camera."""
    ref = CAMERAS[0]
    idx = {ref: np.arange(len(ts[ref]))}
    good = np.ones(len(ts[ref]), bool)
    for n in CAMERAS[1:]:
        idx[n] = align(ts[ref], ts[n])
        good &= idx[n] >= 0
    if not good.any():
        raise ValueError("no frame is seen by all cameras within the tolerance")
    best, run = (0, 0), 0
    for i, g in enumerate(np.append(good, False)):
        run = run + 1 if g else 0
        if run > best[0]:
            best = (run, i - run + 1)
    length, first = best
    if max_frames:
        length = min(length, int(max_frames))
    sel = np.arange(first, first + length)
    return {n: idx[n][sel] for n in CAMERAS}


def cut_videos(src_dir, dest, frames):
    """Re-cut every camera to the frames listed in `frames` (monotonic indices), MJPEG at FPS."""
    import cv2
    os.makedirs(dest, exist_ok=True)
    for n in CAMERAS:
        cap = cv2.VideoCapture(os.path.join(src_dir, f"camera_{n}.mp4"))
        if not cap.isOpened():
            raise FileNotFoundError(os.path.join(src_dir, f"camera_{n}.mp4"))
        w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        out = cv2.VideoWriter(os.path.join(dest, f"camera_{n}.avi"), cv2.VideoWriter_fourcc(*"MJPG"), FPS, (w, h))
        wanted = list(frames[n])
        k, cur, frame = 0, -1, None
        while k < len(wanted):
            target = wanted[k]
            while cur < target:
                ok, frame = cap.read()
                if not ok:
                    raise ValueError(f"camera_{n}: video ends at frame {cur}, frame {target} wanted")
                cur += 1
            out.write(frame)              # a repeated index writes the same frame twice: keeps cameras aligned
            k += 1
        cap.release()
        out.release()
    return dest


def prepare(cam_root, video_root, participant, trial, out, max_frames=MAX_FRAMES):
    inp, gold = os.path.join(out, "input"), os.path.join(out, "gold")
    os.makedirs(inp, exist_ok=True)
    os.makedirs(gold, exist_ok=True)
    cameras = read_rig(cam_root, participant)
    src = trial_dir(video_root, participant, trial)
    ts = {n: read_timestamps(os.path.join(src, f"camera_{n}_timestamps.csv")) for n in CAMERAS}
    frames = common_window(ts, max_frames)
    video_dir = cut_videos(src, os.path.join(out, "_videos"), frames)
    write_pose2sim_toml(cameras, os.path.join(inp, "Calib_scene.toml"), extrinsics=False)
    write_pose2sim_toml(cameras, os.path.join(gold, "Calib_gold.toml"), extrinsics=True)
    n_ref = len(frames[CAMERAS[0]])
    shifts = {f"camera_{n}": int(np.median(frames[n] - frames[CAMERAS[0]])) for n in CAMERAS}
    meta = {"dataset": "COMFI", "participant": str(participant), "trial": trial,
            "stature_m": stature(video_root, participant), "video_dir": video_dir, "fps": FPS,
            "frames": n_ref, "first_reference_frame": int(frames[CAMERAS[0]][0]),
            "median_frame_shift_vs_camera_0": shifts,
            "world": "motion-capture frame, Z up, metres", "up": UP,
            "calibration": os.path.join(cam_root, str(participant))}
    with open(os.path.join(gold, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Prepared COMFI {participant}/{trial} in {out}: {n_ref} frames at {FPS:g} Hz, "
             f"stature {meta['stature_m']} m, shifts {shifts}")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--cam_root", required=True, help="folder holding <participant>/intrinsics and extrinsics")
    p.add_argument("--video_root", required=True, help="folder holding videos*/ and metadata/")
    p.add_argument("--participant", required=True)
    p.add_argument("--trial", default="CircularWalking")
    p.add_argument("--out", required=True)
    p.add_argument("--max_frames", type=int, default=MAX_FRAMES, help="0 = whole common window")
    args = parser.parse_args(argv)
    prepare(args.cam_root, args.video_root, args.participant, args.trial, args.out, args.max_frames)
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
