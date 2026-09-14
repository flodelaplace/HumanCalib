"""The world-skeleton file that maps array indices back to video frame numbers.

Formerly a Python heredoc in calibrate.sh (step 2.5). When a session is cropped
with --start_frame/--end_frame, the pose arrays start at index 0 but the frames
they came from start at start_frame. This file records that correspondence as
absolute frame numbers, which --ref_frame and map_video_frames_to_indices rely
on.

The skeleton coordinates are nulls: nothing downstream reads them
(load_eldersim returns them as p3d_w, which the calibration discards). Only
``frame_indices`` matters, and it must use the same absolute numbering as the
pose files -- see B7 in docs/REFACTOR_PLAN.md for what a mismatch costs.
"""
import glob
import json
import os

DEFAULT_JOINTS = 25


def detect_joint_count(output_dir, subset):
    """Joints per frame in the extracted 2D poses (25 RTMPose, 26/87 MeTRAbs)."""
    files = sorted(glob.glob(os.path.join(output_dir, subset, "2d_joint", "*.json")))
    if not files:
        return DEFAULT_JOINTS
    with open(files[0]) as f:
        return len(json.load(f)["data"][0]["skeleton"][0]["score"])


def write_frame_mapping(output_dir, subset, gid, start_frame, end_frame):
    """Write skeleton_w_G<gid>.json for frames start_frame..end_frame inclusive."""
    start_frame, end_frame = int(start_frame), int(end_frame)
    if end_frame < start_frame:
        raise ValueError(f"end_frame {end_frame} is before start_frame {start_frame}")

    n_frames = end_frame - start_frame + 1
    n_joints = detect_joint_count(output_dir, subset)
    doc = {
        "frame_indices": list(range(start_frame, end_frame + 1)),
        "skeleton": [[[None, None, None] for _ in range(n_joints)] for _ in range(n_frames)],
    }
    path = os.path.join(output_dir, subset, f"skeleton_w_G{int(gid):03d}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(doc, f)
    return path
