"""procrustes_align: recover a known similarity transform exactly.

This is the initialisation of the whole linear calibration -- every camera pose
the bundle adjustment starts from comes out of here. It is also pure
linear algebra with an exact answer, so unlike most of the pipeline it can be
tested against ground truth rather than against a previous run.
"""
import cv2
import numpy as np
import pytest

from humancalib.calibration.calib_linear import procrustes_align


def _rotation(rotvec):
    return cv2.Rodrigues(np.asarray(rotvec, dtype=float))[0]


def test_recovers_a_known_similarity_exactly():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(50, 3))

    R_true = _rotation([0.3, -0.7, 1.1])
    s_true = 2.5
    t_true = np.array([1.0, -2.0, 3.0])
    Y = s_true * (R_true @ X.T).T + t_true

    R, t, s = procrustes_align(X, Y)

    assert s == pytest.approx(s_true, abs=1e-9)
    np.testing.assert_allclose(R, R_true, atol=1e-9)
    np.testing.assert_allclose(t, t_true, atol=1e-9)


def test_is_exact_for_the_identity():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(20, 3))
    R, t, s = procrustes_align(X, X)

    assert s == pytest.approx(1.0, abs=1e-12)
    np.testing.assert_allclose(R, np.eye(3), atol=1e-12)
    np.testing.assert_allclose(t, np.zeros(3), atol=1e-12)


def test_never_returns_a_reflection():
    """A mirrored target must still yield a proper rotation.

    Without the determinant correction, the SVD happily returns an improper
    orthogonal matrix here. That would place cameras behind the scene and is
    the one failure mode of Umeyama that produces a plausible-looking result
    rather than an error.
    """
    rng = np.random.default_rng(2)
    X = rng.normal(size=(40, 3))
    Y = X * np.array([1.0, 1.0, -1.0])          # improper: det = -1

    R, t, s = procrustes_align(X, Y)

    assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-9)
    np.testing.assert_allclose(R @ R.T, np.eye(3), atol=1e-9)


def test_scale_is_recovered_independently_of_translation():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(30, 3))
    for s_true in (0.01, 1.0, 1000.0):
        Y = s_true * X + np.array([500.0, -500.0, 0.0])
        _, _, s = procrustes_align(X, Y)
        assert s == pytest.approx(s_true, rel=1e-9)


def test_linear_poses_are_upgraded_to_real_rotations_without_moving_projections():
    """The linear solve returns general 3x3 matrices. Taking the nearest rotation moves
    every projection; PnP on the same points returns a true rotation that still fits."""
    import cv2
    from humancalib.calibration.calib_linear import metric_upgrade_pnp

    rng = np.random.default_rng(0)
    K = np.array([[1200.0, 0, 960], [0, 1200.0, 540], [0, 0, 1]])
    R = cv2.Rodrigues(np.array([0.2, -0.9, 0.1]))[0]
    t = np.array([[0.4], [-0.2], [6.0]])
    X = rng.uniform(-1.5, 1.5, (60, 3))
    proj = (K @ (R @ X.T + t))
    y = (proj[:2] / proj[2]).T

    skewed = R @ np.diag([1.0, 1.3, 0.7])          # what the linear stage produces
    R_out, t_out = metric_upgrade_pnp([skewed], [t], X, [y], [K])
    assert R_out[0] @ R_out[0].T == pytest.approx(np.eye(3), abs=1e-9)
    assert R_out[0] == pytest.approx(R, abs=1e-6)
    assert t_out[0] == pytest.approx(t, abs=1e-6)
