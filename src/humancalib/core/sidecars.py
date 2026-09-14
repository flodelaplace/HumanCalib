"""Dropped-frame sidecars.

A sidecar lists absolute frame indices that every step of the pipeline must
treat as missing -- black frames, encoding corruption, half-images that the
pose estimator still detects a plausible-looking skeleton in. They are produced
by the auto outlier-frame drop step and can also be hand-written.

These used to live next to the videos, as ``<video>.dropped.json``. That made
the input directory read-write, which prevents mounting it read-only in a
container and means a pipeline run mutates its own inputs. They now live under
the output directory instead, so inputs stay untouched.

Sidecars in the old location are still read, so existing curated drop lists are
not lost; writes always go to the new location.

File format, unchanged::

    {"dropped_frame_indices": [1273, 1274, 1825]}
"""
import json
import os

SIDECAR_DIRNAME = "dropped_frames"


def sidecar_path(output_dir, subset, video_path):
    """Path of the sidecar for ``video_path`` under the output directory."""
    stem = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(output_dir, subset, SIDECAR_DIRNAME, f"{stem}.dropped.json")


def legacy_sidecar_path(video_path):
    """Path of the pre-refactor sidecar, next to the video itself."""
    return os.path.splitext(video_path)[0] + ".dropped.json"


def _read_indices(path):
    with open(path) as f:
        return {int(i) for i in json.load(f).get("dropped_frame_indices", [])}


def read_dropped(output_dir, subset, video_path, warn_legacy=True):
    """Return the set of dropped frame indices for one video.

    Reads the output-directory sidecar; falls back to the legacy one next to
    the video. If both exist they are merged, so a hand-written legacy list is
    never silently ignored.
    """
    indices = set()
    new_path = sidecar_path(output_dir, subset, video_path)
    old_path = legacy_sidecar_path(video_path)

    if os.path.exists(new_path):
        indices |= _read_indices(new_path)
    if os.path.exists(old_path):
        legacy = _read_indices(old_path)
        if legacy and warn_legacy:
            print(
                f"  NOTE: reading legacy sidecar next to the video "
                f"({os.path.basename(old_path)}, {len(legacy)} indices). New "
                f"drops are written to {SIDECAR_DIRNAME}/ under the output "
                f"directory; move it there to keep the input folder read-only."
            )
        indices |= legacy
    return indices


def write_dropped(output_dir, subset, video_path, new_indices):
    """Merge ``new_indices`` into this video's sidecar. Returns how many were new.

    Existing entries, including any in the legacy location, are preserved.
    """
    existing = read_dropped(output_dir, subset, video_path, warn_legacy=False)
    merged = existing | {int(i) for i in new_indices}

    path = sidecar_path(output_dir, subset, video_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"dropped_frame_indices": sorted(merged)}, f, indent=2)
    return len(merged) - len(existing)
