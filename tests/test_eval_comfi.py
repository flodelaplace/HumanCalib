"""COMFI reader: camera -> world extrinsics, and the timestamp alignment."""
import numpy as np
import pytest
import yaml

from humancalib.evaluation import comfi


def test_extrinsics_are_inverted_to_world_to_camera(tmp_path):
    """The yaml stores camera -> world with the camera centre as translation; the rig
    must come back as world -> camera with that same centre."""
    a = 0.3
    R_c2w = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1.0]])
    C = np.array([-0.58, 2.32, 1.11])
    p = tmp_path / "camera_4_extrinsics.yaml"
    with open(p, "w") as f:
        yaml.safe_dump({"camera_extrinsics": {"frame_from": "camera_4", "frame_to": "world",
                                              "rotation_matrix": R_c2w.tolist(),
                                              "translation_vector": C.tolist(), "rms_error": 0.0015}}, f)
    R, t, rms = comfi.read_extrinsics(str(p))
    assert np.allclose(-R.T @ t, C)
    assert np.allclose(R, R_c2w.T)
    assert rms == pytest.approx(0.0015)


def test_a_transform_that_is_not_camera_to_world_is_refused(tmp_path):
    p = tmp_path / "x.yaml"
    with open(p, "w") as f:
        yaml.safe_dump({"camera_extrinsics": {"frame_from": "world", "frame_to": "camera_4",
                                              "rotation_matrix": np.eye(3).tolist(),
                                              "translation_vector": [0, 0, 0]}}, f)
    with pytest.raises(ValueError, match="camera -> world"):
        comfi.read_extrinsics(str(p))


def test_alignment_picks_the_nearest_frame_and_flags_gaps():
    ref = np.arange(10) * 0.025                      # 40 Hz
    other = ref + 0.019                              # started 19 ms later
    idx = comfi.align(ref, other)
    assert idx[0] == 0                               # 19 ms away, still the nearest and within tolerance
    assert np.all(np.diff(idx) >= 0)
    other = np.delete(other, 5)                      # one dropped frame: a neighbour 19-31 ms away fills in
    idx = comfi.align(ref, other)
    assert (idx == -1).sum() <= 1 and np.all(np.diff(idx[idx >= 0]) >= 0)
    far = ref + 0.5                                  # half a second away: nothing matches
    assert np.all(comfi.align(ref, far) == -1)


def test_common_window_is_the_longest_run_everyone_matches():
    ref = np.arange(20) * 0.025
    # camera 4 lost frames 6-8 (75 ms): the middle instant has no frame within tolerance
    ts = {0: ref, 2: ref + 0.01, 4: np.delete(ref, [6, 7, 8]) + 0.005, 6: ref - 0.012}
    frames = comfi.common_window(ts)
    n = len(frames[0])
    assert 9 <= n <= 12 and all(len(frames[c]) == n for c in (2, 4, 6))
    assert 7 not in frames[0]                        # the hole splits the run; the longer side is kept
    assert np.all(np.diff(frames[4]) >= 0)          # a single lost frame is filled by repeating a neighbour
    short = comfi.common_window(ts, max_frames=5)
    assert all(len(short[c]) == 5 for c in (0, 2, 4, 6)) and short[0][0] == frames[0][0]
