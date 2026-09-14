"""Pose loading and TOML export.

The TOML export tests are a regression guard for bug B1: export_to_toml
rewrites an existing intrinsics file line by line, and a camera whose section it
never matched used to be written out carrying its *input* extrinsics. The
result was a valid-looking calibration file with one stale camera in it -- no
error, no warning, wrong geometry.
"""
import json

import numpy as np
import pytest

from core.poses_io import load_poses
from postprocessing.evaluate_calibration import export_to_toml


def _write_poses(path, n_frames=3, n_joints=4, seed=0):
    rng = np.random.default_rng(seed)
    pose = rng.normal(scale=100.0, size=(n_frames, n_joints, 2))
    score = rng.uniform(0.0, 1.0, size=(n_frames, n_joints))
    doc = {"data": [
        {"frame_index": i,
         "skeleton": [{"pose": pose[i].tolist(), "score": score[i].tolist()}]}
        for i in range(n_frames)
    ]}
    path.write_text(json.dumps(doc))
    return pose, score


def test_load_poses_round_trip(tmp_path):
    f = tmp_path / "A001_P001_G001_C001.json"
    pose, score = _write_poses(f)

    idx, p, s = load_poses(str(f))

    np.testing.assert_array_equal(idx, np.arange(len(pose)))
    np.testing.assert_allclose(p, pose)
    np.testing.assert_allclose(s, score)
    assert p.dtype == np.float64 and s.dtype == np.float64


def test_load_poses_keeps_non_contiguous_frame_indices(tmp_path):
    """Frame indices are absolute, not positional.

    Dropped frames leave gaps, and every downstream step matches observations
    across cameras by these numbers.
    """
    f = tmp_path / "poses.json"
    doc = {"data": [
        {"frame_index": i, "skeleton": [{"pose": [[0.0, 0.0]], "score": [1.0]}]}
        for i in (5, 17, 300)
    ]}
    f.write_text(json.dumps(doc))

    idx, _, _ = load_poses(str(f))
    np.testing.assert_array_equal(idx, [5, 17, 300])


_TOML = """[cam_1]
name = "cam_1"
size = [1080.0, 1920.0]
matrix = [[800.0, 0.0, 540.0], [0.0, 800.0, 960.0], [0.0, 0.0, 1.0]]
distortions = [0.0, 0.0, 0.0, 0.0]
rotation = [0.0, 0.0, 0.0]
translation = [0.0, 0.0, 0.0]

[cam_2]
name = "cam_2"
size = [1080.0, 1920.0]
matrix = [[800.0, 0.0, 540.0], [0.0, 800.0, 960.0], [0.0, 0.0, 1.0]]
distortions = [0.0, 0.0, 0.0, 0.0]
rotation = [0.0, 0.0, 0.0]
translation = [0.0, 0.0, 0.0]

[metadata]
adjusted = false
error = 0.0
"""


def test_export_writes_every_camera(tmp_path):
    src = tmp_path / "in.toml"; src.write_text(_TOML)
    dst = tmp_path / "out.toml"

    R = np.array([np.eye(3), np.eye(3)])
    t = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])

    export_to_toml(str(src), str(dst), R, t, ["cam_1", "cam_2"])

    out = dst.read_text()
    assert "translation = [1.0, 2.0, 3.0]" in out
    assert "translation = [4.0, 5.0, 6.0]" in out
    assert out.count("rotation = [") == 2


def test_a_metadata_section_is_not_mistaken_for_a_camera(tmp_path):
    """[metadata] matches the section regex but names no camera. Tolerated."""
    src = tmp_path / "in.toml"; src.write_text(_TOML)
    dst = tmp_path / "out.toml"

    export_to_toml(str(src), str(dst), np.array([np.eye(3)] * 2),
                   np.zeros((2, 3)), ["cam_1", "cam_2"])

    assert "[metadata]" in dst.read_text()


def test_a_camera_missing_from_the_input_is_refused(tmp_path):
    """B1. Silently emitting the input's stale pose is the failure to prevent."""
    src = tmp_path / "in.toml"; src.write_text(_TOML)
    dst = tmp_path / "out.toml"

    R = np.array([np.eye(3)] * 3)
    t = np.zeros((3, 3))

    with pytest.raises(ValueError) as err:
        export_to_toml(str(src), str(dst), R, t, ["cam_1", "cam_2", "cam_3"])

    assert "cam_3" in str(err.value)
    assert not dst.exists(), "nothing may be written when the export is incomplete"


def test_a_camera_with_no_rotation_line_is_refused(tmp_path):
    """A section present but incomplete is just as wrong, and easier to miss."""
    src = tmp_path / "in.toml"
    src.write_text(_TOML.replace("rotation = [0.0, 0.0, 0.0]\ntranslation", "translation", 1))
    dst = tmp_path / "out.toml"

    with pytest.raises(ValueError) as err:
        export_to_toml(str(src), str(dst), np.array([np.eye(3)] * 2),
                       np.zeros((2, 3)), ["cam_1", "cam_2"])
    assert "cam_1" in str(err.value)
