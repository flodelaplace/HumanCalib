"""MeTRAbs pose post-processing and file writing, without TensorFlow.

Everything that happens to one camera's selected poses after inference:
Savitzky-Golay smoothing, undistortion of the 2D keypoints, per-joint scores,
the Halpe26 mapping, and the 2d_joint / 3d_joint / 2d_joint_halpe26 files.
Moved out of metrabs_inference, verbatim, so geometric person re-selection
(humancalib.pipeline.reselect_person) rewrites those files through exactly the
same code, in an environment that need not import TensorFlow.
"""
import json
import os

import cv2
import numpy as np

from humancalib.core.log import get_logger
log = get_logger(__name__)

N_FULL_JOINTS = 87


BML87_TO_HALPE26 = {
    0:  67,  # Nose      <- head
    1:  5,   # LEye      <- lfronthead
    2:  36,  # REye      <- rfronthead
    3:  6,   # LEar      <- lbackhead
    4:  37,  # REar      <- rbackhead
    5:  76,  # LShoulder <- lsho
    6:  84,  # RShoulder <- rsho
    7:  72,  # LElbow    <- lelb
    8:  80,  # RElbow    <- relb
    9:  77,  # LWrist    <- lwri
    10: 85,  # RWrist    <- rwri
    11: 73,  # LHip      <- lhip
    12: 81,  # RHip      <- rhip
    13: 75,  # LKnee     <- lkne
    14: 83,  # RKnee     <- rkne
    15: 71,  # LAnkle    <- lank
    16: 79,  # RAnkle    <- rank
    17: 67,  # Head      <- head
    18: 0,   # Neck      <- backneck
    19: 68,  # MidHip    <- mhip
    20: 23,  # LBigToe   <- ltoe
    21: 54,  # RBigToe   <- rtoe
    22: 22,  # LSmallToe <- lfifthmetatarsal
    23: 53,  # RSmallToe <- rfifthmetatarsal
    24: 21,  # LHeel     <- lhee
    25: 52,  # RHeel     <- rhee
}


def undistort_points(pts_2d, K, dist_coeffs):
    """Undistort 2D points and reproject to pixel coords (pinhole).

    Args:
        pts_2d: (N, 2) array of 2D points in distorted pixel space
        K: (3, 3) intrinsic matrix
        dist_coeffs: distortion coefficients (k1, k2, p1, p2, ...)
    Returns:
        (N, 2) array of undistorted 2D points in pixel space
    """
    if dist_coeffs is None or not np.any(dist_coeffs):
        return pts_2d
    pts = pts_2d.reshape(-1, 1, 2).astype(np.float64)
    undist = cv2.undistortPoints(pts, K, dist_coeffs, P=K)
    return undist.reshape(-1, 2).astype(np.float32)


def bml87_to_halpe26(kp_bml87):
    """Convert bml_movi_87 keypoints to Halpe26 format."""
    n_dim = kp_bml87.shape[-1]
    kp_out = np.zeros((26, n_dim), dtype=np.float32)
    for h_idx, bml_idx in BML87_TO_HALPE26.items():
        kp_out[h_idx] = kp_bml87[bml_idx]
    return kp_out


def smooth_keypoints(poses_list, window=11, polyorder=3):
    """Apply Savitzky-Golay temporal smoothing to a list of keypoint arrays.

    Args:
        poses_list: list of (N_joints, D) arrays (one per frame)
        window: filter window size (must be odd, >= polyorder+2)
        polyorder: polynomial order for the filter
    Returns:
        list of smoothed arrays (same shapes)
    """
    from scipy.signal import savgol_filter

    if len(poses_list) < window:
        return poses_list  # not enough frames to smooth

    arr = np.array(poses_list)  # (N_frames, N_joints, D)
    n_frames, n_joints, n_dim = arr.shape

    # Smooth each joint coordinate independently
    for j in range(n_joints):
        for d in range(n_dim):
            arr[:, j, d] = savgol_filter(arr[:, j, d], window, polyorder)

    return [arr[i] for i in range(n_frames)]


def save_json(filepath, frame_indices, poses, scores):
    """Save poses in the JSON format expected by the calibration pipeline."""
    data = []
    for fidx, pose, score in zip(frame_indices, poses, scores):
        data.append({
            "frame_index": int(fidx),
            "skeleton": [{
                "pose": pose.flatten().tolist(),
                "score": score.tolist(),
            }]
        })
    with open(filepath, "w") as f:
        json.dump({"data": data}, f, indent=2, ensure_ascii=True)


def save_skeleton_w(filepath, frame_indices, poses3d):
    """Save world skeleton JSON (using first camera's 3D as reference)."""
    skeleton = np.array(poses3d, dtype=np.float64)  # (N, N_joints, 3)
    out = {
        "frame_indices": [int(f) for f in frame_indices],
        "skeleton": skeleton.tolist(),
    }
    with open(filepath, "w") as f:
        json.dump(out, f, indent=2, ensure_ascii=True)


def write_camera_outputs(frame_indices, poses3d_raw, poses2d_raw, confidences, K, dist,
                         img_w, img_h, out_2d_dir, out_3d_dir, out_halpe26_dir, base_name):
    """Post-process one camera's selected poses and write its three JSON files.

    poses3d_raw / poses2d_raw: one (87, 3) / (87, 2) array per frame, or None
    where no person was kept. Modified in place by the smoothing, as before.
    Returns the per-frame 87-joint 3D list, which the extractor keeps for the
    world-skeleton placeholder.
    """
    # Temporal smoothing (Savitzky-Golay) to reduce frame-to-frame jitter
    # Only smooth frames where a person was detected
    valid_3d = [p for p in poses3d_raw if p is not None]
    valid_2d = [p for p in poses2d_raw if p is not None]
    if len(valid_3d) > 11:
        smoothed_3d = smooth_keypoints(valid_3d)
        smoothed_2d = smooth_keypoints(valid_2d)
        vi = 0
        for i in range(len(poses3d_raw)):
            if poses3d_raw[i] is not None:
                poses3d_raw[i] = smoothed_3d[vi]
                poses2d_raw[i] = smoothed_2d[vi]
                vi += 1
        log.info(f"  Applied Savitzky-Golay smoothing ({len(valid_3d)} frames)")

    # Convert to full 87-joint format, Halpe26 for scaling compatibility
    full87_2d_list = []
    full87_3d_list = []
    halpe26_2d_list = []
    scores_2d_list = []
    scores_3d_list = []
    scores_halpe26_list = []

    N_FULL_JOINTS = 87

    has_distortion = np.any(dist != 0)
    if has_distortion:
        log.info(f"  Undistorting 2D keypoints (dist={dist[:4]}...)")


    for p3d, p2d, conf in zip(poses3d_raw, poses2d_raw, confidences):
        if p3d is not None:
            # Undistort raw 2D keypoints (all 87) before saving
            if has_distortion:
                p2d = undistort_points(p2d, K, dist)

            # Keep all 87 joints directly (no subsetting)
            kp_2d = p2d.astype(np.float32)   # (87, 2)
            kp_3d = p3d.astype(np.float32)   # (87, 3)
            # Map to Halpe26 (for scale_scene.py backward compat)
            kp_2d_halpe26 = bml87_to_halpe26(p2d)

            # Per-joint 2D confidence scoring (all 87 joints)
            s2d = np.full(N_FULL_JOINTS, conf, dtype=np.float32)

            # Penalize 2D joints outside image bounds
            margin = 10
            oob = ((kp_2d[:, 0] < margin) | (kp_2d[:, 0] > img_w - margin) |
                   (kp_2d[:, 1] < margin) | (kp_2d[:, 1] > img_h - margin))
            s2d[oob] *= 0.1

            # 3D confidence: bbox conf only
            s3d = np.full(N_FULL_JOINTS, conf, dtype=np.float32)
            s_halpe26 = np.full(26, conf, dtype=np.float32)
        else:
            # No detection
            kp_2d = np.zeros((N_FULL_JOINTS, 2), dtype=np.float32)
            kp_3d = np.zeros((N_FULL_JOINTS, 3), dtype=np.float32)
            kp_2d_halpe26 = np.zeros((26, 2), dtype=np.float32)
            s2d = np.zeros(N_FULL_JOINTS, dtype=np.float32)
            s3d = np.zeros(N_FULL_JOINTS, dtype=np.float32)
            s_halpe26 = np.zeros(26, dtype=np.float32)

        full87_2d_list.append(kp_2d)
        full87_3d_list.append(kp_3d)
        halpe26_2d_list.append(kp_2d_halpe26)
        scores_2d_list.append(s2d)
        scores_3d_list.append(s3d)
        scores_halpe26_list.append(s_halpe26)

    # Save 2D (full 87-joint bml_movi_87)
    save_json(
        os.path.join(out_2d_dir, base_name),
        frame_indices, full87_2d_list, scores_2d_list
    )
    log.info(f"  Saved {len(frame_indices)} bml_movi_87 2D frames (87 joints) -> {out_2d_dir}/{base_name}")

    # Save 3D (full 87-joint bml_movi_87)
    save_json(
        os.path.join(out_3d_dir, base_name),
        frame_indices, full87_3d_list, scores_3d_list
    )
    log.info(f"  Saved {len(frame_indices)} bml_movi_87 3D frames (87 joints) -> {out_3d_dir}/{base_name}")

    # Save Halpe26 2D (for scale_scene.py)
    save_json(
        os.path.join(out_halpe26_dir, base_name),
        frame_indices, halpe26_2d_list, scores_halpe26_list
    )
    log.info(f"  Saved {len(frame_indices)} Halpe26 2D frames -> {out_halpe26_dir}/{base_name}")
    return full87_3d_list
