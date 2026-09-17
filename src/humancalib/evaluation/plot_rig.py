"""Figure and animation of a calibration against its gold rig, in the gold world frame.

    python -m humancalib.evaluation.plot_rig --work <trial> --run metrabs_v2 --eval metrabs_v3

Reads <work>/eval/<eval>/calibration_scaled.json (HumanCalib's metric, gravity-aligned
calibration written by compare) and <work>/gold/Calib_gold.toml. Writes, in
<work>/eval/<eval>/:

* cameras_vs_gold_3d_4dof.png, cameras_vs_gold_3d_7dof.png -- camera frustums, floor and
  subject in 3D, for each registration;
* cameras_vs_gold.png -- top and side views of both rigs, camera centres and optical
  axes, after two registrations into the gold world frame: 4-DoF (yaw + translation
  only: HumanCalib's own vertical and scale are kept, so this is what a user gets)
  and 7-DoF (similarity: the rig's shape alone);
* visu_3d.gif (with --gif) -- the pipeline's 3D animation of the skeleton and cameras
  with that calibration.
"""
import argparse
import os
import shutil
import subprocess
import sys

import numpy as np

from humancalib.cli import SUBSET, child_env
from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation import metrics as M
from humancalib.evaluation.compare import UP_HUMANCALIB, load_humancalib
from humancalib.evaluation.rig import read_pose2sim_toml

log = get_logger(__name__)


def display_rotation(up):
    """Rotation that turns the gold world so its vertical points up the figure.

    Errors are computed in the gold world; only what is drawn is turned. Without it a
    Y-down world such as OpenCap's is drawn lying on its side, cameras under the floor."""
    u = np.asarray(up, float) / np.linalg.norm(up)
    z = np.array([0.0, 0.0, 1.0])
    axis = np.cross(u, z)
    if np.linalg.norm(axis) < 1e-9:
        return np.eye(3) if u @ z > 0 else np.diag([1.0, -1.0, -1.0])
    import cv2
    angle = np.arccos(np.clip(u @ z, -1.0, 1.0))
    return cv2.Rodrigues(axis / np.linalg.norm(axis) * angle)[0]


def plot_rigs(est, gold, up_est, up_gold, path, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    Cg = np.array([g.center for g in gold])
    Ce = np.array([e.center for e in est])
    T4, b4 = M.yaw_align(Ce, Cg, up_est, up_gold)
    s7, T7, b7 = M.umeyama(Ce, Cg)
    D = display_rotation(up_gold)
    Cg_d = Cg @ D.T
    views = (("top", 0, 1), ("side", 0, 2))
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    for row, (T, b, s, name) in enumerate(((T4, b4, 1.0, "4-DoF registration: HumanCalib's own vertical and scale"),
                                           (T7, b7, s7, "7-DoF registration: rig shape only"))):
        A = s * Ce @ T.T + b
        err = np.linalg.norm(A - Cg, axis=1) * 1000
        rot = [M.rotation_angle_deg((est[i].R @ T.T) @ gold[i].R.T) for i in range(len(gold))]
        A_d = A @ D.T
        for col, (vname, i, j) in enumerate(views):
            ax = axes[row, col]
            for k, g in enumerate(gold):
                zg = D @ g.R.T @ np.array([0.0, 0.0, 1.0])
                ze = D @ T @ (est[k].R.T @ np.array([0.0, 0.0, 1.0]))
                ax.plot(Cg_d[k, i], Cg_d[k, j], "o", color="tab:green", ms=9)
                ax.arrow(Cg_d[k, i], Cg_d[k, j], 0.8 * zg[i], 0.8 * zg[j], color="tab:green", width=0.02)
                ax.plot(A_d[k, i], A_d[k, j], "x", color="tab:red", ms=10, mew=2)
                ax.arrow(A_d[k, i], A_d[k, j], 0.8 * ze[i], 0.8 * ze[j], color="tab:red", width=0.01)
                ax.annotate(g.name, (Cg_d[k, i], Cg_d[k, j]), xytext=(4, 4), textcoords="offset points", fontsize=8)
            if j == 2:
                ax.set_ylim(0, max(2.5, float(Cg_d[:, 2].max()) + 0.8))   # side view: keep height readable
            else:
                ax.set_aspect("equal")
            ax.grid(alpha=0.3)
            ax.set_xlabel("horizontal (m)")
            ax.set_ylabel("height (m)" if j == 2 else "horizontal (m)")
            ax.set_title(f"{name} — {vname} view\nposition error median {np.median(err):.0f} mm (max {err.max():.0f}), "
                         f"orientation error median {np.median(rot):.2f}° (max {max(rot):.2f}°)", fontsize=9)
    fig.suptitle(f"{title}   green = gold (lab calibration), red = HumanCalib, arrow = optical axis", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


HALPE26_BONES = [(17, 18), (18, 19), (18, 5), (18, 6), (5, 7), (7, 9), (6, 8), (8, 10), (19, 11), (19, 12),
                 (11, 13), (13, 15), (12, 14), (14, 16), (15, 24), (15, 20), (16, 25), (16, 21)]


def subject_skeleton(prefix, est, conf_threshold=0.5):
    """Halpe26 joints (26, 3) of the subject on the frame most cameras see, triangulated with
    the estimated calibration, in its world frame; None if no frame is usable."""
    from humancalib.core import load_poses
    from humancalib.pipeline.reselect_person import robust_triangulate
    d = os.path.join(prefix, SUBSET, "2d_joint_halpe26")
    if not os.path.isdir(d):
        return None
    names = sorted(f for f in os.listdir(d) if f.endswith(".json"))
    if len(names) != len(est):
        return None
    P, S = [], []
    for n in names:
        fi, p, sc = load_poses(os.path.join(d, n))
        P.append(p.reshape(len(fi), -1, 2))
        S.append(sc)
    nf = min(len(x) for x in S)
    seen = np.array([(S[c][:nf] > conf_threshold).sum(axis=1) for c in range(len(est))])   # (C, F)
    order = np.argsort(-(seen >= 20).sum(axis=0), kind="stable")
    Ps = np.array([e.projection() for e in est])
    for f in order[:20]:
        X, used = robust_triangulate(np.array([P[c][f] for c in range(len(est))]),
                                     np.array([S[c][f] > conf_threshold for c in range(len(est))]), Ps, 50.0, 5.0, 3)
        if used.sum() >= 3 and np.isfinite(X).all(axis=1).sum() >= 20:
            return X
    return None


def plot_rigs_3d(est, gold, up_est, up_gold, path, skeleton=None, title="", registration="4dof"):
    """Camera frustums of both rigs in the gold world frame, floor and subject.

    registration "4dof": yaw + translation only, HumanCalib's vertical and scale kept
    (end-to-end error). "7dof": similarity, the rig's shape alone."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    Cg = np.array([g.center for g in gold])
    Ce = np.array([e.center for e in est])
    if registration == "4dof":
        T, b = M.yaw_align(Ce, Cg, up_est, up_gold)
        s = 1.0
        label = "4-DoF registration: yaw and translation only, HumanCalib's own vertical and scale"
    else:
        s, T, b = M.umeyama(Ce, Cg)
        label = f"7-DoF registration: similarity, rig shape only (scale factor {s:.3f})"
    fig = plt.figure(figsize=(11, 9))
    ax = fig.add_subplot(111, projection="3d")
    D = display_rotation(up_gold)                      # drawing only: gold vertical up the figure

    def frustum(cam, R_world, C_world, color, lw, depth=0.6):
        w, h = cam.size
        K_inv = np.linalg.inv(cam.K)
        corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], float) @ K_inv.T * depth
        pts = (corners @ R_world.T + C_world) @ D.T    # camera -> world -> figure
        c = D @ C_world
        for q in pts:
            ax.plot(*zip(c, q), color=color, lw=lw)
        loop = np.vstack([pts, pts[:1]])
        ax.plot(loop[:, 0], loop[:, 1], loop[:, 2], color=color, lw=lw)

    pos_err, rot_err = [], []
    for k, g in enumerate(gold):
        Rw_est = T @ est[k].R.T                        # camera axes in the gold world
        Cw_est = s * T @ Ce[k] + b
        frustum(g, g.R.T, Cg[k], "tab:green", 2.0)
        frustum(est[k], Rw_est, Cw_est, "tab:red", 1.2)
        ax.text(*(D @ Cg[k] + [0, 0, 0.25]), g.name, fontsize=8)
        pos_err.append(np.linalg.norm(Cw_est - Cg[k]) * 1000)
        rot_err.append(M.rotation_angle_deg(Rw_est.T @ g.R.T))

    shown = [Cg @ D.T]
    Xw = None
    if skeleton is not None:
        Xw = (s * skeleton @ T.T + b) @ D.T
        shown.append(Xw[np.isfinite(Xw).all(axis=1)])
    shown = np.vstack(shown)
    lo, hi = shown.min(axis=0) - 1.0, shown.max(axis=0) + 1.0
    gx, gy = np.meshgrid(np.linspace(lo[0], hi[0], 12), np.linspace(lo[1], hi[1], 12))
    ax.plot_wireframe(gx, gy, np.zeros_like(gx), color="0.8", lw=0.5)   # floor: height 0 of the gold world
    if Xw is not None:
        for i, j in HALPE26_BONES:
            if np.isfinite(Xw[[i, j]]).all():
                ax.plot(*zip(Xw[i], Xw[j]), color="tab:blue", lw=2)

    ax.set_xlabel("horizontal (m)")
    ax.set_ylabel("horizontal (m)")
    ax.set_zlabel("height (m)")
    top = max(2.5, float(shown[:, 2].max()) + 0.8)
    ax.set_xlim(lo[0], hi[0])
    ax.set_ylim(lo[1], hi[1])
    ax.set_zlim(0, top)
    ax.set_box_aspect((hi[0] - lo[0], hi[1] - lo[1], top))      # metric proportions
    ax.view_init(elev=24, azim=-58)
    ax.set_title(f"{title}\n{len(gold)} cameras, lab world frame ({label})\n"
                 f"camera position error median {np.median(pos_err):.0f} mm (registration fitted on all cameras), "
                 f"orientation error median {np.median(rot_err):.2f}°", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)


def render_gif(work, run, eval_name, conf_threshold=0.5):
    """The pipeline's own 3D animation, on the scaled calibration of this comparison."""
    prefix = os.path.join(work, run)
    name = f"{eval_name}_scaled"
    shutil.copyfile(os.path.join(work, "eval", eval_name, "calibration_scaled.json"),
                    os.path.join(prefix, "results", f"{name}.json"))
    out = os.path.join(work, "eval", eval_name, "visu_3d.gif")
    rc = subprocess.run([sys.executable, "-m", "humancalib.postprocessing.visualize_results",
                         "--prefix", prefix, "--subset", SUBSET, "--calib", name, "--dataset", "MyDataset",
                         "--output", out, "--conf_threshold", str(conf_threshold)],
                        env=child_env(), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if rc.returncode != 0:
        log.warning(f"3D animation failed: {rc.stderr.strip().splitlines()[-1] if rc.stderr.strip() else rc.returncode}")
        return None
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--work", required=True)
    p.add_argument("--run", required=True, help="HumanCalib output folder, e.g. metrabs_v2")
    p.add_argument("--eval", required=True, help="eval/ folder of the comparison, e.g. metrabs_v3")
    p.add_argument("--gif", action="store_true")
    args = p.parse_args(argv)

    gold = read_pose2sim_toml(os.path.join(args.work, "gold", "Calib_gold.toml"))
    est = load_humancalib(os.path.join(args.work, "eval", args.eval, "calibration_scaled.json"), gold)
    import json
    with open(os.path.join(args.work, "gold", "meta.json")) as f:
        up_gold = json.load(f)["up"]
    png = os.path.join(args.work, "eval", args.eval, "cameras_vs_gold.png")
    plot_rigs(est, gold, UP_HUMANCALIB, up_gold, png,
              title=f"{os.path.basename(os.path.normpath(args.work))} — {args.eval} ({len(gold)} cameras)")
    skeleton = subject_skeleton(os.path.join(args.work, args.run), est)
    for registration in ("4dof", "7dof"):
        png3d = os.path.join(args.work, "eval", args.eval, f"cameras_vs_gold_3d_{registration}.png")
        plot_rigs_3d(est, gold, UP_HUMANCALIB, up_gold, png3d, skeleton=skeleton, registration=registration,
                     title=f"{os.path.basename(os.path.normpath(args.work))}: HumanCalib (red) vs lab calibration (green)")
        log.info(f"3D figure -> {png3d}")
    log.info(f"Figure -> {png}")
    if args.gif:
        gif = render_gif(args.work, args.run, args.eval)
        if gif:
            log.info(f"Animation -> {gif}")
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
