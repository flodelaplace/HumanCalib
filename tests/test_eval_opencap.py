"""OpenCap reader: the traps that would silently corrupt an evaluation."""
import os
import pickle

import numpy as np
import pytest
import yaml

from humancalib.evaluation import opencap


def write_pickle(path, R, t_mm, cx=366.486, cy=638.5016, image_size=(1280.0, 720.0)):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({
            "intrinsicMat": np.array([[913.2225, 0.0, cx], [0.0, 913.5242, cy], [0.0, 0.0, 1.0]]),
            "distortion": np.array([[0.12779, -0.28425, -0.00034093, 6.697e-05, 0.21344]]),
            "imageSize": np.array(image_size).reshape(2, 1),
            "rotation": R,
            "translation": np.asarray(t_mm, dtype=float).reshape(3, 1),
        }, f)


def rotation(yaw):
    c, s = np.cos(yaw), np.sin(yaw)
    return np.array([[c, 0.0, -s], [0.0, 1.0, 0.0], [s, 0.0, c]])


def test_image_size_is_taken_from_the_principal_point_not_the_stored_field():
    """imageSize says [1280, 720] while the videos are portrait 720x1280; believing
    it would put every projection in the wrong half of the image."""
    K = np.array([[913.0, 0.0, 366.0], [0.0, 913.0, 639.0], [0.0, 0.0, 1.0]])
    assert opencap.image_size(K, [1280.0, 720.0]) == (720.0, 1280.0)
    assert opencap.image_size(K, [720.0, 1280.0]) == (720.0, 1280.0)
    # a genuinely landscape camera keeps its order
    K_wide = np.array([[913.0, 0.0, 639.0], [0.0, 913.0, 366.0], [0.0, 0.0, 1.0]])
    assert opencap.image_size(K_wide, [1280.0, 720.0]) == (1280.0, 720.0)


def test_translation_is_read_in_metres_and_k3_is_kept(tmp_path):
    """The pickle stores millimetres, and the fifth distortion coefficient is 0.213 --
    dropping it would leave the keypoints distorted."""
    path = str(tmp_path / "Cam0" / "cameraIntrinsicsExtrinsics.pickle")
    write_pickle(path, rotation(0.3), [-969.0424, 728.7662, 3292.6681])
    cam = opencap.parse_calib(path, "Cam0")
    assert cam.t == pytest.approx([-0.9690424, 0.7287662, 3.2926681])
    assert cam.dist.shape == (5,)
    assert cam.dist[4] == pytest.approx(0.21344)
    assert cam.size == (720.0, 1280.0)


def test_a_non_rotation_is_refused(tmp_path):
    path = str(tmp_path / "Cam0" / "cameraIntrinsicsExtrinsics.pickle")
    write_pickle(path, np.diag([1.0, 1.0, 0.0]), [0.0, 0.0, 1000.0])
    with pytest.raises(ValueError, match="not a rotation"):
        opencap.parse_calib(path, "Cam0")


def test_common_window_aligns_cameras_that_start_at_different_moments():
    """Each camera has its own raw_start -- up to 2.2 s apart. The window is centred on
    that instant, so it lands on the same output frame everywhere, and its width comes
    from the dataset's own sync_frames rather than from everything the cameras share."""
    starts_frames = [(300, 601), (348, 607), (432, 595), (300, 546), (312, 603)]
    windows = {
        f"subject2/Session1/Cam{c}/walking1": {"raw_start": s, "raw_frames": n, "sync_frames": 86, "fps": 60.0}
        for c, (s, n) in enumerate(starts_frames)
    }
    length, starts = opencap.common_window(windows, "subject2", "walking1")
    # centred on the synchronisation instant, sync_frames on each side
    assert length == 86 + 86
    assert starts == {0: 214, 1: 262, 2: 346, 3: 214, 4: 226}
    # the synchronisation instant lands on the same output frame in every camera
    for cam, (raw_start, _) in enumerate(starts_frames):
        assert raw_start - starts[cam] == 86
    # a wider reach is clipped by the shortest camera, never by the longest
    long_length, _ = opencap.common_window(windows, "subject2", "walking1", reach=10_000)
    assert long_length == 300 + 163


def test_common_window_reports_a_missing_camera():
    windows = {"subject2/Session1/Cam0/walking1": {"raw_start": 10, "raw_frames": 100}}
    with pytest.raises(KeyError, match="Cam1"):
        opencap.common_window(windows, "subject2", "walking1")


def test_stature_comes_from_the_session_metadata(tmp_path):
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "subject2"))
    with open(os.path.join(root, "subject2", "sessionMetadata.yaml"), "w") as f:
        yaml.safe_dump({"height_m": 1.96, "mass_kg": 78.2, "subjectID": "subject2"}, f)
    assert opencap.stature(root, "subject2") == pytest.approx(1.96)


def test_up_is_y_down():
    """On 15 cameras the image's downward axis projects on +Y at 0.997 and the optical
    centres sit 0.90 m above the floor, so the world's up is -Y."""
    assert opencap.UP == [0.0, -1.0, 0.0]
