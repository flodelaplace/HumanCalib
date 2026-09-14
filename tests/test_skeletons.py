"""Skeleton topology invariants.

get_bone_config is what keeps the bundle adjustment's bone regulariser away
from MeTRAbs' virtual joints. Those joints are linear combinations of the real
ones inside the regression head, so any bone touching them has constant length
by construction: zero variance, a rank-deficient orientation constraint, and a
lambda2 auto-balance computed from noise. The 87-joint branch exists solely to
prevent that, which makes it worth pinning down.
"""
import numpy as np

from core.skeletons import (METRABS_BML87_INDICES, METRABS_BONE, get_bone_config)


def test_87_joints_uses_the_remapped_metrabs_topology():
    bone, key_sub = get_bone_config(87)

    assert bone.shape == np.asarray(METRABS_BONE).shape == (27, 2)
    np.testing.assert_array_equal(key_sub, np.sort(np.unique(bone.flatten())))


def test_87_joint_bones_touch_only_real_joints():
    """Every endpoint must be one of the 26 non-virtual joints."""
    bone, _ = get_bone_config(87)
    real = set(int(i) for i in METRABS_BML87_INDICES)

    assert set(int(i) for i in bone.flatten()) <= real
    assert len(real) == 26


def test_87_is_the_26_topology_reindexed_not_a_different_skeleton():
    bone_87, _ = get_bone_config(87)
    bone_26, _ = get_bone_config(26)
    lookup = np.array(METRABS_BML87_INDICES)

    np.testing.assert_array_equal(bone_87, lookup[np.asarray(bone_26)])


def test_unknown_joint_counts_fall_back_to_openpose():
    bone, key_sub = get_bone_config(17)
    assert bone.shape == (12, 2)
    assert len(key_sub) > 0


def test_no_bone_joins_a_joint_to_itself():
    for n in (17, 26, 87):
        bone, _ = get_bone_config(n)
        assert not (bone[:, 0] == bone[:, 1]).any(), f"degenerate bone for n={n}"
