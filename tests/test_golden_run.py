"""Golden run: the calibration chain on frozen poses.

The pose estimator is the one part of this pipeline that cannot be tested on a
CPU runner, and it is also the one part that is not deterministic. Freezing its
output as a fixture removes both problems at once: everything downstream --
linear calibration, bundle adjustment, the artefacts they write -- becomes an
ordinary deterministic function of committed data, testable in seconds without a
GPU, a model download, or a network.

What this catches is *change*, not error. The reference values are not ground
truth; they are what the code produced on the day the container was validated
end to end. A failure means the numbers moved, and that is either a bug or a
deliberate improvement -- the test's job is to make sure nobody finds out by
accident, months later, while comparing figures for a paper.

The fixture keeps 20 *contiguous* frames rather than a wider spread, and that
matters: load_eldersim intersects the pose frame indices with the world
skeleton's, which the pipeline writes one-based against zero-based poses. On
contiguous frames that costs one frame, exactly as in production. On a sparse
selection the intersection would be empty and the fixture would test nothing.
"""
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FIXTURES = os.path.join(_REPO, "tests", "fixtures")

# Tolerances, measured rather than guessed. On one machine the whole chain is
# bit-for-bit reproducible, linear stage and bundle adjustment alike. Across
# numpy/scipy versions the linear stage stayed exact (0.000 degrees, 1.4e-12 on
# translations of ~6000) while the bundle adjustment moved 0.011 degrees and
# 2e-4 relative -- least_squares taking a different iterate path from a
# marginally different start and stopping elsewhere in the same basin. These
# leave room for that and for a different BLAS, and nothing more.
TOL = {
    "linear_1_0":    {"deg": 1e-4, "t_rel": 1e-6},
    "linear_1_0_ba": {"deg": 5e-2, "t_rel": 1e-3},
}


def _expected():
    with open(os.path.join(_FIXTURES, "golden_expected.json")) as f:
        return json.load(f)


def _angle_between(A, B):
    """Geodesic angle in degrees between two rotation matrices."""
    cos = (np.trace(A.T @ B) - 1.0) / 2.0
    return float(np.degrees(np.arccos(np.clip(cos, -1.0, 1.0))))


@pytest.fixture(scope="module")
def calibrated(tmp_path_factory):
    """Run linear calibration then bundle adjustment on a copy of the fixture."""
    exp = _expected()
    work = tmp_path_factory.mktemp("golden")
    run = work / "run"
    shutil.copytree(os.path.join(_FIXTURES, "demo_20f"), run)

    env = dict(os.environ, MPLBACKEND="Agg", PYTHONUNBUFFERED="1",
               # the children are separate interpreters: pytest's own
               # pythonpath setting does not reach them
               PYTHONPATH=os.pathsep.join(filter(None, [
                   os.path.join(_REPO, "src"), os.environ.get("PYTHONPATH")])))
    common = [str(run), "1", "1", "1"]

    linear = subprocess.run(
        [sys.executable, "-m", "humancalib.pipeline.run_calib_linear",
         "--conf_threshold", str(exp["conf_threshold"]),
         *common, "noise_1_0", str(exp["frame_skip"]), "MyDataset"],
        cwd=_REPO, env=env, capture_output=True, text=True)

    ba = subprocess.run(
        [sys.executable, "-m", "humancalib.pipeline.run_ba",
         "--prefix", str(run), "--frame_skip", str(exp["frame_skip"]),
         "--conf_threshold", str(exp["conf_threshold"]), "--ba_jac", "analytic"],
        cwd=_REPO, env=env, capture_output=True, text=True)

    return run, linear, ba


def test_the_linear_stage_completes(calibrated):
    run, linear, _ = calibrated
    assert linear.returncode == 0, linear.stdout[-3000:] + linear.stderr[-3000:]
    assert (run / "results" / "linear_1_0.json").exists()


def test_the_bundle_adjustment_completes(calibrated):
    run, _, ba = calibrated
    assert ba.returncode == 0, ba.stdout[-3000:] + ba.stderr[-3000:]
    assert (run / "results" / "linear_1_0_ba.json").exists()


@pytest.mark.parametrize("stage", ["linear_1_0", "linear_1_0_ba"])
def test_camera_poses_match_the_reference(calibrated, stage):
    run, _, _ = calibrated
    exp = _expected()[stage]
    tol = TOL[stage]

    with open(run / "results" / f"{stage}.json") as f:
        got = json.load(f)

    assert got["CAMID"] == exp["CAMID"]

    R_got, R_exp = np.array(got["R_w2c"]), np.array(exp["R_w2c"])
    t_got, t_exp = np.array(got["t_w2c"]), np.array(exp["t_w2c"])

    for cam, (A, B) in enumerate(zip(R_got, R_exp), start=1):
        assert _angle_between(A, B) < tol["deg"], f"camera {cam} rotation moved"

    scale = np.abs(t_exp).max()
    assert np.abs(t_got - t_exp).max() / scale < tol["t_rel"]


def test_rotations_stay_proper(calibrated):
    """Cheap invariant, and it catches the failure that looks plausible."""
    run, _, _ = calibrated
    for stage in ("linear_1_0", "linear_1_0_ba"):
        with open(run / "results" / f"{stage}.json") as f:
            R = np.array(json.load(f)["R_w2c"])
        for cam, Ri in enumerate(R, start=1):
            assert np.linalg.det(Ri) == pytest.approx(1.0, abs=1e-9), \
                f"{stage} camera {cam} is not a rotation"
            np.testing.assert_allclose(Ri @ Ri.T, np.eye(3), atol=1e-9)


def test_bundle_adjustment_does_not_make_the_fit_worse(calibrated):
    """The BA must not move the cameras arbitrarily far from the linear init.

    A degenerate optimisation that flings a camera across the room still writes
    a valid JSON. This bounds the change at something physically sensible
    without asserting an exact improvement, which depends on the data.
    """
    run, _, _ = calibrated
    with open(run / "results" / "linear_1_0.json") as f:
        lin = json.load(f)
    with open(run / "results" / "linear_1_0_ba.json") as f:
        ba = json.load(f)

    R_lin, R_ba = np.array(lin["R_w2c"]), np.array(ba["R_w2c"])
    t_lin, t_ba = np.array(lin["t_w2c"]), np.array(ba["t_w2c"])

    for cam, (A, B) in enumerate(zip(R_lin, R_ba), start=1):
        assert _angle_between(A, B) < 15.0, f"camera {cam} rotated {_angle_between(A, B):.1f} deg"
    assert np.abs(t_ba - t_lin).max() / np.abs(t_lin).max() < 0.5
