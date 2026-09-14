# syntax=docker/dockerfile:1
#
# HumanCalib — main image (MeTRAbs backend, MIT-licensed path only)
#
#   docker build -t humancalib .
#   docker compose run --rm calib demo
#
# The optional RTMPose + VideoPose3D backend is a separate image, because it
# carries a non-commercial licence that must not silently attach itself to the
# default one. See Dockerfile.rtmpose.

# --- Base -------------------------------------------------------------------
#
# Plain Ubuntu, not nvidia/cuda. The CUDA userspace TensorFlow needs
# (cudatoolkit 11.8 + cuDNN 8.9) is declared in envs/calib.yaml and installed
# by conda, exactly as in a native install; only the driver comes from the
# host, injected by the NVIDIA container runtime. A CUDA base image would ship
# a second, independently-built copy of those same libraries on the loader
# path -- around 1.8 GB of duplication whose only effect is the chance of
# binding against the wrong one. One CUDA, from one declaration, is both
# smaller and what makes "same spec in the container as on the host" true.
FROM ubuntu:22.04

# Consumed by the NVIDIA container runtime; normally inherited from a CUDA base
# image, so they have to be stated explicitly here.
ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

# --- System packages --------------------------------------------------------
#
# libgl1 + libglib2.0-0: shared objects opencv links against, absent from the
#   slim Ubuntu base -- their absence shows up as `ImportError: libGL.so.1`.
# ffmpeg is NOT installed here: envs/calib.yaml already brings one, and the
#   environment's bin/ is first on PATH, so matplotlib's animation writer finds
#   it. Installing the apt one too would put two builds on PATH.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        ca-certificates \
        bzip2 \
    && rm -rf /var/lib/apt/lists/*

# --- Environment ------------------------------------------------------------
#
# micromamba rather than a full conda/miniconda install: a single static
# binary, no base environment, and no Anaconda `defaults` channel configured
# behind your back (whose Terms of Service require a paid licence for larger
# organisations -- see the channel comment in envs/calib.yaml).
COPY --from=mambaorg/micromamba:1.5.8 /bin/micromamba /usr/local/bin/micromamba

ENV MAMBA_ROOT_PREFIX=/opt/conda
ENV HUMANCALIB_ENV=/opt/conda/envs/humancalib

# Downloading a conda environment this size (cudatoolkit alone is ~700 MB) over
# a slow or flaky link is the single most common reason this build fails.
# libmamba's defaults give up quickly -- curl error 28, "Timeout was reached",
# usually its low-speed cutoff rather than a genuinely dead connection. These
# raise the patience considerably; combined with the cache mount below, an
# interrupted build resumes instead of starting the downloads over.
ENV MAMBA_REMOTE_MAX_RETRIES=5 \
    MAMBA_REMOTE_BACKOFF_FACTOR=3 \
    MAMBA_REMOTE_CONNECT_TIMEOUT_SECS=60 \
    MAMBA_REMOTE_READ_TIMEOUT_SECS=600

# Copied on its own, before the source tree: editing a Python file must not
# invalidate the layer that takes twenty minutes to build.
COPY envs/calib.yaml /tmp/calib.yaml
# Both package caches are BuildKit cache mounts: the tarballs survive a
# failed build and never enter an image layer. Hence no `micromamba clean`
# -- cleaning would throw away exactly what makes the next attempt cheap,
# and the mount is not part of the image either way. The pip mount matters
# on its own: pip's HTTP cache was adding 902 MB of downloaded wheels to
# the finished image, where nothing would ever read them again.
RUN --mount=type=cache,target=/opt/conda/pkgs,sharing=locked \
    --mount=type=cache,target=/root/.cache/pip,sharing=locked \
    micromamba create -y -f /tmp/calib.yaml \
    && find /opt/conda/envs -follow -type f -name '*.a' -delete \
    && rm -f /tmp/calib.yaml

# The environment's interpreter, by absolute path, for every step. This is the
# single most common way a working install breaks: with conda on PATH, a bare
# `python3` resolves to whichever environment is active -- usually one without
# the dependencies -- and fails several steps later with an opaque ImportError.
# LD_LIBRARY_PATH matters as much as PATH here, and is easier to forget.
# TensorFlow finds libcudart/libcublas/libcudnn through the loader, and
# they live in the environment's lib/. Natively that path is added by conda's
# activation script -- which this image deliberately never runs, calling the
# interpreter by absolute path instead. Without this line the container
# starts, sees the GPU through nvidia-smi, and then silently runs the whole
# pipeline on CPU: no error, just fifteen times slower.
#
# Safe to prepend: the conda environment ships no libcuda/libnvidia of its
# own, so the driver injected by the NVIDIA container runtime at
# /usr/lib/x86_64-linux-gnu is not shadowed. Verified inside the image.
ENV LD_LIBRARY_PATH=/opt/conda/envs/humancalib/lib
ENV PATH=/opt/conda/envs/humancalib/bin:${PATH} \
    HUMANCALIB_PYTHON=/opt/conda/envs/humancalib/bin/python

# MeTRAbs and the calibration share one environment here, so the `conda run -n
# metrabs_opensim` indirection that calibrate.sh needs on a split native install
# is replaced by a direct call. `-u` keeps tqdm's progress bars live.
ENV HUMANCALIB_METRABS_PYTHON="/opt/conda/envs/humancalib/bin/python -u"

# --- Runtime settings -------------------------------------------------------
#
# MPLBACKEND=Agg   : there is no display; without it matplotlib picks an
#                    interactive backend and the figure steps abort.
# MPLCONFIGDIR     : matplotlib writes a font cache at import; when the
#                    container runs as the host user, $HOME is not writable.
# PYTHONUNBUFFERED : progress and errors appear as they happen, not at exit.
# TFHUB_CACHE_DIR  : mount a volume here to download the model once, not once
#                    per container.
# OMP_NUM_THREADS  : unset, OpenMP starts one thread per visible core, which on
#                    a large node oversubscribes badly and slows scipy down.
#                    Override at run time on a machine with cores to spare.
# HOME             : the container is meant to run as the host's uid, which has
#                    no passwd entry here; without this, $HOME resolves to /
#                    and anything writing a dotfile cache fails.
ENV HOME=/tmp \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    TFHUB_CACHE_DIR=/models/tfhub \
    OMP_NUM_THREADS=4

RUN mkdir -p /models/tfhub /input /output /tmp/matplotlib \
    && chmod -R 0777 /models /output /tmp/matplotlib

# --- Optional: bake the pose model into the image ---------------------------
#
# BAKE_MODELS=1 pre-populates the TF-Hub cache (~708 MB download) so the image
# runs with no network at all -- the right trade on an air-gapped cluster or
# for an archival build. Default 0: the model is fetched on first run into
# whatever is mounted at /models, which keeps the image smaller and reusable
# across model versions.
#
# Only src/humancalib/core/models.py is copied at this point: the URL is the sole input, so
# the slow download layer is not invalidated by unrelated source edits.
ARG BAKE_MODELS=0
COPY src/humancalib/core/models.py /tmp/models.py
RUN if [ "${BAKE_MODELS}" = "1" ]; then \
        echo "Pre-fetching the MeTRAbs model into ${TFHUB_CACHE_DIR} ..." && \
        "${HUMANCALIB_PYTHON}" -c "\
import runpy, tensorflow_hub as hub; \
url = runpy.run_path('/tmp/models.py')['METRABS_L_URL']; \
hub.load(url); \
print('Cached:', url)" && \
        chmod -R a+rX "${TFHUB_CACHE_DIR}" ; \
    else \
        echo "BAKE_MODELS=0 - the model is downloaded on first run (~708 MB)." ; \
    fi \
    && rm -f /tmp/models.py

# --- Source -----------------------------------------------------------------
#
# Last, so that editing the pipeline rebuilds only this layer.
WORKDIR /opt/humancalib
COPY . /opt/humancalib

# Installed as a package, not only run from source, so `import humancalib` and
# `python -m humancalib...` work from any working directory -- the acceptance
# criterion for packaging. --no-deps: the environment above already pins every
# dependency exactly, and letting pip re-resolve would undo that.
# --no-build-isolation: build with the pinned setuptools instead of fetching
# whatever PyPI serves on the day of the build.
RUN pip install --no-deps --no-build-isolation /opt/humancalib \
    && rm -rf /opt/humancalib/build /opt/humancalib/src/humancalib.egg-info

ENTRYPOINT ["/opt/humancalib/docker/entrypoint.sh"]
CMD ["--help"]

LABEL org.opencontainers.image.title="HumanCalib" \
      org.opencontainers.image.description="Multi-camera extrinsic calibration from human pose" \
      org.opencontainers.image.licenses="MIT"
