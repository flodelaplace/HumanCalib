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


def test_reduced_rate_rtmpose_runs_get_their_own_folder():
    from humancalib.evaluation.batch import decimation_factor, run_name
    assert run_name("rtmpose") == "rtmpose"
    assert run_name("metrabs", 50) == "metrabs"
    assert run_name("rtmpose", 50) == "rtmpose_50hz"
    assert decimation_factor(200, 50) == 4
    assert decimation_factor(100, 50) == 2
    assert decimation_factor(60, 50) == 1


def test_method_v2_runs_get_their_own_folder():
    from humancalib.evaluation.batch import calibration_command, run_name
    assert run_name("metrabs", None, "geometric") == "metrabs_v2"
    assert run_name("rtmpose", 50, "geometric") == "rtmpose_50hz_v2"
    argv, _ = calibration_command("metrabs", "/v", "/w", "/env/bin/python", "metrabs_v2",
                                  ["--person_selection", "geometric"])
    assert argv[4] == "/w/metrabs_v2" and argv[-2:] == ["--person_selection", "geometric"]


def test_segment_scale_recovers_a_known_scale():
    """Legs of 2 + 2 calibration units for a 1.80 m person: 1.80 x 0.491 / 4 metres per unit."""
    import cv2 as _cv2
    from humancalib.postprocessing.scale_scene import LEG_RATIO, LEGS, segment_scale
    rng = np.random.default_rng(0)
    K = np.array([[1000.0, 0, 960], [0, 1000.0, 540], [0, 0, 1]])
    Rs, ts = [], []
    for a in np.radians([0, 90, 180, 270]):
        C = np.array([20 * np.cos(a), 20 * np.sin(a), 3.0])
        z = -C / np.linalg.norm(C)
        x = np.cross(z, [0, 0, 1.0]); x /= np.linalg.norm(x)
        R = np.vstack([x, np.cross(z, x), z])
        Rs.append(R); ts.append(-R @ C)
    F = 40
    p2d = np.zeros((4, F, 26, 2)); s2d = np.zeros((4, F, 26))
    for f in range(F):
        for side, (hip, knee, ankle) in enumerate(LEGS["halpe26"]):
            H = np.array([0.5 * side, 0.1 * f, 4.0])
            direction = rng.normal(size=3); direction /= np.linalg.norm(direction)
            Kn = H - np.array([0, 0, 2.0])
            An = Kn + 2.0 * direction
            for c in range(4):
                for j, X in ((hip, H), (knee, Kn), (ankle, An)):
                    uv = _cv2.projectPoints(X.reshape(1, 3), _cv2.Rodrigues(Rs[c])[0], ts[c], K, None)[0].ravel()
                    p2d[c, f, j] = uv; s2d[c, f, j] = 1.0
    s = segment_scale(p2d, s2d, np.array([K] * 4), np.array(Rs), np.array(ts), LEGS["halpe26"], 1.80, step=1)
    assert s == pytest.approx(1.80 * LEG_RATIO / 4.0, rel=1e-6)


def test_segment_scale_comparison_names():
    from humancalib.evaluation.batch import segment_scale_name
    assert segment_scale_name("metrabs_v2") == "metrabs_v3"
    assert segment_scale_name("metrabs") == "metrabs_seg"


def test_walking_vertical_removes_the_forward_lean():
    """A walker leaning 8 degrees forward along +x: the body axis alone is off by
    8 degrees; with the walking direction removed the vertical is exact."""
    import cv2 as _cv2
    from humancalib.postprocessing.scale_scene import walking_vertical
    K = np.array([[1000.0, 0, 960], [0, 1000.0, 540], [0, 0, 1]])
    Rs, ts = [], []
    for a in np.radians([20, 110, 200, 290]):
        C = np.array([8 * np.cos(a), 8 * np.sin(a), 2.0])
        z = np.array([0.0, 0.0, 1.0]) - C; z /= np.linalg.norm(z)
        x = np.cross(z, [0, 0, 1.0]); x /= np.linalg.norm(x)
        R = np.vstack([x, np.cross(z, x), z]); Rs.append(R); ts.append(-R @ C)
    lean = np.radians(8)
    feet, head, ankles = [0, 1], 2, (3, 4)
    F = 120
    p2d = np.zeros((4, F, 5, 2)); s2d = np.ones((4, F, 5))
    for f in range(F):
        x0 = -3 + 6 * f / F
        phase = (f // 20) % 2                     # each foot planted for 20 frames in turn
        lfoot = np.array([x0 if phase == 0 else x0 + 0.3 * np.sin(f), 0.1, 0.0 if phase == 0 else 0.1])
        rfoot = np.array([x0 if phase == 1 else x0 + 0.3 * np.sin(f), -0.1, 0.0 if phase == 1 else 0.1])
        lfoot[0] = round(lfoot[0] / 0.6) * 0.6 if phase == 0 else lfoot[0]
        rfoot[0] = round(rfoot[0] / 0.6) * 0.6 if phase == 1 else rfoot[0]
        mid = np.array([x0, 0.0, 0.08])
        top = mid + 1.6 * np.array([np.sin(lean), 0.0, np.cos(lean)])
        pts = [lfoot, rfoot, top, mid + [0, 0.1, 0], mid + [0, -0.1, 0]]
        for c in range(4):
            for j, X in enumerate(pts):
                p2d[c, f, j] = _cv2.projectPoints(X.reshape(1, 3), _cv2.Rodrigues(Rs[c])[0], ts[c], K, None)[0].ravel()
    up = walking_vertical(p2d, s2d, np.array([K] * 4), np.array(Rs), np.array(ts), feet, head, ankles, step=1)
    assert np.degrees(np.arccos(abs(up @ [0, 0, 1.0]))) < 0.5
