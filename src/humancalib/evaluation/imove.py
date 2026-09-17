"""IMOVE-23: gold calibration reader and session preparation.

Layout of the dataset, as used here::

    <root>/Demographics/IMOVE23_Demographics.xlsx            Height_cm per subject
    <root>/Videos/Timing_IMOVE23.xlsx                        walking passes (see below)
    <root>/Videos/Calibration_files/Subject_N_calibration.txt   Qualisys XML
    <root>/Videos/Compressed_RGB_videos/Subject_N/t1_walking/
        t1_walking_001-Camera SS (Cxxxxx).mp4                 10 cameras, 100 Hz
        Rotated_t1_walking_001-Camera SS (Cxxxxx).mp4         the two portrait ones, upright

One walking trial per subject, 2 min 11 s long. Three things decide this reader:

* the calibration is Qualisys XML: `<transform x y z r11..r33>` is world-to-camera,
  R and t with t in millimetres, so the optical centre is -R^T t. Checked on
  subject 2: the ten centres sit 2.16 to 2.56 m high around the origin, and on
  the eight unrotated cameras the image's downward axis points down the world
  (R[1].Z between -0.86 and -0.94). Distortion is radialDistortion1..3 and
  tangentalDistortion1..2 (sic), i.e. OpenCV's k1 k2 p1 p2 k3.
* cameras 22 and 23 are mounted on their side (`viewrotation` 270 and 90). The
  dataset ships them upright as Rotated_*.mp4, but the calibration describes the
  sensor, so K, the distortion and R are rotated here to match the upright image.
  The direction is not read from `viewrotation`: of the two quarter turns, the one
  kept is the one that makes the image's downward axis point down the world.
  That gives counter-clockwise for camera 22 and clockwise for 23, the opposite
  of what the attribute suggests -- which Mesh2Sim had also found empirically.
* `Timing_IMOVE23.xlsx` lists, per group of cameras, the frames where a camera
  sees the subject walk towards it -- written for single-camera use. Its windows
  never overlap between groups, yet eight of the ten cameras do see the subject
  in between. For calibration the window is one out-and-back walk: from the
  first frame of pass 1 to the last frame of pass 2, all groups, gap included.

Usage::

    python -m humancalib.evaluation.imove prepare --root <IMOVE-23> --subject 2 \\
        --out <work>/imove_subject2
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

import numpy as np

from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation.rig import Camera, write_pose2sim_toml

log = get_logger(__name__)

UP = [0.0, 0.0, 1.0]
TRIAL = "t1_walking"


def _attr(text, key):
    m = re.search(rf'\b{key}="([-\d.eE+]+)"', text)
    if m is None:
        raise ValueError(f"attribute {key} missing")
    return float(m.group(1))


def parse_calibration(text):
    """[(serial, viewrotation, Camera)] from a Qualisys calibration XML, unrotated."""
    out = []
    blocks = re.findall(r'<camera active="(\d)" serial="(\d+)" viewrotation="(\d+)".*?'
                        r'<transform ([^/]*)/>.*?<intrinsic ([^/]*)/>', text, re.S)
    for active, serial, viewrotation, tr, intr in blocks:
        R = np.array([[_attr(tr, f"r{i}{j}") for j in (1, 2, 3)] for i in (1, 2, 3)])
        t = np.array([_attr(tr, "x"), _attr(tr, "y"), _attr(tr, "z")]) / 1000.0
        K = np.array([[_attr(intr, "focalLengthU"), 0.0, _attr(intr, "centerPointU")],
                      [0.0, _attr(intr, "focalLengthV"), _attr(intr, "centerPointV")],
                      [0.0, 0.0, 1.0]])
        dist = np.array([_attr(intr, "radialDistortion1"), _attr(intr, "radialDistortion2"),
                         _attr(intr, "tangentalDistortion1"), _attr(intr, "tangentalDistortion2"),
                         _attr(intr, "radialDistortion3")])
        size = (_attr(intr, "sensorMaxU"), _attr(intr, "sensorMaxV"))
        out.append((serial, int(viewrotation), Camera(name=f"Cam{serial}", size=size, K=K, dist=dist, R=R, t=t)))
    return out


def rotate_camera(cam, clockwise):
    """The same camera seen through its image turned a quarter turn.

    Clockwise, pixel (u, v) of a W x H image becomes (H-1-v, u); counter-clockwise
    it becomes (v, W-1-u). The projection matrix picks up that affine map, which
    splits into a new K and a rotation about the optical axis applied to R and t.
    The tangential coefficients turn with the normalised coordinates; the radial
    ones are unchanged."""
    W, H = cam.size
    fx, fy, cx, cy = cam.K[0, 0], cam.K[1, 1], cam.K[0, 2], cam.K[1, 2]
    k1, k2, p1, p2, k3 = cam.dist
    if clockwise:
        K = np.array([[fy, 0.0, H - 1 - cy], [0.0, fx, cx], [0.0, 0.0, 1.0]])
        Rz = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        dist = np.array([k1, k2, p2, -p1, k3])
    else:
        K = np.array([[fy, 0.0, cy], [0.0, fx, W - 1 - cx], [0.0, 0.0, 1.0]])
        Rz = np.array([[0.0, 1.0, 0.0], [-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
        dist = np.array([k1, k2, -p2, p1, k3])
    return Camera(name=cam.name, size=(H, W), K=K, dist=dist, R=Rz @ cam.R, t=Rz @ cam.t)


def upright(cam, up=UP):
    """The quarter turn of a side-mounted camera whose image comes out upright:
    its downward image axis must point down the world."""
    cw, ccw = rotate_camera(cam, True), rotate_camera(cam, False)
    up = np.asarray(up, dtype=float)
    return cw if cw.R[1] @ up < ccw.R[1] @ up else ccw


def read_rig(root, subject):
    """(cameras, rotated serials): the 10 gold cameras as they appear in the videos used."""
    path = os.path.join(root, "Videos", "Calibration_files", f"Subject_{subject}_calibration.txt")
    with open(path, errors="ignore") as f:
        parsed = parse_calibration(f.read())
    cameras, rotated = [], set()
    for serial, viewrotation, cam in parsed:
        if viewrotation % 180 == 90:
            cam = upright(cam)
            rotated.add(serial)
        cameras.append(cam)
    return cameras, rotated


def stature(root, subject):
    import pandas as pd
    d = pd.read_excel(os.path.join(root, "Demographics", "IMOVE23_Demographics.xlsx"))
    row = d[d["Subject"] == int(subject)]
    if row.empty or not np.isfinite(row["Height_cm"].iloc[0]):
        raise KeyError(f"no stature for subject {subject}")
    return float(row["Height_cm"].iloc[0]) / 100.0


def walk_window(rows, subject, passes=(1, 2)):
    """(first, last) frame of one out-and-back walk: all camera groups, gap included.
    rows: records with keys Sujet, Aller num, Début, Fin."""
    sel = [r for r in rows if int(r["Sujet"]) == int(subject) and int(r["Aller num"]) in passes]
    if not sel:
        raise KeyError(f"subject {subject}: passes {passes} not in the timing table")
    return int(min(r["Début"] for r in sel)), int(max(r["Fin"] for r in sel))


def read_timing(root):
    import pandas as pd
    d = pd.read_excel(os.path.join(root, "Videos", "Timing_IMOVE23.xlsx")).dropna(subset=["Sujet", "Aller num"])
    return d.to_dict("records")


def video_path(root, subject, serial, rotated):
    """The take number varies between subjects (_001 on subject 2, _002 on 3, 9, 11, 13),
    so any take is accepted -- but only one, since the timing table has one per subject."""
    folder = os.path.join(root, "Videos", "Compressed_RGB_videos", f"Subject_{subject}", TRIAL)
    pattern = f"{'Rotated_' if rotated else ''}{TRIAL}_*-Camera {serial} (*).mp4"
    hits = sorted(glob.glob(os.path.join(folder, glob.escape(pattern).replace(r"[*]", "*"))))
    if not hits:
        raise FileNotFoundError(os.path.join(folder, pattern))
    if len(hits) > 1:
        raise ValueError(f"several takes for camera {serial} of subject {subject}: {hits}")
    return hits[0]


def cut_videos(root, subject, cameras, rotated, first, last, dest, step=2, fps=100.0):
    """Frames first..last of every camera, one in `step`, selected by number."""
    os.makedirs(dest, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg") or os.path.join(os.path.dirname(sys.executable), "ffmpeg")
    out_fps = fps / step
    for cam in cameras:
        serial = cam.name[3:]
        src = video_path(root, subject, serial, serial in rotated)
        out = os.path.join(dest, f"{cam.name}.avi")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src,
                        "-vf", f"select='between(n\\,{first}\\,{last})*not(mod(n-{first}\\,{step}))',"
                               f"setpts=N/({out_fps:g}*TB)",
                        "-r", f"{out_fps:g}", "-c:v", "mjpeg", "-q:v", "3", "-pix_fmt", "yuvj420p", out],
                       check=True)
    return dest, out_fps


def prepare(root, subject, out, passes=(1, 2), step=2):
    inp, gold = os.path.join(out, "input"), os.path.join(out, "gold")
    os.makedirs(inp, exist_ok=True)
    os.makedirs(gold, exist_ok=True)
    cameras, rotated = read_rig(root, subject)
    first, last = walk_window(read_timing(root), subject, passes)
    video_dir, out_fps = cut_videos(root, subject, cameras, rotated, first, last,
                                    os.path.join(out, "_videos"), step=step)
    write_pose2sim_toml(cameras, os.path.join(inp, "Calib_scene.toml"), extrinsics=False)
    write_pose2sim_toml(cameras, os.path.join(gold, "Calib_gold.toml"), extrinsics=True)
    meta = {"dataset": "IMOVE-23", "participant": f"Subject_{subject}", "trial": TRIAL,
            "stature_m": stature(root, subject), "video_dir": video_dir,
            "window": [first, last], "passes": list(passes), "fps": out_fps,
            "rotated_cameras": sorted(rotated), "world": "Qualisys frame, Z up, metres", "up": UP}
    with open(os.path.join(gold, "meta.json"), "w") as f:
        json.dump(meta, f, indent=2)
    log.info(f"Prepared IMOVE subject {subject} in {out}: frames {first}-{last} at {out_fps:g} Hz, "
             f"rotated {sorted(rotated)}, stature {meta['stature_m']} m")
    return meta


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--root", required=True)
    p.add_argument("--subject", required=True, type=int)
    p.add_argument("--out", required=True)
    p.add_argument("--passes", type=int, nargs="+", default=[1, 2])
    p.add_argument("--step", type=int, default=2, help="keep one frame in step (2: 100 Hz -> 50 Hz)")
    args = parser.parse_args(argv)
    prepare(args.root, args.subject, args.out, tuple(args.passes), args.step)
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
