"""Write the per-run session file (pipeline step 3).

Replaces a 17-line Python heredoc embedded in calibrate.sh, which wrote the
repository-level config/config.yaml. Being a module rather than a string inside
a shell script, it is versioned, importable and testable.

Camera and joint counts are read from the artefacts the previous steps just
produced; frame size and rate are probed from the actual videos rather than
hardcoded.
"""
import argparse
import glob
import json
import os
import sys


from humancalib.core.session import write_session
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output_dir", required=True)
    parser.add_argument("--subset", required=True)
    parser.add_argument("--video_dir", required=True)
    parser.add_argument("--aid", type=int, required=True)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--gid", type=int, required=True)
    args = parser.parse_args(argv)

    subset_dir = os.path.join(args.output_dir, args.subset)

    cam_file = os.path.join(subset_dir, f"cameras_G{args.gid:03d}.json")
    if not os.path.exists(cam_file):
        log.error(f"{cam_file} not found (step 2 must run first).")
        return 1
    with open(cam_file) as f:
        n_cams = len(json.load(f)["CAMID"])

    pattern = os.path.join(
        subset_dir, "2d_joint",
        f"A{args.aid:03d}_P{args.pid:03d}_G{args.gid:03d}_C*.json",
    )
    jfiles = sorted(glob.glob(pattern))
    if not jfiles:
        log.error(f"no 2D pose files matching {pattern} "
              f"(step 1 must run first).")
        return 1
    with open(jfiles[0]) as f:
        jdata = json.load(f)
    n_frames = len(jdata["data"])
    n_joints = len(jdata["data"][0]["skeleton"][0]["score"])

    path = write_session(
        output_dir=args.output_dir,
        subset=args.subset,
        camera_ids=range(1, n_cams + 1),
        available_joints=range(n_joints),
        aid=args.aid,
        pid=args.pid,
        gid=args.gid,
        video_dir=args.video_dir,
    )
    log.info(f"Session written: {n_cams} cameras, {n_frames} frames, "
          f"{n_joints} joints -> {path}")
    return 0


if __name__ == "__main__":
    setup_logging()
    sys.exit(main())
