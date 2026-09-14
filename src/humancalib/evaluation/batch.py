"""Unattended evaluation batch on BioCV: prepare, calibrate, compare.

    python -m humancalib.evaluation.batch --root <BioCV> --work_root <results> \\
        --participants P03 P06 --trials WALK_01 RUN_01 --engines metrabs rtmpose

For every trial and engine, in that order:

1. prepare the trial folder (gold calibration, HumanCalib's intrinsics);
2. run HumanCalib, unless its bundle-adjustment result already exists --
   MeTRAbs natively, RTMPose in the humancalib-rtmpose Docker image, since the
   RTMPose stack (Python 3.8, torch 1.13) is only packaged there;
3. compare with the gold calibration, unless metrics.json already exists.

A failure is recorded and the batch moves on: a failed calibration is a result
(docs/EVALUATION_PROTOCOL.md, section 4), and one bad trial must not cost the
night. Re-running the same command resumes where it stopped.

Every step appends a row to <work_root>/batch_status.csv; logs go next to the
outputs (<trial>/<engine>_run.log, <trial>/eval/<engine>_compare.log).
"""
import argparse
import csv
import datetime
import json
import os
import shutil
import subprocess
import sys
import time

from humancalib.core.log import get_logger, setup_logging
from humancalib.evaluation import biocv

log = get_logger(__name__)

RTMPOSE_IMAGE = "humancalib-rtmpose:latest"
RTMPOSE_MODELS_VOLUME = "humancalib_humancalib-rtmpose-models"
STATUS_FIELDS = ["started", "participant", "trial", "engine", "step", "status", "seconds",
                 "kept_stage", "mre_px", "rel_rot_deg_median", "rel_dir_deg_median", "scale_ratio_median",
                 "gravity_deg", "abs4dof_pos_mm_median", "abs4dof_rot_deg_median", "note"]


def calibration_command(engine, video_dir, work, metrabs_python):
    """(argv, env) running HumanCalib for one engine."""
    toml = os.path.join(work, "input", "Calib_scene.toml")
    if engine == "metrabs":
        env = dict(os.environ, HUMANCALIB_METRABS_PYTHON=metrabs_python)
        exe = os.path.join(os.path.dirname(metrabs_python), "humancalib")
        return [exe, "run", video_dir, toml, os.path.join(work, engine), "cuda", "--pose_engine", "metrabs"], env
    uid, gid = os.getuid(), os.getgid()
    return ["docker", "run", "--rm", "--gpus", "all", "-u", f"{uid}:{gid}",
            "-v", f"{video_dir}:/input:ro", "-v", f"{work}:/output",
            "-v", f"{RTMPOSE_MODELS_VOLUME}:/models/torch",
            RTMPOSE_IMAGE, "/input", "/output/input/Calib_scene.toml", "/output/rtmpose", "cuda",
            "--pose_engine", "rtmpose"], dict(os.environ)


def wait_for(path, minutes):
    """True once `path` is reachable, polling for up to `minutes`.

    An external drive that drops out is not a calibration failure: recording
    every remaining trial as failed would turn one unplugged cable into a
    night of false results. The batch waits, then stops."""
    deadline = time.time() + 60 * minutes
    while True:
        try:
            if os.path.isdir(path) and os.listdir(path) is not None:
                return True
        except OSError:
            pass
        if time.time() >= deadline:
            return False
        log.warning(f"{path} is not reachable; waiting...")
        time.sleep(30)


def local_video_copy(video_dir, dest):
    """Copy a trial's videos to local disk for the Docker run.

    Bind-mounting a Windows drive (drvfs) into a container is slow, and its
    permission semantics break file copies inside the pipeline."""
    os.makedirs(dest, exist_ok=True)
    for name in sorted(os.listdir(video_dir)):
        if name.lower().endswith((".mp4", ".avi", ".mov", ".mkv")):
            shutil.copyfile(os.path.join(video_dir, name), os.path.join(dest, name))
    return dest


def run_logged(argv, log_path, env=None):
    with open(log_path, "w") as f:
        return subprocess.run(argv, stdout=f, stderr=subprocess.STDOUT, env=env).returncode


def append_status(path, row):
    new = not os.path.isfile(path)
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=STATUS_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow(row)


def metrics_row(metrics_path):
    with open(metrics_path) as f:
        m = json.load(f)
    row = {"kept_stage": m.get("kept_stage"), "note": m.get("error", "")}
    stage = m.get("stages", {}).get(m.get("kept_stage"), {})
    row["mre_px"] = stage.get("mre_px")
    row.update({k: v for k, v in m.get("summary", {}).items() if k in STATUS_FIELDS})
    return row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", required=True, help="BioCV dataset root")
    parser.add_argument("--work_root", required=True, help="results folder, one sub-folder per trial")
    parser.add_argument("--participants", nargs="+", required=True)
    parser.add_argument("--trials", nargs="+", required=True)
    parser.add_argument("--engines", nargs="+", default=["metrabs", "rtmpose"], choices=["metrabs", "rtmpose"])
    parser.add_argument("--metrabs_python", default=sys.executable,
                        help="Python of the environment with TensorFlow (default: this one)")
    parser.add_argument("--wait_minutes", type=float, default=20,
                        help="how long to wait for an unreachable dataset drive before stopping")
    args = parser.parse_args(argv)

    status = os.path.join(args.work_root, "batch_status.csv")
    os.makedirs(args.work_root, exist_ok=True)
    for participant in args.participants:
        for trial in args.trials:
            if not wait_for(args.root, args.wait_minutes):
                log.error(f"dataset root unreachable for {args.wait_minutes} min: stopping the batch")
                return 2
            work = os.path.join(args.work_root, f"{participant}_{trial}")
            base = {"participant": participant, "trial": trial}
            try:
                meta = biocv.prepare(args.root, participant, trial, work)
            except Exception as e:                        # missing video, unreadable calibration
                append_status(status, {**base, "started": _now(), "step": "prepare", "status": "failed",
                                        "note": str(e)})
                log.error(f"{participant}_{trial}: prepare failed: {e}")
                continue

            for engine in args.engines:
                row = {**base, "engine": engine}
                ba = os.path.join(work, engine, "results", "linear_1_0_ba.json")
                if not os.path.isfile(ba):
                    video_dir = meta["video_dir"]
                    if engine == "rtmpose":
                        video_dir = local_video_copy(video_dir, os.path.join(work, "_videos"))
                    argv_, env = calibration_command(engine, video_dir, work, args.metrabs_python)
                    log.info(f"{participant}_{trial} [{engine}]: calibrating...")
                    t0, started = time.time(), _now()
                    rc = run_logged(argv_, os.path.join(work, f"{engine}_run.log"), env)
                    if engine == "rtmpose":
                        shutil.rmtree(os.path.join(work, "_videos"), ignore_errors=True)
                    ok = rc == 0 and os.path.isfile(ba)
                    append_status(status, {**row, "started": started, "step": "calibrate",
                                           "status": "ok" if ok else "failed",
                                           "seconds": round(time.time() - t0), "note": "" if ok else f"exit {rc}"})
                    if not ok:
                        log.error(f"{participant}_{trial} [{engine}]: calibration failed (exit {rc})")
                        continue

                metrics = os.path.join(work, "eval", engine, "metrics.json")
                if not os.path.isfile(metrics):
                    os.makedirs(os.path.join(work, "eval"), exist_ok=True)
                    t0, started = time.time(), _now()
                    rc = run_logged([sys.executable, "-m", "humancalib.evaluation.compare", "--work", work,
                                     "--engine", engine], os.path.join(work, "eval", f"{engine}_compare.log"))
                    append_status(status, {**row, "started": started, "step": "compare",
                                           "status": "ok" if rc == 0 else "failed",
                                           "seconds": round(time.time() - t0),
                                           **(metrics_row(metrics) if os.path.isfile(metrics) else {})})
                    log.info(f"{participant}_{trial} [{engine}]: compare exit {rc}")
    return 0


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


if __name__ == "__main__":
    setup_logging()
    raise SystemExit(main())
