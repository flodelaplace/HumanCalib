"""
scale_scene.py
--------------
Scales and reorients a calibrated scene to a metric, gravity-aligned coordinate system.

This script performs two main operations:
1.  **Reorientation**: It defines a new coordinate system by fitting a plane to
    the person's feet keypoints to define the ground (XZ plane) and its normal
    as the vertical axis (Y-axis).
2.  **Scaling**: It scales the entire scene to metric units (meters) based on the
    person's real-world height.

The final transformed calibration is saved to a new JSON file and can be exported
to a TOML file.

Usage:
    python scale_scene.py \\
        --prefix ./data/A001_P003_G001 \\
        --calib linear_1_0_ba \\
        --height 1.80 \\
        --frame_idx 150
"""

import argparse
import json
import os
import sys
import glob

import numpy as np

from humancalib.core import load_poses
from humancalib.core.geometry import triangulate_dlt
from humancalib.core.session import session_ids
from humancalib.core.videos import camera_names
from humancalib.postprocessing.evaluate_calibration import export_to_toml
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)

# Keypoint indices in Halpe26 (used with RTMPose)
HALPE26_HEAD = 17
HALPE26_L_HEEL = 24
HALPE26_R_HEEL = 25
HALPE26_L_BIG_TOE = 20
HALPE26_R_BIG_TOE = 21
HALPE26_L_SMALL_TOE = 22
HALPE26_R_SMALL_TOE = 23

# Keypoint indices in Calib26 / MeTRAbs format
CALIB26_HEAD = 0
CALIB26_L_HEEL = 22
CALIB26_R_HEEL = 23
CALIB26_L_TOE = 24
CALIB26_R_TOE = 25
CALIB26_L_FOO = 20
CALIB26_R_FOO = 21

# Keypoint indices in bml_movi_87 (full MeTRAbs skeleton)
BML87_HEAD = 67
BML87_L_HEEL = 21
BML87_R_HEEL = 52
BML87_L_TOE = 23
BML87_R_TOE = 54
BML87_L_FOO = 78
BML87_R_FOO = 86
BML87_L_FIFTHMET = 22
BML87_R_FIFTHMET = 53

# Thigh (hip-knee) + shank (knee-ankle) as a fraction of stature, Drillis & Contini
# (Winter, Biomechanics and Motor Control of Human Movement, 4th ed., fig. 4.1); de Leva
# (J Biomech 1996, joint centres) gives 0.492 for men. Hip to shoulder: 0.818 - 0.530.
# Fixed from the literature, not fitted to any evaluation data.
LEG_RATIO = 0.245 + 0.246
TRUNK_RATIO = 0.288

# (hip, knee, ankle) per side, for each joint layout.
LEGS = {
    "bml_movi_87": ((73, 75, 71), (81, 83, 79)),
    "calib26": ((14, 16, 18), (15, 17, 19)),
    "halpe26": ((11, 13, 15), (12, 14, 16)),
}
# (mid-hip, neck) of the layouts whose scale adds the trunk to the legs. Only Halpe26 (RTMPose):
# its hip keypoints sit about 85 mm in front of the joint centre, which lengthens the thigh
# and shortens the trunk by opposite amounts. Legs alone overestimated RTMPose scale by +5 %
# on BioCV, legs + trunk -1.8 %; MeTRAbs, whose hips are joint centres, keeps legs alone
# (+1 to +2 %, where legs + trunk gives -2 to -3 %). docs/EVALUATION_PROTOCOL.md, journal.
TRUNK = {"halpe26": (19, 18)}


def segment_scale(p2d_all, s2d_all, K, R_w2c, t_w2c, legs, height, conf_threshold=0.5, step=2, trunk=None):
    """Metres per calibration unit, from segment lengths over the whole sequence.

    The head-height method measures one frame, from a head keypoint that is not
    the top of the skull, on a person who may be mid-stride: every bias shortens
    the measured height, and on BioCV it overestimated scale by about 11 %.
    Segment lengths do not depend on posture and are measured on every frame:
    hip, knee and ankle are triangulated by camera consensus, the median thigh
    and shank lengths are summed, and compared with LEG_RATIO x stature. With
    `trunk` = (mid-hip, neck), the median trunk length is added and compared with
    (LEG_RATIO + TRUNK_RATIO) x stature.
    Returns None when too few frames could be triangulated.
    """
    from humancalib.pipeline.reselect_person import robust_triangulate

    C = p2d_all.shape[0]
    Ps = np.array([K[c] @ np.hstack([R_w2c[c], np.asarray(t_w2c[c]).reshape(3, 1)]) for c in range(C)])
    joints = [j for side in legs for j in side] + (list(trunk) if trunk else [])
    thigh, shank, torso = [], [], []
    for f in range(0, p2d_all.shape[1], step):
        pts = p2d_all[:, f, joints, :]
        valid = s2d_all[:, f, joints] > conf_threshold
        X, used = robust_triangulate(pts, valid, Ps, 50.0, 5.0, 3)
        if used.sum() < 3:
            continue
        for side in range(2):
            hip, knee, ankle = X[3 * side], X[3 * side + 1], X[3 * side + 2]
            thigh.append(np.linalg.norm(hip - knee))
            shank.append(np.linalg.norm(knee - ankle))
        if trunk:
            torso.append(np.linalg.norm(X[6] - X[7]))
    thigh, shank, torso = np.asarray(thigh), np.asarray(shank), np.asarray(torso)
    if np.isfinite(thigh).sum() < 10 or np.isfinite(shank).sum() < 10:
        return None
    if not trunk:
        return height * LEG_RATIO / (np.nanmedian(thigh) + np.nanmedian(shank))
    if np.isfinite(torso).sum() < 10:
        return None
    return height * (LEG_RATIO + TRUNK_RATIO) / (np.nanmedian(thigh) + np.nanmedian(shank) + np.nanmedian(torso))


def walking_vertical(p2d_all, s2d_all, K, R_w2c, t_w2c, feet, head, ankles, conf_threshold=0.5,
                     step=2, stance_quantile=0.4):
    """Upward vertical in the calibration's world frame, from the whole walk.

    A single frame gives the vertical within 0.3 to 12 degrees depending on the
    frame chosen. Over the sequence, two facts are used:
    * the floor contains the walking direction, which the stance-phase foot
      keypoints determine well (they spread metres along it);
    * the body axis, head to mid-ankles, is vertical up to a sagittal lean,
      and the sagittal lean lies along the walking direction.
    So the median body axis, with its component along the walking direction
    removed, is the vertical. A plane fitted to the stance points alone is
    unstable: they span only a foot's width across the walk, less than the
    height differences between heel, toe and metatarsal keypoints.
    Stance frames are those where a foot keypoint moves less than its own
    `stance_quantile` speed quantile. Returns None when too little is seen.
    """
    from humancalib.pipeline.reselect_person import robust_triangulate

    C = p2d_all.shape[0]
    Ps = np.array([K[c] @ np.hstack([R_w2c[c], np.asarray(t_w2c[c]).reshape(3, 1)]) for c in range(C)])
    joints = list(feet) + [head] + list(ankles)
    nf = len(feet)
    frames = list(range(0, p2d_all.shape[1], step))
    X = np.full((len(frames), len(joints), 3), np.nan)
    for k, f in enumerate(frames):
        X[k], used = robust_triangulate(p2d_all[:, f, joints, :], s2d_all[:, f, joints] > conf_threshold,
                                        Ps, 50.0, 5.0, 3)
        if used.sum() < 3:
            X[k] = np.nan
    body = X[:, nf] - 0.5 * (X[:, nf + 1] + X[:, nf + 2])
    body = body[np.isfinite(body).all(axis=1)]
    if len(body) < 10:
        return None
    axis = np.median(body / np.linalg.norm(body, axis=1, keepdims=True), axis=0)
    axis /= np.linalg.norm(axis)

    foot = X[:, :nf]
    speed = np.full(foot.shape[:2], np.nan)
    speed[1:-1] = np.linalg.norm(foot[2:] - foot[:-2], axis=2) / 2
    with np.errstate(invalid="ignore"):
        stance = speed <= np.nanquantile(speed, stance_quantile, axis=0)[None]
    pts = foot[stance]
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(pts) < 10:
        return axis
    walk = np.linalg.svd(pts - pts.mean(axis=0), full_matrices=False)[2][0]
    up = axis - (axis @ walk) * walk
    return up / np.linalg.norm(up)


def get_3d_keypoint(p2d_all, s2d_all, K, R_w2c, t_w2c, frame_idx, joint_idx, conf_threshold=0.5):
    """Triangulates a single 3D keypoint for a specific frame."""
    C = p2d_all.shape[0]
    p2d_frame = p2d_all[:, frame_idx, joint_idx, :]
    s2d_frame = s2d_all[:, frame_idx, joint_idx]

    vis_mask = s2d_frame > conf_threshold # Use a confidence threshold
    if np.sum(vis_mask) < 2:
        return None

    pts_vis = p2d_frame[vis_mask]
    Ps_all = [K[c] @ np.hstack([R_w2c[c], t_w2c[c].reshape(3, 1)]) for c in range(C)]
    Ps_vis = [Ps_all[c] for c, is_vis in enumerate(vis_mask) if is_vis]

    # None rather than NaN, because every caller here tests `is None`.
    X = triangulate_dlt(pts_vis, Ps_vis)
    return None if np.isnan(X).any() else X


def joint_layout(prefix, subset, pose_engine):
    """Where the 2D poses are, and which joints are the head, heels and feet.

    MeTRAbs files hold either the full bml_movi_87 skeleton or the 26-joint
    calib26 subset, told apart by their joint count; RTMPose files are Halpe26.
    """
    detect_dir = os.path.join(prefix, subset, "2d_joint")
    n_joints = 0
    if os.path.isdir(detect_dir):
        sample = sorted(glob.glob(os.path.join(detect_dir, "*.json")))
        if sample:
            with open(sample[0]) as f:
                d = json.load(f)
            if d["data"]:
                n_joints = len(d["data"][0]["skeleton"][0]["score"])

    if pose_engine == "metrabs" and n_joints == 87:
        return {"name": "bml_movi_87", "n_joints": n_joints, "joint_dir": detect_dir, "legs": LEGS["bml_movi_87"],
                "head": BML87_HEAD, "l_heel": BML87_L_HEEL, "r_heel": BML87_R_HEEL,
                "feet": [BML87_L_HEEL, BML87_R_HEEL, BML87_L_TOE, BML87_R_TOE,
                         BML87_L_FOO, BML87_R_FOO, BML87_L_FIFTHMET, BML87_R_FIFTHMET]}
    if pose_engine == "metrabs":
        return {"name": "calib26", "n_joints": n_joints, "joint_dir": detect_dir, "legs": LEGS["calib26"],
                "head": CALIB26_HEAD, "l_heel": CALIB26_L_HEEL, "r_heel": CALIB26_R_HEEL,
                "feet": [CALIB26_L_HEEL, CALIB26_R_HEEL, CALIB26_L_TOE, CALIB26_R_TOE,
                         CALIB26_L_FOO, CALIB26_R_FOO]}
    return {"name": "halpe26", "n_joints": n_joints, "legs": LEGS["halpe26"], "trunk": TRUNK["halpe26"],
            "joint_dir": os.path.join(prefix, subset, "2d_joint_halpe26"),
            "head": HALPE26_HEAD, "l_heel": HALPE26_L_HEEL, "r_heel": HALPE26_R_HEEL,
            "feet": [HALPE26_L_HEEL, HALPE26_R_HEEL, HALPE26_L_BIG_TOE,
                     HALPE26_R_BIG_TOE, HALPE26_L_SMALL_TOE, HALPE26_R_SMALL_TOE]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scales and reorients a scene to metric units.")
    parser.add_argument("--prefix", required=True, help="Path to the session folder")
    parser.add_argument("--calib", required=True, help="Name of the best calibration JSON file")
    parser.add_argument("--height", required=True, type=float, help="Real-world height of the person in meters")
    parser.add_argument("--frame_idx", required=True, type=int, help="Index of a frame where the person is standing straight")
    parser.add_argument("--subset", default="noise_1_0", help="Subset folder name")
    parser.add_argument("--input_toml", default=None, help="Path to the input TOML file template")
    parser.add_argument("--export_toml", default=None, help="Path to save the final calibrated TOML file")
    parser.add_argument("--video_dir", default=None, help="Path to original videos (needed for TOML export)")
    parser.add_argument("--conf_threshold", type=float, default=0.5, help="Confidence threshold for 2D keypoints")
    parser.add_argument("--vertical_method", default="walk", choices=["frame", "walk"],
                        help="frame: head to feet on --frame_idx. walk: body axis over the whole walk "
                             "with the walking direction removed (see walking_vertical)")
    parser.add_argument("--scale_method", default="segments", choices=["head", "segments"],
                        help="head: head height on --frame_idx. segments: leg segment lengths over "
                             "all frames against stature (orientation still uses --frame_idx)")
    parser.add_argument("--pose_engine", default="rtmpose", choices=["rtmpose", "metrabs"],
                        help="Pose engine used: determines joint format for scaling")
    args = parser.parse_args(argv)

    layout = joint_layout(args.prefix, args.subset, args.pose_engine)
    if args.pose_engine == "metrabs":
        log.info(f"  Using MeTRAbs {layout['name']} joints for scaling ({layout['n_joints']} joints)")
    halpe26_dir = layout["joint_dir"]  # used below for loading poses
    HEAD_IDX, L_HEEL_IDX, R_HEEL_IDX = layout["head"], layout["l_heel"], layout["r_heel"]
    foot_kp_indices = layout["feet"]
    calib_json_path = os.path.join(args.prefix, "results", f"{args.calib}.json")

    with open(calib_json_path, 'r') as f:
        calib_data = json.load(f)
    
    CAMID = calib_data['CAMID']
    K = np.array(calib_data['K'])
    R_w2c_orig = np.array(calib_data['R_w2c'])
    t_w2c_orig = np.array(calib_data['t_w2c'])

    aid, pid, gid = session_ids(os.path.join(args.prefix, args.subset), args.prefix)

    p2d_list, s2d_list = [], []
    min_frames = float('inf')
    for cid in CAMID:
        fpath = os.path.join(halpe26_dir, f"A{aid:03d}_P{pid:03d}_G{gid:03d}_C{cid:03d}.json")
        if not os.path.exists(fpath):
            log.error(f"Halpe26 pose file not found: {fpath}")
            sys.exit(1)
        frames, p2d, s2d = load_poses(fpath)
        min_frames = min(min_frames, len(frames))
        p2d_list.append(p2d)
        s2d_list.append(s2d)

    num_joints = p2d_list[0].shape[1] // 2
    p2d_all = np.array([p[:min_frames].reshape(min_frames, num_joints, 2) for p in p2d_list])
    s2d_all = np.array([s[:min_frames].reshape(min_frames, num_joints) for s in s2d_list])

    # --- Triangulate Foot and Head Keypoints ---
    log.info(f"Triangulating keypoints for frame {args.frame_idx}...")
    foot_points_3d = [get_3d_keypoint(p2d_all, s2d_all, K, R_w2c_orig, t_w2c_orig, args.frame_idx, idx, args.conf_threshold) for idx in foot_kp_indices]
    foot_points_3d = [p for p in foot_points_3d if p is not None]

    if len(foot_points_3d) < 3:
        log.error(f"Not enough foot keypoints ({len(foot_points_3d)}) to define a plane. Try a different frame.")
        sys.exit(1)

    head_3d = get_3d_keypoint(p2d_all, s2d_all, K, R_w2c_orig, t_w2c_orig, args.frame_idx, HEAD_IDX, args.conf_threshold)
    if head_3d is None:
        log.error("Could not triangulate head. Cannot calculate scale.")
        sys.exit(1)

    # --- 1. Define New Coordinate System ---
    ground_centroid = np.mean(foot_points_3d, axis=0)
    
    # The vertical axis (Y-axis) is defined by the body's vertical vector
    # (from head to foot centroid). In OpenCV convention, Y points DOWN.
    y_axis_temp = ground_centroid - head_3d
    y_axis = y_axis_temp / np.linalg.norm(y_axis_temp)
    if args.vertical_method == "walk":
        up = walking_vertical(p2d_all, s2d_all, K, R_w2c_orig, t_w2c_orig, foot_kp_indices, HEAD_IDX,
                              (layout["legs"][0][2], layout["legs"][1][2]), args.conf_threshold)
        if up is None:
            log.warning("Too little of the walk seen to estimate the vertical; using frame "
                        f"{args.frame_idx} instead")
        else:
            if up @ (-y_axis) < 0:
                up = -up
            log.info(f"Vertical from the whole walk: {np.degrees(np.arccos(np.clip(up @ -y_axis, -1, 1))):.1f} deg "
                     f"from the frame {args.frame_idx} estimate")
            y_axis = -up

    # X-axis can be defined by the vector between heels
    l_heel_3d = get_3d_keypoint(p2d_all, s2d_all, K, R_w2c_orig, t_w2c_orig, args.frame_idx, L_HEEL_IDX, args.conf_threshold)
    r_heel_3d = get_3d_keypoint(p2d_all, s2d_all, K, R_w2c_orig, t_w2c_orig, args.frame_idx, R_HEEL_IDX, args.conf_threshold)
    
    if l_heel_3d is not None and r_heel_3d is not None:
        # X-axis should point to the right (Left Heel -> Right Heel to fix mirror effect)
        x_axis_temp = l_heel_3d - r_heel_3d
        heels_center = (l_heel_3d + r_heel_3d) / 2.0
    else:
        x_axis_temp = np.array([1.0, 0.0, 0.0])
        heels_center = ground_centroid

    x_axis = x_axis_temp - np.dot(x_axis_temp, y_axis) * y_axis
    if np.linalg.norm(x_axis) < 1e-6:
        x_axis_temp = np.array([1.0, 0.0, 0.0]) if abs(y_axis[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        x_axis = x_axis_temp - np.dot(x_axis_temp, y_axis) * y_axis

    x_axis = x_axis / np.linalg.norm(x_axis)

    # Z-axis is the cross product
    z_axis = np.cross(x_axis, y_axis)

    # Origin (0,0,0) is placed at the center of the heels (for X,Z axes),
    # and aligned with the lowest point of all foot points (for Y axis).
    floor_y_proj = max(np.dot(p, y_axis) for p in foot_points_3d)
    origin = heels_center + (floor_y_proj - np.dot(heels_center, y_axis)) * y_axis

    # --- 2. Create Transformation Matrix ---
    R_transform = np.vstack([x_axis, y_axis, z_axis])

    # --- 3. Transform Cameras ---
    R_w2c_new, t_w2c_new = [], []
    for R, t in zip(R_w2c_orig, t_w2c_orig):
        # Direct algebraic transformation without unstable matrix inversions
        R_new = R @ R_transform.T
        t_new = R @ origin.reshape(3, 1) + t.reshape(3, 1)

        R_w2c_new.append(R_new)
        t_w2c_new.append(t_new)

    R_w2c_new, t_w2c_new = np.array(R_w2c_new), np.array(t_w2c_new)

    # --- 4. Calculate and Apply Scale ---
    head_3d_new = (R_transform @ head_3d) - (R_transform @ origin)
    
    # The new Y coordinate of the head is negative (Y points down). Height is absolute value.
    measured_height = abs(head_3d_new[1])
    
    scale_factor = args.height / measured_height
    if args.scale_method == "segments":
        seg = segment_scale(p2d_all, s2d_all, K, R_w2c_orig, t_w2c_orig, layout["legs"], args.height,
                            args.conf_threshold, trunk=layout.get("trunk"))
        what = "leg and trunk segments" if layout.get("trunk") else "leg segments"
        if seg is None:
            log.warning(f"Too few frames to measure {what}; using the head height instead")
        else:
            log.info(f"Scale from {what}: {seg:.4f} (head height on frame {args.frame_idx}: {scale_factor:.4f})")
            scale_factor = seg
    log.info(f"Calculated scale factor: {scale_factor:.4f}")

    t_w2c_scaled = t_w2c_new * scale_factor

    # --- 5. Save Final Calibrated Files ---
    output_calib_path = os.path.join(args.prefix, "results", f"{args.calib}_oriented_scaled.json")
    out_data = {
        "CAMID": CAMID, "K": K.tolist(), "R_w2c": R_w2c_new.tolist(), "t_w2c": t_w2c_scaled.tolist(),
    }
    with open(output_calib_path, "w") as f:
        json.dump(out_data, f, indent=2)
    log.info(f"\nSaved final oriented and scaled calibration to: {output_calib_path}")

    if args.export_toml:
        if not args.video_dir:
            parser.error("--video_dir is required for TOML export.")
        cam_names = camera_names(args.video_dir)
        export_to_toml(args.input_toml, args.export_toml, R_w2c_new, t_w2c_scaled, cam_names)

if __name__ == "__main__":
    setup_logging()
    main()
