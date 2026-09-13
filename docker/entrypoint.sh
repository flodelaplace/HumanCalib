#!/bin/bash
# Container entrypoint for the HumanCalib image.
#
# Runs a few checks that turn the three most common container mistakes into a
# sentence instead of a stack trace fifteen minutes in, then hands over to the
# pipeline. Every step it launches goes through ${HUMANCALIB_PYTHON}, the
# absolute interpreter of the image's conda environment.
set -euo pipefail

REPO_ROOT="/opt/humancalib"
PYTHON="${HUMANCALIB_PYTHON:-/opt/conda/envs/humancalib/bin/python}"

usage() {
    cat <<'USAGE'
HumanCalib — multi-camera extrinsic calibration from human pose

  docker compose run --rm calib demo
  docker compose run --rm calib /input/session /input/session/calib.toml /output/run1 \
      --pose_engine metrabs --height 1.78 --ref_frame 5

Commands:
  demo              Run the bundled 4-camera demo, writing to /output/demo
  shell             Interactive bash inside the environment
  python ...        Run the environment's interpreter
  --help            This message

Anything else is passed straight to scripts/calibrate.sh:

  calibrate.sh <video_dir> <calib_toml> [output_dir] [device] [mode] [options]

Mount points:
  /input            Your videos and intrinsics (read-only is fine)
  /output           Results. Must be writable by the container user.
  /models/tfhub     Pose-model cache. Mount it, or the ~708 MB MeTRAbs model
                    is downloaded again for every container.
USAGE
}

preflight() {
    # GPU. A missing driver is not fatal -- the pipeline runs on CPU, just very
    # slowly -- but silence here is what makes people wonder why it crawls.
    if [ ! -e /dev/nvidiactl ] && ! command -v nvidia-smi >/dev/null 2>&1; then
        echo "  NOTE: no NVIDIA device visible in the container. Pose extraction" >&2
        echo "        will run on CPU (hours, not minutes). Start the container" >&2
        echo "        with '--gpus all', or 'gpus: all' under compose." >&2
    fi

    # Output must be writable. Running as the host user (recommended, so the
    # results are not owned by root) fails here if the directory was created by
    # a previous root-owned run.
    if [ ! -w /output ]; then
        echo "ERROR: /output is not writable by uid $(id -u)." >&2
        echo "       Either fix the ownership on the host, or drop the 'user:'" >&2
        echo "       override and let the container run as root." >&2
        exit 1
    fi

    # Model cache. Not mounting it costs a 708 MB download per container.
    local cache="${TFHUB_CACHE_DIR:-/models/tfhub}"
    if ! mountpoint -q "${cache}" 2>/dev/null; then
        if [ ! -d "${cache}" ] || [ -z "$(ls -A "${cache}" 2>/dev/null)" ]; then
            echo "  NOTE: ${cache} is empty and not a mounted volume; the pose" >&2
            echo "        model will be downloaded (~708 MB) and lost when this" >&2
            echo "        container exits." >&2
        fi
    fi
}

case "${1:-}" in
    ""|-h|--help|help)
        usage
        exit 0
        ;;
    shell|bash)
        shift
        exec bash "$@"
        ;;
    python)
        shift
        exec "${PYTHON}" "$@"
        ;;
    demo)
        shift
        preflight
        # Same invocation as the README quick demo, with the output redirected
        # to the mounted volume. Extra arguments are appended, so
        # `demo --ba_jac numeric` works.
        exec bash "${REPO_ROOT}/scripts/calibrate.sh" \
            "${REPO_ROOT}/demo" \
            "${REPO_ROOT}/demo/Calib_scene.toml" \
            /output/demo \
            --pose_engine metrabs \
            --height 1.78 \
            --ref_frame 5 \
            "$@"
        ;;
    *)
        preflight
        exec bash "${REPO_ROOT}/scripts/calibrate.sh" "$@"
        ;;
esac
