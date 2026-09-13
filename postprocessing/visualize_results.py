"""
visualize_results.py
---------------------
Visualisation frame par frame du squelette 3D triangulé + position des caméras
à partir des résultats de calibration extrinsèque.

Usage:
    python visualize_results.py \
        --prefix   ./data/A001_P001_G001 \
        --subset   noise_1_0 \
        --calib    linear_1_0_ba \
        --dataset  MyDataset \
        --output   ./data/A001_P001_G001/results/camera/visu_3d.gif

    # Pour un MP4 au lieu d'un GIF :
        --output   ./data/A001_P001_G001/results/camera/visu_3d.mp4
"""

import argparse
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import mpl_toolkits.mplot3d.art3d as art3d

# Add repo root for util import (script lives in postprocessing/) and locate VideoPose3D
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

vp3d_path = os.path.join(_REPO_ROOT, "third_party", "VideoPose3D")
if vp3d_path not in sys.path:
    sys.path.insert(0, vp3d_path)

from core import load_poses, load_eldersim_camera
from core.skeletons import METRABS_BONE, METRABS_KEY, OP_KEY
from core.session import load_session_dir
from postprocessing.evaluate_calibration import reproject_points, triangulate_skeleton

# ── Display skeletons ────────────────────────────────────────────────────────
#
# IMPORTANT: OPENPOSE_DRAW_SKELETON is NOT core.skeletons.OP_BONE and must not
# be merged with it. core's OP_BONE has 12 bones -- the set used for bone-length
# regularisation in bundle adjustment. The 24 edges below are for *drawing*:
# they add face, ears and toe segments that make the rendered figure readable
# but would be redundant or degenerate as calibration constraints.
#
# The MeTRAbs topology and both joint-name lists, by contrast, were verified
# identical to core's and are now taken from there.
OPENPOSE_DRAW_SKELETON = (
    (1, 8), (1, 2), (1, 5), (0, 15), (0, 16),
    (15, 17), (16, 18), (1, 0),
    (2, 3), (3, 4), (5, 6), (6, 7),
    (8, 9), (8, 12),
    (9, 10), (12, 13),
    (10, 11), (13, 14),
    (11, 22), (11, 24), (22, 23),
    (14, 19), (14, 21), (19, 20),
)
OPENPOSE_SKELETON = OPENPOSE_DRAW_SKELETON  # backwards-compatible alias

METRABS_SKELETON = METRABS_BONE
OP_NAMES = list(OP_KEY)
METRABS_NAMES = list(METRABS_KEY)


def export_to_trc(X3d_world, output_path, fps=30.0):
    """
    Exporte les coordonnées 3D au format .trc (pour OpenSim / Mokka)
    """
    import os
    N, J, _ = X3d_world.shape
    if J == 87:
        from core import BML87_KEY
        joint_names = [k for k, v in sorted(BML87_KEY.items(), key=lambda x: x[1])]
    elif J == 26:
        joint_names = METRABS_NAMES
    else:
        joint_names = OP_NAMES[:J]
    for i in range(len(joint_names), J):
        joint_names.append(f"Joint_{i}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(f"PathFileType\t4\t(X/Y/Z)\t{os.path.basename(output_path)}\n")
        f.write("DataRate\tCameraRate\tNumFrames\tNumMarkers\tUnits\tOrigDataRate\tOrigDataStartFrame\tOrigNumFrames\n")
        f.write(f"{fps:.2f}\t{fps:.2f}\t{N}\t{J}\tm\t{fps:.2f}\t1\t{N}\n")
        f.write("Frame#\tTime\t")
        for name in joint_names:
            f.write(f"{name}\t\t\t")
        f.write("\n\t\t")
        for i in range(1, J + 1):
            f.write(f"X{i}\tY{i}\tZ{i}\t")
        f.write("\n\n")
        for n in range(N):
            time = n / fps
            f.write(f"{n + 1}\t{time:.5f}\t")
            for j in range(J):
                pt = X3d_world[n, j]
                if np.isnan(pt).any():
                    f.write("\t\t\t")
                else:
                    f.write(f"{pt[0]:.5f}\t{pt[1]:.5f}\t{pt[2]:.5f}\t")
            f.write("\n")
    print(f"Saved TRC file to: {output_path}")

BONE_COLOR  = "#f94e3e"
CAM_COLOR   = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0",
               "#00BCD4", "#FFEB3B", "#795548", "#607D8B"]


def draw_camera(ax, R_w2c, t_w2c, color, label, scale=0.15):
    """Dessine une pyramide représentant une caméra dans le repère monde."""
    C = (-R_w2c.T @ t_w2c.reshape(3, 1)).flatten()
    
    w, h, f = 0.8, 0.6, 1.0
    corners_cam = np.array([[w, h, f], [-w, h, f], [-w, -h, f], [w, -h, f]]) * scale
    corners_world = (R_w2c.T @ corners_cam.T).T + C

    # Mapping pour l'affichage Matplotlib : (X_cv, Y_cv, Z_cv) -> (X, Z, -Y)
    C_plot = [C[0], C[2], -C[1]]
    corners_plot = np.empty_like(corners_world)
    corners_plot[:, 0] = corners_world[:, 0]
    corners_plot[:, 1] = corners_world[:, 2]
    corners_plot[:, 2] = -corners_world[:, 1]

    for corner in corners_plot:
        ax.plot([C_plot[0], corner[0]], [C_plot[1], corner[1]], [C_plot[2], corner[2]],
                color=color, linewidth=1.5, alpha=0.8)
    for i in range(4):
        j = (i + 1) % 4
        ax.plot([corners_plot[i, 0], corners_plot[j, 0]],
                [corners_plot[i, 1], corners_plot[j, 1]],
                [corners_plot[i, 2], corners_plot[j, 2]],
                color=color, linewidth=1.5, alpha=0.8)

    ax.scatter(*C_plot, c=color, s=60, zorder=10, marker="o", depthshade=False)
    ax.text(C_plot[0], C_plot[1], C_plot[2] + 0.1, f"  {label}", color=color, fontsize=9, fontweight="bold", ha='center')


def make_animation(X3d_world, R_w2c, t_w2c, output_path, fps=15, step=1,
                   floor_at_zero=False, K=None, p2d_all=None, s2d_all=None,
                   conf_threshold=0.5):
    """
    Génère un GIF/MP4 animé avec le squelette triangulé + les caméras.

    floor_at_zero: when True, clamps the vertical-axis lower bound to 0
    (used for the FINAL oriented+scaled viz where the calibration places
    feet at y=0 in world space).

    K, p2d_all, s2d_all, conf_threshold: optional. When provided, live
    reprojection-error metrics are overlaid (mean MRE, per-camera MRE,
    and per-frame Cams/Joints/MRE card).
    """
    N, J, _ = X3d_world.shape
    frames_to_render = list(range(0, N, step))

    cam_positions = np.array([(-R.T @ t.reshape(3, 1)).flatten() for R, t in zip(R_w2c, t_w2c)])

    # ── Pre-compute reprojection metrics (once) ──────────────────────────────
    metrics_enabled = K is not None and p2d_all is not None and s2d_all is not None
    global_mre = float('nan')
    per_cam_mre = None
    frame_n_cams = None
    frame_n_joints = None
    frame_mre = None
    if metrics_enabled:
        K_arr = np.array(K)
        p2d_reproj = reproject_points(X3d_world, K_arr, R_w2c, t_w2c)  # (C, N, J, 2)
        err_tensor = np.linalg.norm(p2d_reproj - p2d_all, axis=-1)  # (C, N, J)
        valid_tensor = (s2d_all > conf_threshold) & ~np.isnan(err_tensor)
        C_metrics = err_tensor.shape[0]

        per_cam_mre = np.array([
            float(np.mean(err_tensor[c][valid_tensor[c]])) if valid_tensor[c].any() else float('nan')
            for c in range(C_metrics)
        ])
        all_valid = err_tensor[valid_tensor]
        global_mre = float(np.mean(all_valid)) if len(all_valid) else float('nan')

        frame_n_cams = valid_tensor.any(axis=2).sum(axis=0).astype(int)
        frame_n_joints = (~np.isnan(X3d_world).any(axis=2)).sum(axis=1).astype(int)
        with np.errstate(invalid='ignore', all='ignore'):
            errs_per_frame = np.where(valid_tensor, err_tensor, np.nan)
            frame_mre = np.nanmean(errs_per_frame.reshape(C_metrics, N, -1), axis=(0, 2))

    valid = X3d_world[~np.isnan(X3d_world).any(axis=-1)].reshape(-1, 3)

    # Bounding box pour le squelette (robuste au bruit via les percentiles)
    if len(valid) > 0:
        valid_plot = np.copy(valid)
        valid_plot[:, 0] = valid[:, 0]
        valid_plot[:, 1] = valid[:, 2]
        valid_plot[:, 2] = -valid[:, 1]
        skel_min = np.percentile(valid_plot, 2, axis=0)
        skel_max = np.percentile(valid_plot, 98, axis=0)
    else:
        skel_min = np.array([np.inf, np.inf, np.inf])
        skel_max = np.array([-np.inf, -np.inf, -np.inf])

    # Bounding box pour les caméras (inclusions strictes avec min/max)
    cam_plot = np.copy(cam_positions)
    cam_plot[:, 0] = cam_positions[:, 0]
    cam_plot[:, 1] = cam_positions[:, 2]
    cam_plot[:, 2] = -cam_positions[:, 1]
    cam_min = np.min(cam_plot, axis=0)
    cam_max = np.max(cam_plot, axis=0)

    pad = 0.1
    xmin, ymin, zmin = np.minimum(skel_min, cam_min) - pad
    xmax, ymax, zmax = np.maximum(skel_max, cam_max) + pad
    if floor_at_zero:
        zmin = 0.0  # Feet at y=0 by construction; never plot the floor in the negative half.

    cam_colors = ["#2196F3", "#E91E63", "#4CAF50", "#FF9800",
                  "#9C27B0", "#00BCD4", "#FFEB3B", "#795548"]
    n_cams = len(R_w2c)
    # Camera marker size scales with the largest world extent.
    scale = max(xmax - xmin, ymax - ymin, zmax - zmin) * 0.06

    BG_COLOR     = "#FAFAFA"
    FLOOR_COLOR  = "#7A7A7A"
    SIDE_PANE    = "#F0F0F0"
    POINT_COLOR  = "#1a1a1a"
    TEXT_COLOR   = "#222222"
    TICK_COLOR   = "#555555"

    # Approximate the projected 2D aspect ratio of the 3D scene at the chosen
    # view angle so the figure isn't a square wasting white space when the
    # scene is rectangular (typical with cameras spread around a small zone).
    import math as _math
    _e = _math.radians(20); _a = _math.radians(-60)
    _dx = xmax - xmin; _dy = ymax - ymin; _dz = zmax - zmin
    _horiz_proj = abs(_dx * _math.cos(_a)) + abs(_dy * _math.sin(_a))
    _vert_proj = (abs(_dz * _math.cos(_e))
                  + (abs(_dx * _math.sin(_a)) + abs(_dy * _math.cos(_a))) * _math.sin(_e))
    _scene_aspect = _horiz_proj / max(_vert_proj, 1e-6)

    _content_h = 8.0
    _title_inches = 0.85 if metrics_enabled else 0.3
    _fig_h = _content_h + _title_inches
    _fig_w = max(min(_content_h * _scene_aspect, 16.0), 7.0)

    fig = plt.figure(figsize=(_fig_w, _fig_h), facecolor=BG_COLOR)
    ax  = fig.add_subplot(111, projection="3d")
    _top = 1.0 - (_title_inches / _fig_h)
    fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=_top)
    ax.set_facecolor(BG_COLOR)
    fig.patch.set_facecolor(BG_COLOR)
    # Closer 3D camera trims some of matplotlib's interior auto-padding.
    try:
        ax.dist = 8.0
    except Exception:
        pass

    method_labels = {
        "linear_1_0":     "Linear",
        "linear_1_0_ba":  "Linear + Bundle Adjustment ⭐",
        "ransac_1_0":     "RANSAC",
        "ransac_1_0_ba":  "RANSAC + Bundle Adjustment",
    }
    calib_name = os.path.splitext(os.path.basename(output_path))[0].replace("visu_3d_", "")
    method_label = method_labels.get(calib_name, calib_name)

    # Static per-camera MRE line, rendered once below the (dynamic) suptitle.
    if metrics_enabled and per_cam_mre is not None:
        per_cam_str = "   ".join(
            f"Cam{c+1}: {per_cam_mre[c]:.1f} px" if not np.isnan(per_cam_mre[c]) else f"Cam{c+1}:  -- "
            for c in range(len(per_cam_mre))
        )
        # Per-cam line near the bottom of the reserved title strip
        # (suptitle sits above, plot sits below — both with breathing room).
        _percam_y = _top + 0.25 * (1.0 - _top)
        fig.text(0.5, _percam_y, per_cam_str,
                 color=TEXT_COLOR, fontsize=9, ha='center',
                 family='monospace')

    def draw_frame(fc):
        ax.clear()
        ax.set_facecolor(BG_COLOR)

        if metrics_enabled:
            suptitle = (f"{method_label}  —  Frame {fc+1}/{N}  —  "
                        f"Mean MRE: {global_mre:.2f} px")
            _sup_y = _top + 0.75 * (1.0 - _top)
            fig.suptitle(suptitle, color=TEXT_COLOR, fontsize=11, y=_sup_y)
        else:
            ax.set_title(f"{method_label}  —  Frame {fc+1}/{N}  —  {n_cams} cameras",
                         color=TEXT_COLOR, fontsize=10)

        # Side panes barely visible; floor pane (zaxis) takes a stronger gray when the
        # calibration is oriented+scaled so the ground reads as ground. Use the native
        # zaxis pane rather than plot_surface — the pane is rendered behind the scene
        # by matplotlib's depth sort, while a translucent surface ends up overlaid on
        # top of the skeleton due to a known 3D-zorder issue.
        ax.xaxis.pane.set_facecolor(SIDE_PANE)
        ax.xaxis.pane.set_edgecolor(SIDE_PANE)
        ax.yaxis.pane.set_facecolor(SIDE_PANE)
        ax.yaxis.pane.set_edgecolor(SIDE_PANE)
        floor_color = FLOOR_COLOR if floor_at_zero else SIDE_PANE
        ax.zaxis.pane.set_facecolor(floor_color)
        ax.zaxis.pane.set_edgecolor(floor_color)

        ax.set_xlabel("X", color=TEXT_COLOR); ax.set_ylabel("Z", color=TEXT_COLOR)
        ax.set_zlabel("Y (vertical)", color=TEXT_COLOR)
        ax.tick_params(colors=TICK_COLOR)

        # Independent per-axis limits: the previous cubic [cx ± max_range]
        # left a lot of empty space whenever cameras and skeleton spanned
        # different ranges along each axis. set_box_aspect keeps proportions
        # visually correct without forcing a cube.
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_zlim(zmin, zmax)
        ax.set_box_aspect((xmax - xmin, ymax - ymin, zmax - zmin))

        ax.view_init(elev=20, azim=-60)

        # Per-frame metrics card (top-left in axes-relative coords).
        if metrics_enabled:
            fmre = frame_mre[fc] if frame_mre is not None else float('nan')
            mre_color = (
                "#1B5E20" if (not np.isnan(fmre) and fmre < 5)
                else "#E65100" if (not np.isnan(fmre) and fmre < 10)
                else "#B71C1C" if not np.isnan(fmre)
                else TEXT_COLOR
            )
            mre_str = f"{fmre:.1f} px" if not np.isnan(fmre) else "  -- "
            card = (f"Cams      : {frame_n_cams[fc]}/{n_cams}\n"
                    f"Joints    : {frame_n_joints[fc]}/{J}\n"
                    f"Frame MRE : {mre_str}")
            ax.text2D(0.02, 0.92, card, transform=ax.transAxes,
                      family='monospace', fontsize=9, color=TEXT_COLOR,
                      verticalalignment='top', horizontalalignment='left',
                      bbox=dict(facecolor='white', alpha=0.85,
                                edgecolor='#cccccc', boxstyle='round,pad=0.4'))
            # Dot to color-code the frame MRE next to its value.
            ax.text2D(0.155, 0.858, "●", transform=ax.transAxes,
                      fontsize=12, color=mre_color, verticalalignment='top')

        pts = X3d_world[fc]
        pts_plot = np.copy(pts)
        pts_plot[:, 0] = pts[:, 0]
        pts_plot[:, 1] = pts[:, 2]
        pts_plot[:, 2] = -pts[:, 1]

        valid_mask = ~np.isnan(pts_plot).any(axis=1)
        ax.scatter(pts_plot[valid_mask, 0], pts_plot[valid_mask, 1], pts_plot[valid_mask, 2],
                   c=POINT_COLOR, s=8, zorder=5, depthshade=False)
        skeleton = (METRABS_SKELETON if X3d_world.shape[1] == 26
                    else OPENPOSE_SKELETON)
        if X3d_world.shape[1] == 87:
            from core import BML87_BONE
            skeleton = [(int(b[0]), int(b[1])) for b in BML87_BONE]
        for j0, j1 in skeleton:
            p0, p1 = pts_plot[j0], pts_plot[j1]
            if not (np.isnan(p0).any() or np.isnan(p1).any()):
                line = art3d.Line3D([p0[0], p1[0]], [p0[1], p1[1]], [p0[2], p1[2]],
                                    color=BONE_COLOR, linewidth=3, alpha=1.0) # Traits plus épais
                ax.add_line(line)

        # Draw cameras
        for i, (R, t) in enumerate(zip(R_w2c, t_w2c)):
            color = cam_colors[i % len(cam_colors)]
            draw_camera(ax, R, t, color=color, label=f"Cam{i+1}", scale=scale)

    print(f"Rendering {len(frames_to_render)} frames...")
    ani = animation.FuncAnimation(fig, draw_frame,
                                  frames=frames_to_render,
                                  interval=1000 // fps,
                                  repeat=False)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    ext = os.path.splitext(output_path)[1].lower()
    if ext == ".gif":
        ani.save(output_path, writer="pillow", fps=fps)
    else:
        ani.save(output_path, writer="ffmpeg", fps=fps,
                 extra_args=["-vcodec", "libx264", "-pix_fmt", "yuv420p"])
    plt.close(fig)
    print(f"Saved: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Visualize the triangulated 3D skeleton + cameras after calibration."
    )
    parser.add_argument("--prefix",  required=True,
                        help="Example: ./data/A001_P001_G001")
    parser.add_argument("--subset",  default="noise_1_0",
                        help="Name of the subset folder with poses (default: noise_1_0)")
    parser.add_argument("--calib",   default="linear_1_0_ba",
                        help="Name of the calibration JSON file in results/ (default: linear_1_0_ba)")
    parser.add_argument("--dataset", default="MyDataset")
    parser.add_argument("--output",  default=None,
                        help="Output path .gif or .mp4 (default: results/camera/visu_3d.gif)")
    parser.add_argument("--fps",     type=int, default=15,
                        help="Animation FPS (default: 15)")
    parser.add_argument("--step",    type=int, default=0,
                        help="Render 1 frame every N (default: 0 = auto-cap GIF to ~150 frames)")
    parser.add_argument("--max_frames", type=int, default=150,
                        help="Max GIF frames when --step=0 (default: 150)")
    parser.add_argument("--conf_threshold", type=float, default=0.5,
                         help="Confidence threshold for 2D keypoints")
    parser.add_argument("--export_trc", default=None,
                         help="Export the triangulated 3D skeleton to a .trc file path")
    args = parser.parse_args()

    subset_dir = os.path.join(args.prefix, args.subset)
    calib_json = os.path.join(args.prefix, "results", f"{args.calib}.json")
    if args.output is None:
        out_dir = os.path.join(args.prefix, "results", "camera")
        args.output = os.path.join(out_dir, f"visu_3d_{args.calib}.gif")

    session = load_session_dir(subset_dir)
    
    base_name = os.path.basename(os.path.normpath(args.prefix))
    import re
    match = re.search(r'A(\d+)_P(\d+)_G(\d+)', base_name)
    if match:
        aid, pid, gid = int(match.group(1)), int(match.group(2)), int(match.group(3))
    else:
        # Fallback for folder names that don't follow the Axxx_Pxxx_Gxxx convention
        print(f"WARNING: Output directory '{base_name}' does not match Axxx_Pxxx_Gxxx format. Using default IDs (AID=1, PID=1, GID=1).")
        aid, pid, gid = 1, 1, 1
    
    camera_ids = session["camera_ids"]

    print(f"Dataset    : {args.dataset}")
    print(f"Subset     : {subset_dir}")
    print(f"Calibration: {calib_json}")
    print(f"Cameras    : {camera_ids}")

    CAMID, K, R_w2c, t_w2c, _dist = load_eldersim_camera(calib_json)
    R_w2c = np.array(R_w2c)
    t_w2c = np.array(t_w2c)
    K      = np.array(K)
    print(f"Loaded calibration for {len(CAMID)} cameras")

    p2d_list, s2d_list = [], []
    min_frames = 999999
    for cid in camera_ids:
        fpath = os.path.join(subset_dir, "2d_joint", f"A{aid:03d}_P{pid:03d}_G{gid:03d}_C{cid:03d}.json")
        frames, p2d, s2d = load_poses(fpath)
        if len(frames) < min_frames:
            min_frames = len(frames)
        p2d_list.append(p2d.reshape(len(frames), -1, 2))
        s2d_list.append(s2d)

    p2d_list = [p[:min_frames] for p in p2d_list]
    s2d_list = [s[:min_frames] for s in s2d_list]
    p2d_all = np.array(p2d_list)
    s2d_all = np.array(s2d_list)
    N = p2d_all.shape[1]
    print(f"Frames     : {N} (truncated to shortest video)")

    print("Triangulating 3D skeleton in world frame...")
    X3d_world = triangulate_skeleton(p2d_all, s2d_all, K, R_w2c, t_w2c, args.conf_threshold)
    print(f"X3d_world shape: {X3d_world.shape}")

    if args.export_trc:
        dataset_fps = session.get("frame_rate", 30.0)
        export_to_trc(X3d_world, args.export_trc, fps=dataset_fps)

    # Auto-step: cap GIF to ~max_frames for fast rendering
    step = args.step
    if step == 0:
        step = max(1, N // args.max_frames)
        if step > 1:
            print(f"Auto-step: rendering 1/{step} frames ({N // step}/{N} total)")

    make_animation(X3d_world, R_w2c, t_w2c,
                   output_path=args.output,
                   fps=args.fps,
                   step=step,
                   floor_at_zero=args.calib.endswith("_oriented_scaled"),
                   K=K, p2d_all=p2d_all, s2d_all=s2d_all,
                   conf_threshold=args.conf_threshold)


if __name__ == "__main__":
    main()
