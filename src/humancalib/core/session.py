"""Per-session configuration.

Replaces the repository-level ``config/config.yaml``, which was global mutable
state: it was tracked in git, rewritten by every run, and read back by three
scripts. Two consequences, both real:

* the working tree was dirtied by every calibration, and a run inherited
  whatever the previous one had left behind -- there was no binding between a
  session and its configuration;
* the image size written there was hardcoded to 1920x1080 at 30 fps regardless
  of the actual footage. On the shipped demo (1088x1920 @ 60) that is a
  landscape/portrait swap. It is latent today because the two code paths that
  consume it are off by default, but ``--ba_obs_weight declip`` would have
  discarded every joint below y=1080 on a 1920-tall frame.

The session file is written once per run into ``<output_dir>/<subset>/`` and
read from there, so concurrent runs on different datasets cannot interfere and
nothing is written inside the repository.
"""
import os

import yaml

from humancalib.core.videos import list_videos
from humancalib.core.log import get_logger
log = get_logger(__name__)

SESSION_FILENAME = "session.yaml"

VIDEO_EXTENSIONS = (".mp4", ".avi", ".mov", ".mkv", ".MP4", ".AVI")


def session_path(output_dir, subset):
    """Absolute path of the session file for this run."""
    return os.path.join(output_dir, subset, SESSION_FILENAME)


def probe_videos(video_dir):
    """Read frame size and rate from the actual footage.

    Returns:
        dict with ``width``, ``height`` (int, pixels) and ``frame_rate`` (float).

    Raises:
        FileNotFoundError: if no readable video is found.

    Cameras are expected to be synchronised and identically configured. If they
    are not, the first video wins and a warning names the outliers -- the
    calibration itself uses each camera's own intrinsics, so a mismatch here is
    informative rather than fatal.
    """
    import cv2

    videos = list_videos(video_dir)
    if not videos:
        raise FileNotFoundError(f"No video files found in {video_dir}")

    probed = []
    for path in videos:
        cap = cv2.VideoCapture(path)
        try:
            if not cap.isOpened():
                continue
            probed.append(
                (
                    os.path.basename(path),
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    float(cap.get(cv2.CAP_PROP_FPS)),
                )
            )
        finally:
            cap.release()

    if not probed:
        raise FileNotFoundError(f"No readable video files in {video_dir}")

    _, width, height, fps = probed[0]
    odd = [n for n, w, h, _ in probed if (w, h) != (width, height)]
    if odd:
        log.warning(f"frame size differs across cameras; using {width}x{height} "
            f"from {probed[0][0]}. Different: {', '.join(odd)}")
    if fps <= 0:
        log.warning(f"could not read frame rate from {probed[0][0]}, assuming 30")
        fps = 30.0

    return {"width": width, "height": height, "frame_rate": fps}


def write_session(output_dir, subset, camera_ids, available_joints, aid, pid, gid,
                  video_dir):
    """Write the session file for this run and return its path."""
    session = {
        "camera_ids": [int(c) for c in camera_ids],
        "available_joints": [int(j) for j in available_joints],
        "aid": int(aid),
        "pid": int(pid),
        "gid": int(gid),
        "video_dir": os.path.abspath(video_dir),
    }
    session.update(probe_videos(video_dir))

    path = session_path(output_dir, subset)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(session, f, default_flow_style=False, allow_unicode=True)
    return path


def load_session(output_dir, subset):
    """Read the session file for this run."""
    return load_session_dir(os.path.join(output_dir, subset))


def load_session_dir(subset_dir):
    """Read the session file from an already-joined <output_dir>/<subset> path.

    Raises:
        FileNotFoundError: with a message pointing at the step that writes it.
    """
    path = os.path.join(subset_dir, SESSION_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No session file at {path}. It is written by step 3 of the "
            f"pipeline (python -m humancalib.pipeline.write_session, called from calibrate.sh). "
            f"Running a later step on its own requires that step to have run "
            f"first for this output directory."
        )
    with open(path) as f:
        return yaml.safe_load(f)


def session_ids(subset_dir, prefix=None):
    """Return ``(aid, pid, gid)`` for the run stored in ``subset_dir``.

    They come from the session file, which is where they are recorded. Three
    post-processing scripts used to re-derive them by regex from the *name of
    the output directory*, each with its own copy of the same block: renaming a
    result folder therefore changed which artefacts were read, and any name not
    matching ``Axxx_Pxxx_Gxxx`` fell back to 1/1/1 behind a warning that looked
    alarming but described the normal case.

    The regex survives only as a fallback for result directories produced
    before the session file existed. ``prefix`` is the output directory whose
    name is parsed in that case; without it the defaults are used silently,
    which is correct -- nothing has varied these values in a long time.
    """
    try:
        session = load_session_dir(subset_dir)
    except (FileNotFoundError, OSError):
        session = None

    if session and all(k in session for k in ("aid", "pid", "gid")):
        return int(session["aid"]), int(session["pid"]), int(session["gid"])

    if prefix:
        import re
        match = re.search(r"A(\d+)_P(\d+)_G(\d+)",
                          os.path.basename(os.path.normpath(prefix)))
        if match:
            log.info("  NOTE: no session file; session IDs read from the directory "
                  "name (pre-refactor result folder).")
            return int(match.group(1)), int(match.group(2)), int(match.group(3))

    return 1, 1, 1
