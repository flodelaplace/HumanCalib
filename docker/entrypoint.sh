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
  demo              Run the bundled 4-camera demo with this image's pose engine,
                    writing to /output/demo (/output/demo_rtmpose in the RTMPose image)
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
    # --- GPU ---------------------------------------------------------------
    #
    # Two different failures look identical from the outside, and both end with
    # the pipeline quietly running on CPU about fifteen times slower. They are
    # separated here because the fixes are unrelated.
    #
    # An explicitly empty CUDA_VISIBLE_DEVICES means the operator asked for CPU;
    # that is a choice, not a fault, so neither check applies.
    if [ "${CUDA_VISIBLE_DEVICES-unset}" = "" ]; then
        echo "  NOTE: CUDA_VISIBLE_DEVICES is empty — running on CPU by request." >&2

    elif ! nvidia-smi -L >/dev/null 2>&1; then
        # (1) No GPU reached the container at all. Not fatal: CPU is a valid,
        # if slow, way to run the demo, and some machines have no GPU.
        echo "  NOTE: no NVIDIA device visible in the container. Pose extraction" >&2
        echo "        will run on CPU (hours, not minutes). Start the container" >&2
        echo "        with '--gpus all', or 'gpus: all' under compose." >&2

    elif ! "${PYTHON}" -c "import ctypes; ctypes.CDLL('libcudnn.so.8'); ctypes.CDLL('libcudart.so.11.0')" 2>/dev/null; then
        # (2) The GPU is right there and the driver works, but the CUDA runtime
        # libraries cannot be resolved by the loader. TensorFlow reports no
        # error for this -- it just returns an empty device list and carries on
        # using the CPU. That is the one case worth refusing to start for: the
        # machine can clearly do better, and a silent 15x slowdown is far more
        # expensive than stopping now. Checked with ctypes rather than by
        # importing TensorFlow, which would cost ~20 seconds on every run.
        echo "ERROR: this container can see a GPU, but cannot load the CUDA runtime" >&2
        echo "       libraries (libcudnn.so.8 / libcudart.so.11.0)." >&2
        echo "       Neither TensorFlow nor onnxruntime reports this: pose extraction" >&2
        echo "       would silently run on CPU, many times slower." >&2
        echo >&2
        echo "       The libraries ship inside the image's conda environment, so they" >&2
        echo "       must be on the loader path. The image sets this; if you overrode" >&2
        echo "       LD_LIBRARY_PATH at run time, append to it rather than replacing it:" >&2
        ENV_LIB="$(dirname "$(dirname "${PYTHON}")")/lib"
        TORCH_LIB="$(ls -d "${ENV_LIB}"/python3*/site-packages/torch/lib 2>/dev/null | head -1 || true)"
        echo "         LD_LIBRARY_PATH=${ENV_LIB}${TORCH_LIB:+:${TORCH_LIB}}:\$LD_LIBRARY_PATH" >&2
        echo >&2
        echo "       Currently: LD_LIBRARY_PATH=${LD_LIBRARY_PATH:-<empty>}" >&2
        echo "       To run on CPU deliberately instead, set CUDA_VISIBLE_DEVICES=\"\"" >&2
        exit 1
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

    # Model cache. Not mounting it costs a fresh model download per container.
    # Which cache depends on the image's engine: it used to warn about the
    # 708 MB MeTRAbs model even in the RTMPose image, which never downloads it.
    local cache size
    if [ "${HUMANCALIB_DEFAULT_ENGINE:-metrabs}" = "metrabs" ]; then
        cache="${TFHUB_CACHE_DIR:-/models/tfhub}"; size="~708 MB MeTRAbs model"
    else
        cache="${TORCH_HOME:-/models/torch}"; size="RTMPose/RTMDet models"
    fi
    if ! mountpoint -q "${cache}" 2>/dev/null; then
        if [ ! -d "${cache}" ] || [ -z "$(ls -A "${cache}" 2>/dev/null)" ]; then
            echo "  NOTE: ${cache} is empty and not a mounted volume; the ${size}" >&2
            echo "        will be downloaded and lost when this container exits." >&2
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
        if [ -n "${2:-}" ] && [ "${2#-}" = "${2}" ]; then
            # Not the shortcut. HOWTO.md's commands begin with a video folder
            # that is literally called `demo` -- `demo demo/Calib_scene.toml
            # ...` -- and this branch used to swallow that first word and
            # append the rest after its own arguments, so every documented
            # command failed with "unrecognized arguments". `demo` followed by
            # a positional argument is a pipeline command like any other.
            preflight
            exec bash "${REPO_ROOT}/scripts/calibrate.sh" "$@"
        fi
        shift
        preflight
        # Same invocation as the README quick demo, with the output redirected
        # to the mounted volume and the engine this image contains. Extra
        # arguments are appended, so `demo --ba_jac numeric` works.
        ENGINE="${HUMANCALIB_DEFAULT_ENGINE:-metrabs}"
        DEMO_OUT=/output/demo
        if [ "${ENGINE}" != "metrabs" ]; then
            DEMO_OUT="/output/demo_${ENGINE}"
        fi
        exec bash "${REPO_ROOT}/scripts/calibrate.sh" \
            "${REPO_ROOT}/demo" \
            "${REPO_ROOT}/demo/Calib_scene.toml" \
            "${DEMO_OUT}" \
            --pose_engine "${ENGINE}" \
            --height 1.78 \
            --ref_frame 5 \
            "$@"
        ;;
    *)
        preflight
        exec bash "${REPO_ROOT}/scripts/calibrate.sh" "$@"
        ;;
esac
