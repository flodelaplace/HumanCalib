"""Figure and animation of a calibration against its gold rig, in the gold world frame.

    python -m humancalib.evaluation.plot_rig --work <trial> --run metrabs_v2 --eval metrabs_v3

Reads <work>/eval/<eval>/calibration_scaled.json (HumanCalib's metric, gravity-aligned
calibration written by compare) and <work>/gold/Calib_gold.toml. Writes, in
<work>/eval/<eval>/:

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


def plot_rigs(est, gold, up_est, up_gold, path, title=""):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    Cg = np.array([g.center for g in gold])
    Ce = np.array([e.center for e in est])
    T4, b4 = M.yaw_align(Ce, Cg, up_est, up_gold)
    s7, T7, b7 = M.umeyama(Ce, Cg)
    views = (("dessus (x, y)", 0, 1), ("côté (x, z)", 0, 2))
    fig, axes = plt.subplots(2, 2, figsize=(13, 10))
    for row, (T, b, s, name) in enumerate(((T4, b4, 1.0, "recalage 4 ddl : verticale et échelle HumanCalib"),
                                           (T7, b7, s7, "recalage 7 ddl : forme seule"))):
        A = s * Ce @ T.T + b
        err = np.linalg.norm(A - Cg, axis=1) * 1000
        rot = [M.rotation_angle_deg((est[i].R @ T.T) @ gold[i].R.T) for i in range(len(gold))]
        for col, (vname, i, j) in enumerate(views):
            ax = axes[row, col]
            for k, g in enumerate(gold):
                zg = g.R.T @ np.array([0.0, 0.0, 1.0])
                ze = T @ (est[k].R.T @ np.array([0.0, 0.0, 1.0]))
                ax.plot(Cg[k, i], Cg[k, j], "o", color="tab:green", ms=9)
                ax.arrow(Cg[k, i], Cg[k, j], 0.8 * zg[i], 0.8 * zg[j], color="tab:green", width=0.02)
                ax.plot(A[k, i], A[k, j], "x", color="tab:red", ms=10, mew=2)
                ax.arrow(A[k, i], A[k, j], 0.8 * ze[i], 0.8 * ze[j], color="tab:red", width=0.01)
                ax.annotate(g.name, (Cg[k, i], Cg[k, j]), xytext=(4, 4), textcoords="offset points", fontsize=8)
            ax.set_aspect("equal")
            ax.grid(alpha=0.3)
            ax.set_xlabel(f"{'xyz'[i]} (m)")
            ax.set_ylabel(f"{'xyz'[j]} (m)")
            ax.set_title(f"{name} — vue de {vname}\nposition médiane {np.median(err):.0f} mm (max {err.max():.0f}), "
                         f"orientation médiane {np.median(rot):.2f}° (max {max(rot):.2f}°)", fontsize=9)
    fig.suptitle(f"{title}   vert = gold, rouge = HumanCalib, flèche = axe optique", fontsize=11)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
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
              title=f"{os.path.basename(os.path.normpath(args.work))} — {args.eval} ({len(gold)} caméras)")
    log.info(f"Figure -> {png}")
    if args.gif:
        gif = render_gif(args.work, args.run, args.eval)
        if gif:
            log.info(f"Animation -> {gif}")
    return 0


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
