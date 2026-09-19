"""Every person detected in every frame, kept beside the selected one.

Pose extraction keeps one person per frame per camera: the largest detection
(get_best_person in both extractors). That rule has no memory and no notion of
the other cameras, so a bystander standing close to one camera wins in that
camera for the whole trial -- BioCV P06 and P10, camera 08. Geometric
re-selection (humancalib.pipeline.reselect_person) fixes this after a first
calibration, and needs every detection to choose from: this file stores them.

One compressed .npz per camera, next to the pose JSONs::

    <subset>/candidates/A001_P001_G001_C00N.npz

    frames   (F,)       absolute frame numbers, one per processed frame
    status   (F,)       0 = processed, 1 = dropped by sidecar, 2 = too dark
    owner    (P,)       row of `frames` each detection belongs to (sorted)
    box      (P, B)     detector box, in the extractor's own convention
    pose2d   (P, J, 2)  raw keypoints -- before undistortion or smoothing
    score2d  (P, J)     per-joint confidence (RTMPose only)
    pose3d   (P, J, 3)  camera-frame 3D joints (MeTRAbs only)
    imshape  (2,)       image height, width

The selection rules are here too, so extraction and re-selection cannot drift
apart: `largest` reproduces get_best_person exactly, and `plausible` is the
filter get_best_person and the MeTRAbs extractor apply to their choice.
"""
import os

import numpy as np

STATUS_OK, STATUS_DROPPED, STATUS_DARK = 0, 1, 2
CANDIDATES_DIRNAME = "candidates"


def candidates_path(output_dir, subset, base_name):
    stem = os.path.splitext(base_name)[0]
    return os.path.join(output_dir, subset, CANDIDATES_DIRNAME, f"{stem}.npz")


def save_candidates(path, frames, status, detections, imshape):
    """detections: one entry per frame, None or a dict of arrays with a leading
    person axis -- box (n, B), pose2d (n, J, 2), and optionally score2d (n, J)
    and pose3d (n, J, 3)."""
    frames = np.asarray(frames, dtype=np.int64)
    owner, parts = [], {"box": [], "pose2d": [], "score2d": [], "pose3d": []}
    for row, det in enumerate(detections):
        if det is None or len(det["box"]) == 0:
            continue
        n = len(det["box"])
        owner.extend([row] * n)
        for key in parts:
            if det.get(key) is not None:
                parts[key].append(np.asarray(det[key], dtype=np.float32).reshape((n,) + np.shape(det[key])[1:]))
    arrays = {"frames": frames, "status": np.asarray(status, dtype=np.int8),
              "owner": np.asarray(owner, dtype=np.int64), "imshape": np.asarray(imshape, dtype=np.int64)}
    for key, chunks in parts.items():
        if chunks:
            arrays[key] = np.concatenate(chunks)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez_compressed(path, **arrays)


def load_candidates(path):
    """The saved arrays, plus `start` (F+1,) so frame row i owns detections start[i]:start[i+1]."""
    with np.load(path) as z:
        c = {k: z[k] for k in z.files}
    c["start"] = np.searchsorted(c["owner"], np.arange(len(c["frames"]) + 1))
    return c


def box_areas(engine, box):
    box = np.asarray(box, dtype=float).reshape(len(box), -1)
    if engine == "metrabs":                       # x, y, width, height, confidence
        return box[:, 2] * box[:, 3]
    return (box[:, 2] - box[:, 0]) * (box[:, 3] - box[:, 1])   # x1, y1, x2, y2


def plausible(engine, box, pose2d, imshape):
    """(n,) bool: detections the extractor would accept if it picked them.

    MeTRAbs rejects a box under 0.5 % of the image and a skeleton whose joints
    collapse to one spot; RTMPose applies no filter."""
    n = len(box)
    if engine != "metrabs" or n == 0:
        return np.ones(n, dtype=bool)
    area_ok = box_areas(engine, box) >= 0.005 * float(imshape[0]) * float(imshape[1])
    spread_ok = np.std(np.asarray(pose2d, dtype=float), axis=1).mean(axis=1) >= 20
    return area_ok & spread_ok


def largest(engine, box, pose2d, imshape):
    """Index of the detection get_best_person keeps, or -1 for none."""
    if len(box) == 0:
        return -1
    i = int(np.argmax(box_areas(engine, box)))
    if engine == "metrabs" and not plausible(engine, box[i:i + 1], pose2d[i:i + 1], imshape)[0]:
        return -1
    return i
