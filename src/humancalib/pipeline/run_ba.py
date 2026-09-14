#!/usr/bin/env python3
"""Bundle adjustment runner with out-of-memory retry.

Runs ``humancalib.calibration.ba`` in a fresh subprocess and, if it fails --
typically out of memory on a long session -- retries with ``--frame_skip``
raised by 5, up to 60.

The subprocess is the point, not an accident of history: a process that has hit
an allocation failure cannot be trusted to have released its memory, so every
attempt must start clean. It is the one calibration step the Python CLI does not
run in-process.

Usage:
    python -m humancalib.pipeline.run_ba --prefix OUTPUT_DIR [--frame_skip 10]
        [--target linear_1_0] [--conf_threshold 0.5] [--ba_jac analytic] ...

The former form, 13 positional arguments (PREFIX AID PID GID FRAME_SKIP LAMBDA1
LAMBDA2 TARGET DATASET OBS_MASK SAVE_OBS_MASK [CONF_THRESHOLD] [BA_JAC]), is
still accepted so existing scripts keep working, but it is deprecated: two bare
`false true` tokens in the middle of a command line say nothing about what they
switch.
"""
import argparse
import subprocess
import sys
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)

MAX_FRAME_SKIP = 60
FRAME_SKIP_STEP = 5

BA_MODULE = "humancalib.calibration.ba"

_LEGACY_ORDER = ("prefix", "aid", "pid", "gid", "frame_skip", "lambda1", "lambda2",
                 "target", "dataset", "obs_mask", "save_obs_mask", "conf_threshold",
                 "ba_jac")


class BundleAdjustmentFailed(RuntimeError):
    """Every attempt failed, up to the frame-skip cap."""


def build_parser():
    p = argparse.ArgumentParser(
        prog="python -m humancalib.pipeline.run_ba",
        description="Bundle adjustment with out-of-memory retry.",
    )
    p.add_argument("--prefix", required=True, help="Session output directory")
    p.add_argument("--frame_skip", type=int, default=10,
                   help="Initial frame subsampling; raised by 5 after each failure")
    p.add_argument("--aid", type=int, default=1)
    p.add_argument("--pid", type=int, default=1)
    p.add_argument("--gid", type=int, default=1)
    p.add_argument("--lambda1", type=float, default=1.0, help="3D-orientation term weight")
    p.add_argument("--lambda2", type=float, default=1.0, help="Bone-length term weight")
    p.add_argument("--target", default="linear_1_0",
                   help="Calibration to refine: results/<target>.json")
    p.add_argument("--dataset", default="MyDataset")
    p.add_argument("--obs_mask", default="false", help="Use the observation mask (true/false)")
    p.add_argument("--save_obs_mask", default="true", help="Save the observation mask (true/false)")
    p.add_argument("--conf_threshold", type=float, default=0.5)
    p.add_argument("--ba_jac", default="analytic", choices=["analytic", "numeric"])
    return p


def parse(argv):
    """Parse named options, or translate the deprecated positional form."""
    argv = list(argv)
    if len(argv) >= 11 and not argv[0].startswith("-"):
        log.error("NOTE: positional arguments to run_ba are deprecated; "
              "use named options (--prefix, --frame_skip, ...).")
        named = []
        for key, value in zip(_LEGACY_ORDER, argv):
            named += [f"--{key}", value]
        argv = named
    return build_parser().parse_args(argv)


def ba_command(opts, frame_skip):
    return [
        sys.executable, "-m", BA_MODULE,
        "--prefix", opts.prefix,
        "--aid", str(opts.aid),
        "--pid", str(opts.pid),
        "--gid", str(opts.gid),
        "--frame_skip", str(frame_skip),
        "--ba_lambda1", str(opts.lambda1),
        "--ba_lambda2", str(opts.lambda2),
        "--target", opts.target,
        "--dataset", opts.dataset,
        "--obs_mask", opts.obs_mask,
        "--th_obs_mask", "20",
        "--save_obs_mask", opts.save_obs_mask,
        "--conf_threshold", str(opts.conf_threshold),
        "--ba_jac", opts.ba_jac,
    ]


def run(opts, runner=subprocess.run):
    """Run until an attempt succeeds. Returns the frame skip that worked.

    Raises:
        BundleAdjustmentFailed: if every frame skip up to MAX_FRAME_SKIP failed.
    """
    frame_skip = opts.frame_skip
    while True:
        log.info(f"Attempting Bundle Adjustment with FRAME_SKIP={frame_skip}...")
        if runner(ba_command(opts, frame_skip)).returncode == 0:
            log.info(f"Bundle Adjustment successful with FRAME_SKIP={frame_skip}.")
            return frame_skip

        log.warning("Bundle Adjustment failed. This might be due to an out-of-memory error.")
        previous = frame_skip
        frame_skip += FRAME_SKIP_STEP
        if frame_skip > MAX_FRAME_SKIP:
            raise BundleAdjustmentFailed(
                f"Bundle Adjustment failed even with FRAME_SKIP up to {previous}.")
        log.info(f"Retrying with a larger frame skip: {frame_skip}...\n")


def main(argv=None):
    opts = parse(sys.argv[1:] if argv is None else argv)
    try:
        return run(opts)
    except BundleAdjustmentFailed as err:
        log.error(f"{err} Aborting.")
        sys.exit(1)


if __name__ == "__main__":
    setup_logging()
    main()
