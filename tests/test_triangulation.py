"""Triangulation: which implementations are the same, and which only look it.

The repository grew several triangulation routines. Deduplicating them by
inspection was deliberately deferred, because the failure mode of getting it
wrong is not a crash -- it is slightly different 3D points, and therefore
slightly different published numbers, with nothing to notice. This file settles
the question by measurement, so the merge that follows rests on evidence.

Two genuinely different estimators are in the tree, and the distinction is not
cosmetic:

* Homogeneous DLT, solved by SVD. Three copies:
  evaluate_calibration.triangulate_skeleton, scale_scene.get_3d_keypoint and
  fix_person_association.triangulate (the only one that takes weights). With
  equal weights they are the same computation.
* Inhomogeneous weighted least squares -- core.triangulate_point, used on the
  calibration path. It fixes the homogeneous coordinate to 1 instead of taking
  the smallest singular vector, so on noisy observations it lands somewhere
  slightly different *by construction*. That is a modelling choice, not a
  duplicate, and merging the two would silently change results.

On exact observations every one of them must return the same point, and that is
the property worth pinning: it is the only case with a right answer.
"""
import numpy as np
import pytest

from humancalib.core.geometry import triangulate_point
from humancalib.postprocessing.evaluate_calibration import triangulate_skeleton
from humancalib.postprocessing.scale_scene import get_3d_keypoint
from humancalib.tools.fix_person_association import triangulate as triangulate_weighted


def _rig(n_cams=4, radius=4000.0, f=1600.0):
    """Cameras on a ring, looking inward. Millimetres, like the real pipeline."""
    K, R, t = [], [], []
    for i in range(n_cams):
        a = 2 * np.pi * i / n_cams
        # world -> camera: rotate so the ring centre is straight ahead at +z
        cam_pos = np.array([radius * np.cos(a), 0.0, radius * np.sin(a)])
        fwd = -cam_pos / np.linalg.norm(cam_pos)
        up = np.array([0.0, 1.0, 0.0])
        right = np.cross(up, fwd); right /= np.linalg.norm(right)
        true_up = np.cross(fwd, right)
        Rc = np.vstack([right, true_up, fwd])           # rows: camera axes
        K.append(np.array([[f, 0.0, 540.0], [0.0, f, 960.0], [0.0, 0.0, 1.0]]))
        R.append(Rc)
        t.append(-Rc @ cam_pos)
    return np.array(K), np.array(R), np.array(t)


def _project(K, R, t, X):
    p = K @ (R @ X + t)
    return p[:2] / p[2]


def _observations(X, noise_px=0.0, seed=0):
    """(K, R, t, p2d (C,1,1,2), s2d (C,1,1)) for one point seen by every camera."""
    K, R, t = _rig()
    rng = np.random.default_rng(seed)
    pts = np.array([_project(K[c], R[c], t[c], X) for c in range(len(K))])
    if noise_px:
        pts = pts + rng.normal(scale=noise_px, size=pts.shape)
    p2d = pts.reshape(len(K), 1, 1, 2)
    s2d = np.full((len(K), 1, 1), 0.9)
    return K, R, t, p2d, s2d


TRUE_X = np.array([120.0, -300.0, 45.0])


def _projection_matrices(K, R, t):
    return [K[c] @ np.hstack([R[c], t[c].reshape(3, 1)]) for c in range(len(K))]


# --- exact observations: everything must agree with the truth ---------------

def test_every_implementation_recovers_an_exact_point():
    K, R, t, p2d, s2d = _observations(TRUE_X)
    Ps = _projection_matrices(K, R, t)
    pts = p2d[:, 0, 0, :]

    got = {
        "triangulate_skeleton": triangulate_skeleton(p2d, s2d, K, R, t)[0, 0],
        "get_3d_keypoint": get_3d_keypoint(p2d, s2d, K, R, t, 0, 0),
        "fix_person_association": triangulate_weighted(Ps, pts, np.ones(len(Ps)))[:3],
        "core.triangulate_point": triangulate_point(pts, np.array(Ps))[:3],
    }
    for name, X in got.items():
        np.testing.assert_allclose(X, TRUE_X, atol=1e-6, err_msg=name)


# --- noisy observations: the SVD family must be identical -------------------

@pytest.mark.parametrize("noise", [0.0, 0.5, 3.0])
def test_the_three_svd_implementations_are_one_computation(noise):
    """Identical to floating-point noise, so they can safely become one."""
    K, R, t, p2d, s2d = _observations(TRUE_X, noise_px=noise, seed=1)
    Ps = _projection_matrices(K, R, t)
    pts = p2d[:, 0, 0, :]

    a = triangulate_skeleton(p2d, s2d, K, R, t)[0, 0]
    b = get_3d_keypoint(p2d, s2d, K, R, t, 0, 0)
    c = triangulate_weighted(Ps, pts, np.ones(len(Ps)))[:3]

    np.testing.assert_allclose(b, a, rtol=0, atol=1e-9)
    np.testing.assert_allclose(c, a, rtol=0, atol=1e-9)


def test_uniform_weights_do_not_change_the_svd_result():
    """Scaling every row alike leaves the null vector alone -- worth pinning,
    because it is what makes the weighted routine a drop-in for the others."""
    K, R, t, p2d, _ = _observations(TRUE_X, noise_px=1.0, seed=2)
    Ps = _projection_matrices(K, R, t)
    pts = p2d[:, 0, 0, :]

    ones = triangulate_weighted(Ps, pts, np.ones(len(Ps)))[:3]
    sevens = triangulate_weighted(Ps, pts, np.full(len(Ps), 7.0))[:3]
    np.testing.assert_allclose(sevens, ones, rtol=0, atol=1e-9)


def test_the_two_estimator_families_differ_under_noise_but_stay_close():
    """Not a duplicate: a different estimator, and the gap is bounded.

    If this ever fails wide, someone has changed one of the two into the other
    -- which would move published 3D points without any test noticing.
    """
    K, R, t, p2d, s2d = _observations(TRUE_X, noise_px=2.0, seed=3)
    Ps = np.array(_projection_matrices(K, R, t))
    pts = p2d[:, 0, 0, :]

    svd = triangulate_skeleton(p2d, s2d, K, R, t)[0, 0]
    lsq = triangulate_point(pts, Ps)[:3]

    gap = np.linalg.norm(svd - lsq)
    assert gap > 0.0, "the two families have become the same computation"
    assert gap < 5.0, f"they have drifted apart: {gap:.3f} mm for 2 px of noise"


# --- degenerate input -------------------------------------------------------

def test_a_joint_seen_by_one_camera_is_not_invented():
    K, R, t, p2d, s2d = _observations(TRUE_X)
    s2d[1:, 0, 0] = 0.0                       # only camera 0 still sees it

    assert np.isnan(triangulate_skeleton(p2d, s2d, K, R, t)[0, 0]).all()
    assert get_3d_keypoint(p2d, s2d, K, R, t, 0, 0) is None


def test_confidence_threshold_selects_the_cameras_used():
    """Below-threshold cameras must not contribute, however good their data."""
    K, R, t, p2d, s2d = _observations(TRUE_X, noise_px=2.0, seed=4)
    s2d[2:, 0, 0] = 0.1                       # cameras 2,3 drop out

    Ps = _projection_matrices(K, R, t)
    pts = p2d[:, 0, 0, :]

    got = triangulate_skeleton(p2d, s2d, K, R, t, conf_threshold=0.5)[0, 0]
    expected = triangulate_weighted(Ps[:2], pts[:2], np.ones(2))[:3]

    np.testing.assert_allclose(got, expected, rtol=0, atol=1e-9)
