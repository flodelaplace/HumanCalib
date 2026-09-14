"""HumanCalib command line.

    humancalib run VIDEO_DIR CALIB_TOML [OUTPUT_DIR] [cuda|cpu]
                   [lightweight|balanced|performance] [options]
    humancalib STEP [step options]          (humancalib --help lists the steps)

``humancalib run`` is the whole pipeline. It carries the logic that used to be
scripts/calibrate.sh -- now a few lines forwarding here -- and it accepts that
script's command line unchanged, bare device and mode words included, so every
command in HOWTO.md works exactly as written.

What changed is how the steps talk to each other. calibrate.sh launched each
one as a separate interpreter and recovered results by searching what it
printed: the MRE was the fourth whitespace-separated token of a line containing
"Global MRE", the number of dropped frames came from a line starting
"NEW_DROPS=". Here each step's ``main(argv)`` is called and returns its result.

Three steps still run in their own process, each for a stated reason:

* pose extraction -- TensorFlow and PyTorch keep GPU memory until their process
  exits, and MeTRAbs may live in another conda environment altogether;
* bundle adjustment -- its out-of-memory retry needs every attempt to start in
  a clean process (humancalib.pipeline.run_ba);
* visualisation -- memory-heavy animation rendering whose failure the pipeline
  has always tolerated, and which must not take a finished calibration with it.
"""
import argparse
import datetime
import importlib
import importlib.util
import logging
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)

# Vestigial dataset identifiers: they only shape artefact file names. See
# docs/REFACTOR_PLAN.md (T4.4).
AID = PID = GID = 1
SUBSET = "noise_1_0"
DATASET = "MyDataset"
VP3D_MODEL = "pretrained_h36m_detectron_coco.bin"
LAMBDA1 = LAMBDA2 = 1.0

DEVICES = ("cuda", "cpu")
ENGINES = ("rtmpose", "metrabs")
MODES = ("lightweight", "balanced", "performance")
RULE = "━" * 62

STEPS = {
    "extract-metrabs": ("humancalib.pose.metrabs_inference", "MeTRAbs 2D+3D pose extraction"),
    "extract-rtmpose": ("humancalib.pose.rtmlib_inference", "RTMPose 2D pose extraction"),
    "lift": ("humancalib.pose.inference", "VideoPose3D 2D->3D lifting (RTMPose path)"),
    "cameras": ("humancalib.pipeline.create_cameras_from_toml", "intrinsics TOML -> cameras JSON"),
    "session": ("humancalib.pipeline.write_session", "write the session file"),
    "linear": ("humancalib.pipeline.run_calib_linear", "chunked linear calibration"),
    "outliers": ("humancalib.pipeline.detect_outlier_frames", "per-camera outlier-frame drop"),
    "ba": ("humancalib.pipeline.run_ba", "bundle adjustment with OOM retry"),
    "evaluate": ("humancalib.postprocessing.evaluate_calibration", "MRE evaluation"),
    "visualize": ("humancalib.postprocessing.visualize_results", "3D animation / TRC export"),
    "scale": ("humancalib.postprocessing.scale_scene", "metric scaling and orientation"),
}


class PipelineError(RuntimeError):
    """A step failed; the message says which and why."""


# --- command line ---------------------------------------------------------------

def build_run_parser():
    p = argparse.ArgumentParser(
        prog="humancalib run",
        usage="humancalib run VIDEO_DIR CALIB_TOML [OUTPUT_DIR] [cuda|cpu] "
              "[lightweight|balanced|performance] [options]",
        description="Run the full extrinsic calibration pipeline.",
    )
    p.add_argument("video_dir", help="Folder containing the synchronised videos")
    p.add_argument("calib_toml", help="Intrinsics TOML (Pose2Sim format)")
    p.add_argument("output_dir", nargs="?", default=None,
                   help="Output folder (default: ./data/session_<timestamp>)")
    p.add_argument("--device", choices=DEVICES, default="cuda")
    p.add_argument("--mode", choices=MODES, default="balanced", help="RTMPose model size")
    p.add_argument("--pose_engine", choices=ENGINES, default=default_engine(),
                   help="metrabs is recommended. Default: rtmpose, as calibrate.sh had it, "
                        "unless HUMANCALIB_DEFAULT_ENGINE says otherwise -- each Docker "
                        "image sets it to the one backend it contains")
    p.add_argument("--height", type=float, default=None, help="Subject height in metres")
    p.add_argument("--ref_frame", type=int, default=None,
                   help="Absolute frame where the subject stands straight")
    p.add_argument("--start_frame", type=int, default=None)
    p.add_argument("--end_frame", type=int, default=None)
    p.add_argument("--frame_skip", type=int, default=10)
    p.add_argument("--conf_threshold", type=float, default=0.5)
    p.add_argument("--save_video", action="store_true", help="RTMPose overlay video")
    p.add_argument("--auto_outlier_drop", dest="auto_outlier_drop", action="store_true", default=True)
    p.add_argument("--no_auto_outlier_drop", dest="auto_outlier_drop", action="store_false")
    p.add_argument("--outlier_abs_px", type=float, default=50.0)
    p.add_argument("--outlier_x_median", type=float, default=5.0)
    p.add_argument("--ref_cam", type=int, default=None)
    p.add_argument("--ba_jac", choices=("analytic", "numeric"), default="analytic")
    return p


def default_engine(environ=None):
    """The pose engine used when --pose_engine is not given.

    rtmpose, as calibrate.sh always defaulted, so documented commands keep their
    meaning. Each Docker image contains exactly one backend and declares it in
    HUMANCALIB_DEFAULT_ENGINE; without that, a command that omits the flag failed
    in the main image, which has no RTMPose, and in the RTMPose image, which has
    no TensorFlow.
    """
    value = (os.environ if environ is None else environ).get("HUMANCALIB_DEFAULT_ENGINE", "")
    return value if value in ENGINES else "rtmpose"


def parse_run_args(argv):
    """calibrate.sh's command line, parsed.

    Positions 4 and 5 of that script were bare words -- `cuda balanced` -- that
    it recognised anywhere after the first three arguments. They are translated
    to --device/--mode here. Carriage returns are stripped from every argument,
    as the script did: a command line pasted from a Windows editor otherwise
    carries a trailing '\r' into a number and fails to parse.
    """
    tokens = [a.replace("\r", "").replace("\n", "") for a in argv]
    positional, rest = tokens[:2], tokens[2:]
    if rest and not rest[0].startswith("-") and rest[0] not in DEVICES + MODES:
        positional.append(rest.pop(0))

    options, device, mode = [], None, None
    for i, tok in enumerate(rest):
        after_flag = i > 0 and rest[i - 1] in ("--device", "--mode")
        if tok in DEVICES and not after_flag:
            device = tok
        elif tok in MODES and not after_flag:
            mode = tok
        else:
            options.append(tok)
    if device:
        options += ["--device", device]
    if mode:
        options += ["--mode", mode]

    cfg = build_run_parser().parse_args(positional + options)
    if cfg.output_dir is None:
        cfg.output_dir = os.path.join(
            "data", "session_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))
    cfg.video_dir = os.path.abspath(cfg.video_dir)
    cfg.calib_toml = os.path.abspath(cfg.calib_toml)
    cfg.output_dir = os.path.abspath(cfg.output_dir)
    return cfg


# --- environment ----------------------------------------------------------------------

def package_root():
    """The directory that contains the humancalib package (src/ or site-packages)."""
    return Path(__file__).resolve().parents[1]


def repo_root():
    """The source checkout, if this is one. None for an installed package.

    Only the RTMPose/VideoPose3D path needs it: its weights are resolved as
    ./model/<file> relative to the checkout, a frozen legacy convention.
    """
    candidate = Path(__file__).resolve().parents[2]
    return candidate if (candidate / "scripts" / "calibrate.sh").is_file() else None


def _torch_lib_dir():
    """PyTorch's bundled library directory, located without importing torch."""
    try:
        spec = importlib.util.find_spec("torch")
    except (ImportError, ValueError):
        return None
    if spec is None or not spec.origin:
        return None
    return os.path.join(os.path.dirname(spec.origin), "lib")


def child_env(environ=None, isdir=os.path.isdir, prefix=None, exists=os.path.exists,
              torch_lib="auto"):
    """Environment for the steps that run in their own process."""
    env = dict(os.environ if environ is None else environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in (str(package_root()), env.get("PYTHONPATH")) if p)
    env["PYTHONUNBUFFERED"] = "1"
    # WSL2 exposes the Windows driver's libcuda here, off the default loader
    # path. Only where it exists: prepending it unconditionally shadowed the
    # driver stubs the NVIDIA container runtime injects.
    wsl = "/usr/lib/wsl/lib"

    # The CUDA runtime installed by envs/calib.yaml lives in the environment's
    # lib/, which is NOT on the loader path: `conda activate` does not add it --
    # neither cudatoolkit nor cudnn ships an activate.d script that does -- and
    # TensorFlow 2.12 finds libcudart and libcudnn only through the loader. So a
    # native install that followed the README exactly (create, activate, run)
    # ran pose extraction on CPU. It has to be set before the step's interpreter
    # starts, which is why it is done here. Added only when that runtime is
    # actually present, and never twice: the Docker image sets it already.
    lib = os.path.join(sys.prefix if prefix is None else prefix, "lib")

    # Empty components are dropped, not preserved: an empty entry makes the
    # loader search the current directory. Libraries this process imports leave
    # them behind -- opencv prepends its own directory to an empty variable and
    # a trailing separator remains.
    paths = [p for p in env.get("LD_LIBRARY_PATH", "").split(os.pathsep) if p]
    if isdir(wsl) and wsl not in paths:
        paths.insert(0, wsl)
    if exists(os.path.join(lib, "libcudart.so.11.0")) and lib not in paths:
        paths.insert(0, lib)

    # The RTMPose environment adds a second trap: PyTorch keeps cuDNN in its own
    # package directory, and onnxruntime's CUDA provider needs it. Without it,
    # RTMPose silently ran on CPU. Appended after the environment's lib/, so a
    # cuDNN installed at the environment level still takes precedence.
    tlib = _torch_lib_dir() if torch_lib == "auto" else torch_lib
    if tlib and exists(os.path.join(tlib, "libcudnn.so.8")) and tlib not in paths:
        paths.append(tlib)
    if paths:
        env["LD_LIBRARY_PATH"] = os.pathsep.join(paths)
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


def _conda_env_names():
    try:
        out = subprocess.run(["conda", "env", "list"], capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {line.split()[0] for line in out.splitlines()
            if line.strip() and not line.startswith("#")}


def resolve_metrabs_launcher(environ=None, which=shutil.which, conda_env_names=_conda_env_names):
    """Command prefix that runs a Python module with TensorFlow available.

    The documented installs -- envs/calib.yaml and the Docker image -- keep
    TensorFlow in the same environment as everything else, so that is the
    default. A separate `metrabs_opensim` conda environment, the layout of the
    original development machine, is used only if it exists: calling it
    unconditionally made step 1 fail on every other machine.
    HUMANCALIB_METRABS_PYTHON overrides both with a command line of its own.
    """
    environ = os.environ if environ is None else environ
    override = environ.get("HUMANCALIB_METRABS_PYTHON", "").strip()
    if override:
        return shlex.split(override)
    if which("conda") and "metrabs_opensim" in conda_env_names():
        return ["conda", "run", "--live-stream", "-n", "metrabs_opensim", "python", "-u"]
    return [sys.executable, "-u"]


# --- step plumbing ----------------------------------------------------------------------

def run_step(name, func, argv):
    """Call a step's main(argv) in-process and return what it returns.

    Steps still end with sys.exit() on error, as scripts do. Here that becomes
    a PipelineError naming the step, instead of silently ending the whole
    program -- and a clean sys.exit(0) is not a failure.
    """
    try:
        return func(argv)
    except SystemExit as err:
        if err.code in (0, None):
            return None
        raise PipelineError(f"step '{name}' failed (exit status {err.code})") from None


def run_process(name, cmd, env, cwd=None, check=True):
    rc = subprocess.run(cmd, env=env, cwd=cwd).returncode
    if rc != 0 and check:
        raise PipelineError(f"step '{name}' failed (exit status {rc})")
    return rc


def map_ref_frame(ref_frame, start_frame, end_frame):
    """Index of --ref_frame within the cropped arrays, or None if outside the range.

    --ref_frame is an absolute video frame number; once the session is cropped
    at --start_frame, index 0 is that frame.
    """
    if start_frame is None:
        return ref_frame
    if ref_frame < start_frame or (end_frame is not None and ref_frame > end_frame):
        return None
    return ref_frame - start_frame


def best_calibration(scores):
    """Name with the lowest MRE; on a tie the earlier stage wins, as before."""
    best = None
    for name, mre in scores.items():
        if best is None or mre < scores[best]:
            best = name
    return best


def format_summary(scores, best, output_dir, scaling_requested):
    results = os.path.join(output_dir, "results")
    lines = [
        "", "╔" + "═" * 62 + "╗",
        "║                      ✅  DONE !                              ║",
        "╠" + "═" * 62 + "╣",
        f"║  Results in : {results}/",
        "╠" + "═" * 62 + "╣",
        "║  \U0001F4CA MRE Summary Table (Mean Reprojection Error)              ║",
        "║" + "─" * 62 + "║",
        "║ %-25s | %s" % ("Method", "MRE (pixels)"),
        "║" + "─" * 62 + "║",
    ]
    for name, mre in scores.items():
        mark = "⭐ " if name == best else "  "
        lines.append("║%s%-24s | %.3f" % (mark, name, mre))
    lines.append("║" + "─" * 62 + "║")

    final_toml = os.path.join(results, "Calib_scene_calibrated.toml")
    if os.path.isfile(final_toml):
        lines.append("║  Final TOML file generated:")
        lines.append(f"║    results/{os.path.basename(final_toml)}")
        for label, rel in (("Final TRC file (3D Poses):", "3d_skeleton_FINAL.trc"),
                           ("Final visualization:", "camera/visu_3d_FINAL.gif")):
            if os.path.isfile(os.path.join(results, rel)):
                lines += [f"║  {label}", f"║    results/{rel}"]
    elif scaling_requested:
        # calibrate.sh announced a final TOML here even when scaling had been
        # skipped for an out-of-range --ref_frame. Report what exists instead.
        lines.append("║  Scaling was requested but produced no final TOML --")
        lines.append("║  see the messages from step 7 above.")
    else:
        lines.append("║  To generate a final TOML, rerun with options:")
        lines.append("║    --height <h> --ref_frame <f>")
    lines.append("╚" + "═" * 62 + "╝")
    return "\n".join(lines)


def _header(title):
    log.info(f"\n{RULE}\n{title}\n{RULE}")


def preflight(cfg):
    """Fail in the first second, not fifteen minutes in."""
    from humancalib.core.videos import VIDEO_PATTERNS, list_videos

    if not os.path.isdir(cfg.video_dir):
        raise PipelineError(f"video directory not found: {cfg.video_dir}")
    if not os.path.isfile(cfg.calib_toml):
        raise PipelineError(f"intrinsics TOML not found: {cfg.calib_toml}")
    if not list_videos(cfg.video_dir):
        raise PipelineError(f"no videos in {cfg.video_dir} (looked for {', '.join(VIDEO_PATTERNS)})")
    if cfg.pose_engine == "rtmpose" and importlib.util.find_spec("rtmlib") is None:
        raise PipelineError(
            "the RTMPose backend is not installed in this environment. Pass "
            "--pose_engine metrabs (recommended, and the only backend in the main "
            "Docker image), or install envs/rtmpose.yaml.")


# --- the pipeline -----------------------------------------------------------------------

def run_pipeline(cfg):
    preflight(cfg)

    from humancalib.core.videos import camera_names
    from humancalib.pipeline import (create_cameras_from_toml, detect_outlier_frames,
                                     run_ba, run_calib_linear, write_session)
    from humancalib.pipeline.frame_mapping import write_frame_mapping
    from humancalib.pipeline.poses_cache import poses_are_cached
    from humancalib.postprocessing import evaluate_calibration, scale_scene

    env = child_env()
    out, vd, sub = cfg.output_dir, cfg.video_dir, os.path.join(cfg.output_dir, SUBSET)
    ids = ["--aid", str(AID), "--pid", str(PID), "--gid", str(GID)]
    frames = ((["--start_frame", str(cfg.start_frame)] if cfg.start_frame is not None else [])
              + (["--end_frame", str(cfg.end_frame)] if cfg.end_frame is not None else []))

    log.info("\n╔" + "═" * 62 + "╗")
    log.info("║          Extrinsic Camera Calibration Pipeline               ║")
    log.info("╠" + "═" * 62 + "╣")
    log.info(f"║  Video Dir  : {vd}")
    log.info(f"║  Calib TOML : {cfg.calib_toml}")
    log.info(f"║  Output Dir : {out}")
    log.info(f"║  Pose Engine: {cfg.pose_engine}")
    log.info(f"║  Device     : {cfg.device}         Mode: {cfg.mode}")
    log.info(f"║  Frame Skip : {cfg.frame_skip}             Conf Threshold: {cfg.conf_threshold}")
    if cfg.start_frame is not None:
        log.info(f"║  Calib Range: Frames {cfg.start_frame} to {cfg.end_frame}")
    if cfg.height is not None:
        log.info(f"║  Scaling    : Height={cfg.height}m, Ref Frame={cfg.ref_frame}")
    log.info("╚" + "═" * 62 + "╝")
    os.makedirs(out, exist_ok=True)

    # 1. Pose extraction ------------------------------------------------------------------
    rng = f"  -> frame range: {cfg.start_frame or 0} to {cfg.end_frame if cfg.end_frame is not None else '<end>'}"
    if cfg.pose_engine == "metrabs":
        _header("[1/7] Extracting 2D+3D poses with MeTRAbs (replaces steps 1+4)...")
        log.info(rng)
        cached = poses_are_cached(out, SUBSET, cfg.start_frame, cfg.end_frame)
        if cached:
            log.info(f"  -> Found existing poses: {cached.n_cameras} cameras, {cached.n_frames} frames "
                  f"({cached.start}-{cached.end})")
            log.info("  -> Skipping MeTRAbs inference (reusing cached results)")
        else:
            run_process("extract-metrabs", resolve_metrabs_launcher() + [
                "-m", "humancalib.pose.metrabs_inference",
                "--video_dir", vd, "--calib_toml", cfg.calib_toml, "--output_dir", out,
                *ids, "--subset_name", SUBSET, "--batch_size", "8", *frames], env)
    else:
        _header("[1/7] Extracting 2D poses with RTMPose...")
        log.info(rng)
        run_process("extract-rtmpose", [
            sys.executable, "-u", "-m", "humancalib.pose.rtmlib_inference",
            "--video_dir", vd, "--output_dir", out, *ids, "--subset_name", SUBSET,
            "--device", cfg.device, "--mode", cfg.mode, *frames,
            *(["--save_video"] if cfg.save_video else [])], env)

    # 2. Intrinsics -------------------------------------------------------------------------
    _header("[2/7] Reading intrinsics from TOML...")
    run_step("cameras", create_cameras_from_toml.main, [
        "--toml", cfg.calib_toml, "--output_dir", sub, "--gid", str(GID),
        "--cam_names", *camera_names(vd)])

    if cfg.start_frame is not None and cfg.end_frame is not None:
        _header("[2.5] Creating frame mapping file...")
        path = write_frame_mapping(out, SUBSET, GID, cfg.start_frame, cfg.end_frame)
        log.info(f"  -> Compatible mapping file created: {path}")

    # 3. Session ------------------------------------------------------------------------------
    _header("[3/7] Updating configuration...")
    if run_step("session", write_session.main, [
            "--output_dir", out, "--subset", SUBSET, "--video_dir", vd, *ids]) not in (0, None):
        raise PipelineError("step 'session' failed")

    # 4. Lifting ------------------------------------------------------------------------------
    if cfg.pose_engine == "metrabs":
        _header("[4/7] Skipped (3D already extracted by MeTRAbs in step 1)")
    else:
        _header("[4/7] Lifting 2D -> 3D with VideoPose3D...")
        run_process("lift", [
            sys.executable, "-u", "-m", "humancalib.pose.inference",
            "--prefix", out, *ids, "--target", SUBSET, "--dataset", DATASET,
            "--model", VP3D_MODEL, "--device", cfg.device], env, cwd=repo_root())

    # 5. Calibration ----------------------------------------------------------------------------
    _header("[5/7] Extrinsic calibration...")
    log.info("  → Running linear calibration by chunks...")
    linear_argv = (["--conf_threshold", str(cfg.conf_threshold)]
                   + (["--ref_cam", str(cfg.ref_cam)] if cfg.ref_cam is not None else [])
                   + [out, str(AID), str(PID), str(GID), SUBSET, str(cfg.frame_skip), DATASET])
    run_step("linear", run_calib_linear.main, linear_argv)

    linear_json = os.path.join(out, "results", "linear_1_0.json")
    if not os.path.isfile(linear_json):
        raise PipelineError(f"linear calibration result not found: {linear_json}. "
                            "Bundle adjustment not attempted; see the linear step's output above.")

    if cfg.auto_outlier_drop:
        log.info("\n  → Detecting outlier frames (per camera)...")
        new_drops = run_step("outliers", detect_outlier_frames.main, [
            "--prefix", out, "--subset", SUBSET, *ids, "--calib", "linear_1_0",
            "--video_dir", vd, "--abs_px", str(cfg.outlier_abs_px),
            "--x_median", str(cfg.outlier_x_median), "--conf_threshold", str(cfg.conf_threshold)])
        if new_drops:
            log.info(f"\n  → Re-running linear calibration on cleaned data ({new_drops} outliers dropped)...")
            run_step("linear", run_calib_linear.main, linear_argv)

    log.info("  → Bundle Adjustment (linear)...")
    run_step("ba", run_ba.main, [
        "--prefix", out, "--frame_skip", str(cfg.frame_skip),
        "--lambda1", str(LAMBDA1), "--lambda2", str(LAMBDA2), "--target", "linear_1_0",
        "--dataset", DATASET, "--obs_mask", "false", "--save_obs_mask", "true",
        "--conf_threshold", str(cfg.conf_threshold), "--ba_jac", cfg.ba_jac])

    # 6. Evaluation -------------------------------------------------------------------------------
    _header("[6/7] Evaluation and Visualization...")
    scores = {}
    for calib in ("linear_1_0", "linear_1_0_ba"):
        if not os.path.isfile(os.path.join(out, "results", f"{calib}.json")):
            continue
        mre = run_step("evaluate", evaluate_calibration.main, [
            "--prefix", out, "--calib", calib, "--video_dir", vd, "--visualize",
            "--conf_threshold", str(cfg.conf_threshold),
            *(["--start_frame", str(cfg.start_frame)] if cfg.start_frame is not None else [])])
        if mre is not None:
            scores[calib] = float(mre)
        log.info(f"  → 3D Visualization for {calib}...")
        if run_process("visualize", [
                sys.executable, "-m", "humancalib.postprocessing.visualize_results",
                "--prefix", out, "--subset", SUBSET, "--calib", calib, "--dataset", DATASET,
                "--output", os.path.join(out, "results", "camera", f"visu_3d_{calib}.gif"),
                "--conf_threshold", str(cfg.conf_threshold)], env, check=False) != 0:
            log.warning(f"Visu {calib} failed")
    best = best_calibration(scores)

    # 7. Scaling ----------------------------------------------------------------------------------
    scaling_requested = cfg.height is not None and cfg.ref_frame is not None
    if scaling_requested and best:
        _header("[7/7] Scaling, Orientation and Final Visualization...")
        mapped = map_ref_frame(cfg.ref_frame, cfg.start_frame, cfg.end_frame)
        if mapped is None:
            log.error(f"--ref_frame {cfg.ref_frame} is outside the calibration range")
            log.info(f"         [--start_frame {cfg.start_frame}, --end_frame "
                  f"{cfg.end_frame if cfg.end_frame is not None else '<end>'}].")
            log.info("         --ref_frame expects an ABSOLUTE video frame number within the")
            log.info("         cropped range. Scaling skipped -- linear and BA calibrations are saved.")
        else:
            if cfg.start_frame is not None:
                log.info(f"  -> Reference frame re-mapped from {cfg.ref_frame} to index {mapped} "
                      "to match cropped data.")
            run_step("scale", scale_scene.main, [
                "--prefix", out, "--calib", best, "--height", str(cfg.height),
                "--frame_idx", str(mapped), "--input_toml", cfg.calib_toml,
                "--export_toml", os.path.join(out, "results", "Calib_scene_calibrated.toml"),
                "--video_dir", vd, "--conf_threshold", str(cfg.conf_threshold),
                "--pose_engine", cfg.pose_engine])

            final = f"{best}_oriented_scaled"
            if os.path.isfile(os.path.join(out, "results", f"{final}.json")):
                log.info("  → Final visualization...")
                run_process("visualize", [
                    sys.executable, "-m", "humancalib.postprocessing.visualize_results",
                    "--prefix", out, "--subset", SUBSET, "--calib", final, "--dataset", DATASET,
                    "--output", os.path.join(out, "results", "camera", "visu_3d_FINAL.gif"),
                    "--export_trc", os.path.join(out, "results", "3d_skeleton_FINAL.trc"),
                    "--conf_threshold", str(cfg.conf_threshold)], env)

    log.info(format_summary(scores, best, out, scaling_requested))
    return 0


# --- entry point ------------------------------------------------------------------------------

def _usage():
    width = max(len(k) for k in STEPS)
    steps = "\n".join(f"  {k:<{width}}  {desc}" for k, (_, desc) in STEPS.items())
    return (
        "usage: humancalib [--verbose|--quiet] run VIDEO_DIR CALIB_TOML [OUTPUT_DIR] [cuda|cpu] "
        "[lightweight|balanced|performance] [options]\n"
        "       humancalib STEP [step options]\n\n"
        "  run  the full pipeline (humancalib run --help for its options)\n"
        "  --verbose / --quiet  more detail, or only problems (or HUMANCALIB_LOG_LEVEL)\n\n"
        f"Steps, each runnable on its own:\n{steps}\n")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)

    # --verbose / --quiet before the command, or anywhere in `humancalib run`.
    # The level is exported to HUMANCALIB_LOG_LEVEL, so steps running in their
    # own process follow it too.
    level = None
    while argv and argv[0] in ("-v", "--verbose", "-q", "--quiet"):
        level = logging.DEBUG if argv.pop(0) in ("-v", "--verbose") else logging.WARNING
    if argv[:1] == ["run"]:
        for flag, flag_level in (("--verbose", logging.DEBUG), ("--quiet", logging.WARNING)):
            while flag in argv:
                argv.remove(flag)
                level = flag_level
    setup_logging(level)

    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_usage())
        return 0
    if argv[0] == "--version":
        from humancalib import __version__
        print(__version__)
        return 0

    command, rest = argv[0], argv[1:]
    if command == "run":
        try:
            return run_pipeline(parse_run_args(rest))
        except PipelineError as err:
            log.error(f"{err}")
            return 1

    if command not in STEPS:
        print(f"humancalib: unknown command '{command}'\n\n{_usage()}", file=sys.stderr)
        return 2
    module_name = STEPS[command][0]
    if command in ("extract-metrabs", "extract-rtmpose", "lift"):
        # Their own process, as in `humancalib run`: GPU memory is only released
        # when a process exits, and the CUDA libraries must be on the loader
        # path before the interpreter starts -- from inside this one, importing
        # TensorFlow here, it would already be too late.
        return subprocess.call([sys.executable, "-m", module_name, *rest], env=child_env(),
                               cwd=repo_root() if command == "lift" else None)
    result = importlib.import_module(module_name).main(rest)
    return result if command == "session" else 0


if __name__ == "__main__":
    sys.exit(main())
