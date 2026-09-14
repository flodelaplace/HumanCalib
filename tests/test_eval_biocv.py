"""BioCV gold calibration reader and the Pose2Sim TOML writer.

No dataset is needed: a .calib file is synthesised with the property that makes
the real ones tricky -- a rotation block scaled by s != 1 -- and the reader must
return a camera that projects exactly like the raw matrix does.
"""
import cv2
import numpy as np
import pytest

from humancalib.evaluation import biocv
from humancalib.evaluation.rig import Camera, read_pose2sim_toml, write_pose2sim_toml


def synthetic_calib(s=0.998):
    R = cv2.Rodrigues(np.array([0.3, -1.2, 0.4]))[0]
    t_mm = np.array([-712.0, 1196.0, 4338.0])
    K = np.array([[1244.75, 0, 932.5], [0, 1244.75, 533.9], [0, 0, 1]])
    L = np.eye(4)
    L[:3, :3], L[:3, 3] = s * R, t_mm
    text = "1920\n1080\n" + "\n".join(" ".join(map(str, row)) for row in K) + "\n\n"
    text += "\n".join(" ".join(map(str, row)) for row in L) + "\n\n-0.15 0.083 0 0 0\n"
    return text, K, L


def test_scaled_rotation_block_is_read_as_the_same_projection():
    text, K, L = synthetic_calib()
    cam, s = biocv.parse_calib(text, "00")
    assert s == pytest.approx(0.998)
    assert cam.R @ cam.R.T == pytest.approx(np.eye(3), abs=1e-12)
    assert np.linalg.det(cam.R) == pytest.approx(1.0)

    X_mm = np.random.default_rng(1).uniform(-3000, 3000, (20, 3))
    raw = (K @ L[:3, :] @ np.c_[X_mm, np.ones(20)].T).T
    ours = (cam.projection() @ np.c_[X_mm / 1000.0, np.ones(20)].T).T
    assert ours[:, :2] / ours[:, 2:] == pytest.approx(raw[:, :2] / raw[:, 2:], abs=1e-6)


def test_units_are_metres():
    text, _, L = synthetic_calib(s=1.0)
    cam, _ = biocv.parse_calib(text, "00")
    assert cam.t == pytest.approx(L[:3, 3] / 1000.0)


def test_truncated_file_is_rejected():
    with pytest.raises(ValueError):
        biocv.parse_calib("1920 1080 1 0 0", "00")


def test_pose2sim_toml_round_trip(tmp_path):
    text, _, _ = synthetic_calib()
    cam, _ = biocv.parse_calib(text, "00")
    path = tmp_path / "calib.toml"
    write_pose2sim_toml([cam], path)
    (back,) = read_pose2sim_toml(path)
    assert back.name == "00"
    assert back.R == pytest.approx(cam.R, abs=1e-12)
    assert back.t == pytest.approx(cam.t)
    assert back.dist == pytest.approx(cam.dist[:4])


def test_intrinsics_only_toml_keeps_the_lines_the_exporter_fills(tmp_path):
    text, _, _ = synthetic_calib()
    cam, _ = biocv.parse_calib(text, "00")
    path = tmp_path / "intrinsics.toml"
    write_pose2sim_toml([cam], path, extrinsics=False)
    content = path.read_text()
    assert "rotation = [0.0, 0.0, 0.0]" in content
    assert "translation = [0.0, 0.0, 0.0]" in content


def test_nonzero_k3_is_refused(tmp_path):
    cam = Camera("00", (1920, 1080), np.eye(3), np.array([0.1, 0.0, 0.0, 0.0, 0.2]))
    with pytest.raises(ValueError, match="k3"):
        write_pose2sim_toml([cam], tmp_path / "x.toml")
