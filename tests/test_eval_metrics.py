"""Evaluation metrics: each is checked on rigs whose true error is known.

The central property is gauge invariance: an estimated rig that differs from
the gold one only by a similarity must score zero on every invariant metric,
and a known perturbation must show up exactly where, and only where, expected.
"""
import cv2
import numpy as np
import pytest

from humancalib.evaluation import metrics as M
from humancalib.evaluation.rig import Camera

UP_GOLD = np.array([0.0, 0.0, 1.0])


def look_at(center, target=(0.0, 0.0, 1.0), up=UP_GOLD):
    """World-to-camera rotation of a camera at `center` looking at `target`,
    OpenCV axes (x right, y down, z forward)."""
    z = np.asarray(target, float) - center
    z /= np.linalg.norm(z)
    x = np.cross(z, up)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.vstack([x, y, z])


def ring_rig(n=8, radius=4.0, rng=None):
    rng = np.random.default_rng(0) if rng is None else rng
    cams = []
    for k in range(n):
        a = 2 * np.pi * k / n + rng.uniform(-0.2, 0.2)
        C = np.array([radius * np.cos(a), radius * np.sin(a), 1.2 + rng.uniform(-0.4, 0.4)])
        R = look_at(C)
        cams.append(Camera(f"{k:02d}", (1920, 1080), np.eye(3), np.zeros(4), R, -R @ C))
    return cams


def transform(cams, s=1.0, Q=np.eye(3), b=np.zeros(3)):
    """The same physical rig expressed in another world: X' = s Q X + b."""
    out = []
    for c in cams:
        C = s * Q @ c.center + b
        R = c.R @ Q.T
        out.append(Camera(c.name, c.size, c.K, c.dist, R, -R @ C))
    return out


def rot(axis, deg):
    return cv2.Rodrigues(np.asarray(axis, float) / np.linalg.norm(axis) * np.radians(deg))[0]


def test_similarity_leaves_invariant_metrics_at_zero():
    gold = ring_rig()
    est = transform(gold, s=0.37, Q=rot([0.3, -1, 0.5], 71), b=np.array([5.0, -2.0, 9.0]))
    for p in M.pairwise_errors(est, gold):
        assert p["rot_deg"] == pytest.approx(0, abs=1e-5)
        assert p["dir_deg"] == pytest.approx(0, abs=1e-5)
        assert p["baseline_ratio"] == pytest.approx(0.37)
    for r in M.absolute_errors(est, gold, "7dof"):
        assert r["pos_err_m"] == pytest.approx(0, abs=1e-9)
        assert r["rot_err_deg"] == pytest.approx(0, abs=1e-5)


def test_scale_is_reported_not_absorbed():
    gold = ring_rig()
    est = transform(gold, s=1.03, Q=rot([0, 0, 1], 40))
    s = M.compare_rigs(est, gold, UP_GOLD, UP_GOLD)["summary"]
    assert s["scale_ratio_median"] == pytest.approx(1.03)
    assert s["scale_ratio_umeyama"] == pytest.approx(1.03)
    assert s["shape_baseline_pct_max"] == pytest.approx(0, abs=1e-9)
    assert s["gravity_deg"] == pytest.approx(0, abs=1e-5)
    # 4-DoF keeps scale at 1, so a 3% scale error is visible in metres.
    assert s["abs4dof_pos_mm_median"] > 50
    assert s["abs7dof_pos_mm_max"] == pytest.approx(0, abs=1e-6)


def test_yaw_and_translation_vanish_under_4dof_even_with_a_y_down_estimate():
    gold = ring_rig()
    # HumanCalib's final frame is y down: gold +z becomes estimated -y.
    to_y_down = M.rotation_between(UP_GOLD, [0, -1, 0])
    est = transform(gold, Q=to_y_down @ rot(UP_GOLD, 123), b=np.array([1.0, 2.0, 3.0]))
    s = M.compare_rigs(est, gold, up_est=[0, -1, 0], up_gold=UP_GOLD)["summary"]
    assert s["gravity_deg"] == pytest.approx(0, abs=1e-5)
    assert s["abs4dof_pos_mm_max"] == pytest.approx(0, abs=1e-6)
    assert s["abs4dof_rot_deg_max"] == pytest.approx(0, abs=1e-5)


def test_tilt_is_measured_as_gravity_error():
    gold = ring_rig()
    est = transform(gold, Q=rot([1, 0, 0], 3.0))
    assert M.gravity_error_deg(est, gold, UP_GOLD, UP_GOLD) == pytest.approx(3.0, abs=1e-6)


def test_one_rotated_camera_only_affects_its_own_pairs():
    gold = ring_rig()
    est = transform(gold, Q=rot([1, 2, 3], 30))
    bad = est[2]
    C = bad.center
    R = rot([0, 1, 0], 2.0) @ bad.R           # rotate the camera about its own centre
    est[2] = Camera(bad.name, bad.size, bad.K, bad.dist, R, -R @ C)
    for p in M.pairwise_errors(est, gold):
        expected = 2.0 if "02" in (p["cam_i"], p["cam_j"]) else 0.0
        assert p["rot_deg"] == pytest.approx(expected, abs=1e-5)


def test_leave_one_out_does_not_let_a_bad_camera_hide():
    gold = ring_rig()
    est = transform(gold)
    moved = est[0]
    C = moved.center + np.array([0.5, 0.0, 0.0])
    est[0] = Camera(moved.name, moved.size, moved.K, moved.dist, moved.R, -moved.R @ C)
    loo = M.absolute_errors(est, gold, "4dof", UP_GOLD, UP_GOLD, leave_one_out=True)
    fit_all = M.absolute_errors(est, gold, "4dof", UP_GOLD, UP_GOLD, leave_one_out=False)
    assert loo[0]["pos_err_m"] == pytest.approx(0.5, abs=1e-9)
    assert fit_all[0]["pos_err_m"] < 0.5


def test_auc_bounds():
    assert M.auc([0.0, 0.0], 5) == pytest.approx(1.0)
    assert M.auc([10.0, 20.0], 5) == 0.0
    assert M.auc([2.5], 5) == pytest.approx(0.5, abs=1e-3)


def test_rotation_between_handles_opposite_directions():
    R = M.rotation_between([0, 0, 1], [0, 0, -1])
    assert R @ np.array([0, 0, 1.0]) == pytest.approx([0, 0, -1])
    assert np.linalg.det(R) == pytest.approx(1.0)


def test_a_matrix_that_is_not_a_rotation_is_refused_not_read_as_zero():
    """The RTMPose path's linear stage returns general matrices; the trace
    formula clipped them to 0 degrees, i.e. a perfect score."""
    with pytest.raises(ValueError, match="not a rotation"):
        M.rotation_angle_deg(1.3 * np.eye(3))


def test_humancalib_loader_projects_non_rotations(tmp_path):
    import json
    from humancalib.evaluation.compare import load_humancalib, orthonormality_dev
    gold = ring_rig(n=3)
    sheared = [(g.R @ np.diag([1.0, 1.4, 0.7])).tolist() for g in gold]
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"R_w2c": sheared, "t_w2c": [g.t.tolist() for g in gold]}))
    cams = load_humancalib(str(path), gold)
    assert orthonormality_dev(str(path)) > 0.5
    for c in cams:
        assert c.R @ c.R.T == pytest.approx(np.eye(3), abs=1e-12)


def test_rig_figure_is_written(tmp_path):
    from humancalib.evaluation.plot_rig import plot_rigs
    gold = ring_rig()
    est = transform(gold, s=1.02, Q=M.rotation_between(UP_GOLD, [0, -1, 0]) @ rot(UP_GOLD, 30))
    path = tmp_path / "rig.png"
    plot_rigs(est, gold, [0, -1, 0], UP_GOLD, str(path), title="synthetic")
    assert path.stat().st_size > 10000
