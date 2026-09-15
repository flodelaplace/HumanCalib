"""Whether pose extraction can be skipped because its results are already there.

Formerly a Python snippet embedded in calibrate.sh. Extracting MeTRAbs poses
costs about two minutes per camera, so a re-run on the same session reuses them.

The rule is deliberately narrow, and deliberately unchanged: the cache is valid
when the 2D and 3D pose directories hold the same, non-zero number of files and
the first camera covers exactly the requested frame range. It does NOT compare
intrinsics or model versions -- a documented limitation (HOWTO.md, "Caching"):
after changing the TOML, delete the cached poses to force re-extraction.
"""
import glob
import json
import os
from collections import namedtuple

PoseRange = namedtuple("PoseRange", "start end n_frames n_cameras")


def cached_pose_range(output_dir, subset):
    """Frame range held by an existing extraction, or None if there is none."""
    d2 = os.path.join(output_dir, subset, "2d_joint")
    d3 = os.path.join(output_dir, subset, "3d_joint")
    if not (os.path.isdir(d2) and os.path.isdir(d3)):
        return None

    files_2d = sorted(glob.glob(os.path.join(d2, "*.json")))
    files_3d = glob.glob(os.path.join(d3, "*.json"))
    if not files_2d or len(files_2d) != len(files_3d):
        return None

    try:
        with open(files_2d[0]) as f:
            data = json.load(f)["data"]
        return PoseRange(int(data[0]["frame_index"]), int(data[-1]["frame_index"]),
                         len(data), len(files_2d))
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        # A truncated or foreign file is not a cache; re-extract.
        return None


def poses_are_cached(output_dir, subset, start_frame=None, end_frame=None):
    """Return the cached PoseRange if it matches the request, else None.

    Without --start_frame the request starts at frame 0; without --end_frame
    any cached end is accepted, exactly as calibrate.sh behaved.
    """
    cached = cached_pose_range(output_dir, subset)
    if cached is None:
        return None
    want_start = 0 if start_frame is None else int(start_frame)
    want_end = cached.end if end_frame is None else int(end_frame)
    if cached.start == want_start and cached.end == want_end:
        return cached
    return None


def covers_all_cameras(cached, n_cameras):
    """Whether a cached extraction holds every camera.

    An extraction interrupted between cameras leaves equal numbers of 2D and 3D
    files for the cameras it finished, which poses_are_cached accepts: reusing it
    would calibrate a rig with cameras missing."""
    return cached is not None and cached.n_cameras == n_cameras
