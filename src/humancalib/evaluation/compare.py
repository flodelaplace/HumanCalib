"""Compare HumanCalib's output for one prepared trial with its gold calibration.

    python -m humancalib.evaluation.compare --work <trial folder> --engine metrabs

Reads   <work>/gold/Calib_gold.toml, <work>/gold/meta.json   (from a dataset's `prepare`)
        <work>/<engine>/                                     (a `humancalib run` output folder)
Writes  <work>/eval/<engine>/metrics.json, pairs.csv, cameras.csv, ref_frames.csv

Steps, following docs/EVALUATION_PROTOCOL.md:

1. MRE of each calibration stage, and the one the pipeline would keep (lowest MRE).
2. Similarity-invariant metrics for every stage -- they need no scaling.
3. The reference frame for scaling, chosen from HumanCalib's own detections only:
   the frame where most cameras see the head and both heels confidently, ties
   broken by mean confidence. The kept calibration is scaled on it with the
   pipeline's own step, and every metric is computed.
4. Sensitivity to that choice: scale and verticality recomputed on up to N other
   frames with the same camera coverage, spread over the trial.
"""
import argparse
import csv
import json
import os
import shutil

import numpy as np

from humancalib.cli import SUBSET, best_calibration
from humancalib.core import load_poses
from humancalib.core.log import get_logger, setup_logging
from humancalib.core.session import session_ids
from humancalib.evaluation.metrics import compare_rigs, pairwise_errors
from humancalib.evaluation.rig import Camera, read_pose2sim_toml
from humancalib.postprocessing import evaluate_calibration, scale_scene

log = get_logger(__name__)

# HumanCalib's final frame: OpenCV axes, y pointing down.
UP_HUMANCALIB = (0.0, -1.0, 0.0)
STAGES = ("linear_1_0", "linear_1_0_ba")


def load_humancalib(path, gold):
    """A HumanCalib calibration JSON as cameras named like the gold ones.

    HumanCalib numbers cameras in the sorted order of the video names, which is
    the order of the gold TOML for every prepared trial."""
    with open(path) as f:
        d = json.load(f)
    R, t = np.array(d["R_w2c"], float), np.array(d["t_w2c"], float).reshape(-1, 3)
    if len(R) != len(gold):
        raise ValueError(f"{path}: {len(R)} cameras, gold has {len(gold)}")
    return [Camera(g.name, g.size, g.K, g.dist, R[i], t[i]) for i, g in enumerate(gold)]


def pose_scores(prefix, layout):
    """Per camera, frame and joint confidence (C, F, J), and the absolute frame numbers."""
    with open(os.path.join(prefix, "results", f"{STAGES[0]}.json")) as f:
        camids = json.load(f)["CAMID"]
    aid, pid, gid = session_ids(os.path.join(prefix, SUBSET), prefix)
    frames, scores = [], []
    for cid in camids:
        fi, _, s = load_poses(os.path.join(layout["joint_dir"], f"A{aid:03d}_P{pid:03d}_G{gid:03d}_C{cid:03d}.json"))
        frames.append(fi)
        scores.append(s)
    n = min(len(s) for s in scores)
    return np.array([s[:n] for s in scores]), np.asarray(frames[0][:n])


def rank_reference_frames(scores, layout, conf_threshold):
    """Frame indices ordered by (cameras seeing head and heels, mean confidence), best first."""
    joints = [layout["head"], layout["l_heel"], layout["r_heel"]]
    s = scores[:, :, joints]                                   # (C, F, 3)
    seen = (s > conf_threshold).all(axis=2)                     # (C, F)
    coverage = seen.sum(axis=0)
    mean_conf = np.where(seen[:, :, None], s, 0).sum(axis=(0, 2)) / np.maximum(3 * coverage, 1)
    order = np.lexsort((-mean_conf, -coverage))
    return order, coverage


def scale_on(prefix, calib, height, frame_idx, engine, conf_threshold):
    """Run the pipeline's scaling step on one frame; the resulting JSON path, or None."""
    try:
        scale_scene.main(["--prefix", prefix, "--calib", calib, "--height", str(height),
                          "--frame_idx", str(int(frame_idx)), "--pose_engine", engine,
                          "--conf_threshold", str(conf_threshold)])
    except SystemExit as e:
        if e.code not in (0, None):
            return None
    path = os.path.join(prefix, "results", f"{calib}_oriented_scaled.json")
    return path if os.path.isfile(path) else None


def write_csv(path, rows):
    if not rows:
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work", required=True, help="prepared trial folder")
    parser.add_argument("--engine", required=True, choices=("metrabs", "rtmpose"))
    parser.add_argument("--conf_threshold", type=float, default=0.5)
    parser.add_argument("--n_ref_frames", type=int, default=10, help="frames for the sensitivity analysis")
    args = parser.parse_args(argv)

    with open(os.path.join(args.work, "gold", "meta.json")) as f:
        meta = json.load(f)
    gold = read_pose2sim_toml(os.path.join(args.work, "gold", "Calib_gold.toml"))
    up_gold = meta["up"]
    prefix = os.path.join(args.work, args.engine)
    out = os.path.join(args.work, "eval", args.engine)
    os.makedirs(out, exist_ok=True)
    report = {"meta": meta, "engine": args.engine, "stages": {}}

    # 1-2. every calibration stage: MRE and invariant metrics
    scores = {}
    for stage in STAGES:
        path = os.path.join(prefix, "results", f"{stage}.json")
        if not os.path.isfile(path):
            continue
        mre = evaluate_calibration.main(["--prefix", prefix, "--calib", stage, "--video_dir", meta["video_dir"],
                                         "--conf_threshold", str(args.conf_threshold)])
        scores[stage] = float(mre)
        pairs = pairwise_errors(load_humancalib(path, gold), gold)
        report["stages"][stage] = {
            "mre_px": scores[stage],
            "rel_rot_deg_median": float(np.median([p["rot_deg"] for p in pairs])),
            "rel_dir_deg_median": float(np.median([p["dir_deg"] for p in pairs])),
        }
    best = best_calibration(scores)
    if best is None:
        raise SystemExit(f"no HumanCalib calibration found in {prefix}/results")
    report["kept_stage"] = best

    # 3. reference frame and scaling
    layout = scale_scene.joint_layout(prefix, SUBSET, args.engine)
    conf, frame_numbers = pose_scores(prefix, layout)
    order, coverage = rank_reference_frames(conf, layout, args.conf_threshold)
    chosen = int(order[0])
    top = order[coverage[order] == coverage[chosen]]
    others = [int(f) for f in np.sort(top)[np.linspace(0, len(top) - 1, min(args.n_ref_frames, len(top))).astype(int)]]

    # 4. sensitivity first, so the chosen frame's result is the one left in results/
    sensitivity = []
    for f in others + [chosen]:
        path = scale_on(prefix, best, meta["stature_m"], f, args.engine, args.conf_threshold)
        row = {"frame_idx": f, "video_frame": int(frame_numbers[f]), "cameras_seeing": int(coverage[f]),
               "chosen": f == chosen, "ok": path is not None}
        if path:
            s = compare_rigs(load_humancalib(path, gold), gold, UP_HUMANCALIB, up_gold)["summary"]
            row.update({k: s[k] for k in ("scale_ratio_median", "gravity_deg", "abs4dof_pos_mm_median",
                                          "abs4dof_rot_deg_median")})
            if f == chosen:
                shutil.copyfile(path, os.path.join(out, "calibration_scaled.json"))
                final = compare_rigs(load_humancalib(path, gold), gold, UP_HUMANCALIB, up_gold)
        sensitivity.append(row)

    if not sensitivity[-1]["ok"]:
        report["error"] = f"scaling failed on the chosen frame {chosen}"
        log.error(report["error"])
    else:
        report["reference_frame"] = {"frame_idx": chosen, "video_frame": int(frame_numbers[chosen]),
                                     "cameras_seeing": int(coverage[chosen])}
        report["summary"] = final["summary"]
        write_csv(os.path.join(out, "pairs.csv"), final["pairs"])
        write_csv(os.path.join(out, "cameras.csv"), final["cameras"])
    write_csv(os.path.join(out, "ref_frames.csv"), sensitivity)
    with open(os.path.join(out, "metrics.json"), "w") as f:
        json.dump(report, f, indent=2)
    log.info(f"Metrics written to {out}")
    return 0 if "summary" in report else 1


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
