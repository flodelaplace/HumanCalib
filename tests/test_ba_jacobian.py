"""The analytic bundle-adjustment Jacobian, against finite differences.

This is the highest-risk code in the repository: it is the newest, it is
hand-derived, and it is on by default (`--ba_jac analytic`). A wrong Jacobian
does not raise -- least_squares simply takes worse steps and converges
somewhere slightly different, which looks exactly like a hard calibration
problem. Finite differences are the only independent check available.

The residual layout is three stacked blocks and they are verified separately,
because they are not derived the same way: the reprojection and bone-variance
blocks are analytic, while the 3D-orientation block is itself computed
numerically inside ba_jacobian, so comparing it to finite differences only
confirms the plumbing.
"""
import cv2
import numpy as np
import pytest

from humancalib.calibration.ba import from_theta, objfun, objfun_var3d, to_theta
from humancalib.calibration.ba_jacobian import ba_jacobian

C, N, J = 3, 4, 6
BONE_IDX = np.array([[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [0, 5]])
LAMBDA1 = LAMBDA2 = 1.0
CONF = 0.5


def _problem(seed=7, with_dropouts=True):
    """A small, well-conditioned synthetic calibration.

    Points sit in a unit blob at the origin; every camera looks at it from ~6
    units away, so nothing is near the image border and no depth approaches
    zero. Finite differences need that: the projection derivative goes as 1/z
    and a grazing point would swamp the comparison with truncation error.
    """
    rng = np.random.default_rng(seed)

    x = rng.normal(scale=0.3, size=(N * J, 3))

    K = np.tile(np.array([[800.0, 0, 320.0], [0, 800.0, 240.0], [0, 0, 1.0]]), (C, 1, 1))
    R = np.array([cv2.Rodrigues(rng.normal(scale=0.25, size=3))[0] for _ in range(C)])
    t = np.column_stack([rng.normal(scale=0.2, size=C),
                         rng.normal(scale=0.2, size=C),
                         np.full(C, 6.0)])

    # projections, with a little noise so no residual sits exactly at zero
    sp2d = np.empty((C, N * J, 2))
    for c in range(C):
        cam = (R[c] @ x.T + t[c].reshape(3, 1))
        img = (K[c] @ cam)
        sp2d[c] = (img[:2] / img[2]).T + rng.normal(scale=0.5, size=(N * J, 2))

    ss2d = np.full((C, N, J), 0.9)
    if with_dropouts:
        # a few observations below the confidence threshold, so the masking
        # path is exercised rather than assumed away
        ss2d[0, 0, 0] = 0.1
        ss2d[1, 2, 3] = 0.2
        ss2d[2, 1, 5] = 0.0

    sp3d = np.empty((C, N, J, 3))
    for c in range(C):
        cam = (R[c] @ x.T + t[c].reshape(3, 1)).T
        sp3d[c] = cam.reshape(N, J, 3) + rng.normal(scale=0.01, size=(N, J, 3))
    ss3d = np.full((C, N, J), 0.9)

    params = to_theta(R, t, x)
    return params, K, sp2d, ss2d, sp3d, ss3d


def _residual(params, K, sp2d, ss2d, sp3d, ss3d):
    return objfun(params, K, sp2d, ss2d, sp3d, ss3d, BONE_IDX, C, N, J,
                  LAMBDA1, LAMBDA2, None, conf_threshold=CONF)


def _numeric_jacobian(params, args, eps=1e-6):
    """Central differences, with a step scaled to each parameter."""
    f0 = _residual(params, *args)
    out = np.empty((f0.size, params.size))
    for i in range(params.size):
        h = eps * max(1.0, abs(params[i]))
        pp = params.copy(); pp[i] += h
        pm = params.copy(); pm[i] -= h
        out[:, i] = (_residual(pp, *args) - _residual(pm, *args)) / (2 * h)
    return out


@pytest.fixture(scope="module")
def jacobians():
    params, *args = _problem()
    analytic = ba_jacobian(params, *args, BONE_IDX, C, N, J,
                           LAMBDA1, LAMBDA2, None, conf_threshold=CONF).toarray()
    numeric = _numeric_jacobian(params, args)
    return analytic, numeric, params, args


def test_shape_matches_the_residual_and_parameter_vectors(jacobians):
    analytic, numeric, params, args = jacobians
    assert analytic.shape == numeric.shape
    assert analytic.shape == (_residual(params, *args).size, params.size)


def test_reprojection_block_matches_finite_differences(jacobians):
    """The 2D reprojection rows -- the bulk of the objective, fully analytic."""
    analytic, numeric, _, args = jacobians
    n_nll = int((args[2] > CONF).sum()) * 2      # two residuals per visible joint

    a = analytic[:n_nll]
    n = numeric[:n_nll]
    scale = max(np.abs(n).max(), 1.0)
    assert np.abs(a - n).max() / scale < 1e-6


def test_bone_variance_block_matches_finite_differences(jacobians):
    """The last rows: one bone-length variance per bone, analytic."""
    analytic, numeric, _, _ = jacobians
    n_bones = len(BONE_IDX)

    a = analytic[-n_bones:]
    n = numeric[-n_bones:]
    scale = max(np.abs(n).max(), 1.0)
    assert np.abs(a - n).max() / scale < 1e-5


def test_whole_jacobian_agrees_within_tolerance(jacobians):
    analytic, numeric, _, _ = jacobians
    scale = max(np.abs(numeric).max(), 1.0)
    assert np.abs(analytic - numeric).max() / scale < 1e-4


def test_bone_variance_rows_do_not_touch_camera_parameters(jacobians):
    """Bone lengths are a property of the 3D points alone.

    If these columns were ever non-zero the regulariser would be pulling on the
    camera poses, which is not what it is for.
    """
    analytic, _, _, _ = jacobians
    n_bones = len(BONE_IDX)
    assert np.abs(analytic[-n_bones:, :6 * C]).max() == 0.0


def test_masked_observations_contribute_no_rows():
    """A joint below the confidence threshold must drop out entirely."""
    params, *args = _problem(with_dropouts=True)
    n_visible = int((args[2] > CONF).sum())
    assert n_visible < C * N * J                       # the fixture really drops some

    jac = ba_jacobian(params, *args, BONE_IDX, C, N, J,
                      LAMBDA1, LAMBDA2, None, conf_threshold=CONF)
    res = _residual(params, *args)

    n_var3d = objfun_var3d(from_theta(params, C)[0], args[3], args[4] > 0, BONE_IDX).size
    assert jac.shape[0] == res.size
    assert jac.shape[0] == n_visible * 2 + n_var3d + len(BONE_IDX)
