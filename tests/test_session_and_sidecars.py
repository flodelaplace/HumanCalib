"""Per-session configuration and dropped-frame sidecars.

Both replaced global mutable state that lived in the repository or next to the
input videos. The properties worth pinning are the ones that motivated the
change: a run must not write into its own inputs, and an existing hand-curated
drop list must never be silently lost.

The session_ids test is also a direct regression guard. Routing three
post-processing scripts through this helper is what removed the last copies of
a regex that read the session identifiers out of a directory *name*.
"""
import json

import pytest

from humancalib.core.session import SESSION_FILENAME, load_session_dir, session_ids
from humancalib.core.sidecars import (legacy_sidecar_path, read_dropped,
                           write_dropped)

import yaml


def _session(tmp_path, subset="noise_1_0", **over):
    d = tmp_path / subset
    d.mkdir(parents=True, exist_ok=True)
    doc = {"aid": 1, "pid": 1, "gid": 1, "camera_ids": [1, 2],
           "available_joints": [0, 1], "width": 1080, "height": 1920,
           "frame_rate": 60.0, "video_dir": "/somewhere"}
    doc.update(over)
    (d / SESSION_FILENAME).write_text(yaml.safe_dump(doc))
    return d


def test_missing_session_names_the_step_that_writes_it(tmp_path):
    with pytest.raises(FileNotFoundError) as err:
        load_session_dir(str(tmp_path / "nope"))
    assert "write_session" in str(err.value)


def test_ids_come_from_the_session_not_the_directory_name(tmp_path):
    """The directory is deliberately named to contradict the session file."""
    root = tmp_path / "A009_P008_G007"
    d = _session(root, aid=1, pid=1, gid=1)

    assert session_ids(str(d), str(root)) == (1, 1, 1)


def test_ids_fall_back_to_the_directory_name_for_pre_refactor_results(tmp_path):
    root = tmp_path / "A003_P002_G001"
    (root / "noise_1_0").mkdir(parents=True)

    assert session_ids(str(root / "noise_1_0"), str(root)) == (3, 2, 1)


def test_ids_default_quietly_when_there_is_nothing_to_read(tmp_path):
    assert session_ids(str(tmp_path / "absent")) == (1, 1, 1)


def test_sidecars_are_written_under_the_output_directory(tmp_path):
    out = tmp_path / "out"
    video = tmp_path / "input" / "cam01.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")

    write_dropped(str(out), "noise_1_0", str(video), [3, 1, 2])

    assert (out / "noise_1_0" / "dropped_frames" / "cam01.dropped.json").exists()
    assert not legacy_sidecar_path(str(video)) in [str(p) for p in video.parent.iterdir()]
    assert sorted(p.name for p in video.parent.iterdir()) == ["cam01.mp4"], \
        "the input directory must stay untouched, so it can be mounted read-only"


def test_a_legacy_sidecar_is_read_and_merged_never_lost(tmp_path):
    out = tmp_path / "out"
    video = tmp_path / "input" / "cam01.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"")

    legacy = tmp_path / "input" / "cam01.dropped.json"
    legacy.write_text(json.dumps({"dropped_frame_indices": [10, 11]}))

    n_new = write_dropped(str(out), "noise_1_0", str(video), [11, 42])

    assert n_new == 1                                  # 11 was already known
    assert read_dropped(str(out), "noise_1_0", str(video)) == {10, 11, 42}
    assert json.loads(legacy.read_text())["dropped_frame_indices"] == [10, 11], \
        "the legacy file is read, never rewritten"


def test_dropped_indices_are_sorted_and_deduplicated(tmp_path):
    out = tmp_path / "out"
    video = tmp_path / "cam01.mp4"
    video.write_bytes(b"")

    write_dropped(str(out), "s", str(video), [5, 5, 1])
    written = json.loads((tmp_path / "out" / "s" / "dropped_frames" / "cam01.dropped.json").read_text())
    assert written["dropped_frame_indices"] == [1, 5]


def test_no_sidecar_means_no_dropped_frames(tmp_path):
    assert read_dropped(str(tmp_path), "s", str(tmp_path / "cam01.mp4")) == set()
