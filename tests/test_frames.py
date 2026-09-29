"""Exported world frames: Z up in the TOML (Pose2Sim), Y up in the .trc (OpenSim)."""
import numpy as np

from humancalib.core.frames import (WORLD_TO_TRC, WORLD_TO_ZUP, ZUP_TO_YUP, extrinsics_in,
                                    points_in)

UP_INTERNAL = np.array([0.0, -1.0, 0.0])      # the scaled world has Y pointing down


def test_frames_are_rotations():
    for M in (WORLD_TO_ZUP, ZUP_TO_YUP, WORLD_TO_TRC):
        assert np.allclose(M @ M.T, np.eye(3)) and np.isclose(np.linalg.det(M), 1.0)


def test_up_is_z_in_the_toml_and_y_in_the_trc():
    assert np.allclose(WORLD_TO_ZUP @ UP_INTERNAL, [0, 0, 1])
    assert np.allclose(WORLD_TO_TRC @ UP_INTERNAL, [0, 1, 0])


def test_trc_matches_what_pose2sim_writes_from_the_toml():
    """Pose2Sim triangulates in the TOML's world and applies zup2yup: (X, Y, Z) -> (Y, Z, X)."""
    X = np.random.default_rng(0).normal(size=(5, 3))
    zup = points_in(WORLD_TO_ZUP, X)
    assert np.allclose(points_in(WORLD_TO_TRC, X), zup[:, [1, 2, 0]])


def test_rotating_the_world_leaves_every_projection_unchanged():
    rng = np.random.default_rng(1)
    R = np.linalg.qr(rng.normal(size=(3, 3)))[0]
    R *= np.sign(np.linalg.det(R))
    t = rng.normal(size=3)
    X = rng.normal(size=(10, 3))
    R2, t2 = extrinsics_in(WORLD_TO_ZUP, R, t)
    assert np.allclose(X @ R.T + t, points_in(WORLD_TO_ZUP, X) @ R2.T + t2)
