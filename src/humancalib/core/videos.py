"""The one definition of which videos a session contains, and in what order.

Camera IDs are positional: the Nth video in this list is camera N, and every
artefact on disk (A001_P001_G001_C00N.json) is named from that. So the order is
not cosmetic -- two steps that list videos differently disagree about which
physical camera is which.

That is exactly what used to happen. The pose step sorted file names
lexicographically, while calibrate.sh listed them with `sort -V` (natural
order) to pick each camera's intrinsics out of the TOML. Both agree on
zero-padded names, but not on `cam1 ... cam10`: natural order gives
cam1, cam2, cam10 where lexicographic gives cam1, cam10, cam2, so from the tenth
camera on, poses were paired with another camera's intrinsics. No error, just a
wrong calibration.

calibrate.sh also only looked for .mp4/.MP4 when naming cameras, although the
pose step reads .avi, .mov and .mkv too -- so any other container stopped the
pipeline at step 2, despite the documentation listing them as supported.

The order here is the pose step's (lexicographic), not natural order, on
purpose: it is the order every already-extracted pose file was numbered in, and
changing it would silently renumber the cameras of existing results.
"""
import glob
import os

VIDEO_PATTERNS = ("*.mp4", "*.avi", "*.mov", "*.mkv", "*.MP4", "*.AVI")


def list_videos(video_dir):
    """Absolute-or-as-given paths of every video in ``video_dir``, camera order.

    A set, not a list, collects the matches: on a case-insensitive filesystem --
    NTFS under WSL's /mnt/c, or macOS by default -- ``*.mp4`` and ``*.MP4``
    match the same file, which would otherwise count every camera twice.
    """
    found = set()
    for pattern in VIDEO_PATTERNS:
        found.update(glob.glob(os.path.join(video_dir, pattern)))
    return sorted(found)


def camera_names(video_dir):
    """Video base names without extension, in camera order.

    These are the section names looked up in the intrinsics TOML.
    """
    return [os.path.splitext(os.path.basename(p))[0] for p in list_videos(video_dir)]
