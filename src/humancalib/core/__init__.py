"""Shared library for the calibration pipeline.

Submodules:
- skeletons : joint indices, bone connectivity (OP, MeTRAbs-26, bml_movi_87)
- geometry  : triangulation, projection, R/T inversion
- poses_io  : JSON load/save for poses, cameras, skeletons
- filtering : per-frame visibility / orientation helpers used by linear calibration
- gpu       : GPU selection helper (import directly: ``from core.gpu import select_gpu``)

Everything is re-exported here so consumers can do either:
    from humancalib.core import OP_BONE, load_poses, triangulate_with_conf
or:
    from humancalib.core.skeletons import OP_BONE
    from humancalib.core.poses_io import load_poses
"""
from .skeletons import (
    OP_KEY, COCO_KEY, H36M32_KEY, H36M17_KEY, op_to_coco,
    OP_BONE, OP_KEY_SUB, OP_BONE_SUB, mk_bone_sub,
    METRABS_KEY, METRABS_BML87_INDICES, MK,
    METRABS_BONE, METRABS_KEY_SUB, METRABS_BONE_SUB,
    BML87_KEY, B, BML87_BONE, BML87_KEY_SUB, BML87_BONE_SUB,
    get_bone_config,
)
from .geometry import (
    z_test_w2c,
    triangulate_dlt, triangulate_point, triangulate_with_conf,
    project, project_cv2,
)
# NOTE: constraint_mat / constraint_mat_from_single_view are internals of
# triangulate_point and are not re-exported. A `triangulate` used to be
# exported here with the same (pt2d, P) signature as pycalib.calib.triangulate,
# which `from core import *` would shadow in callers -- it was dead and is gone.
from .poses_io import (
    load_poses, load_eldersim_camera, load_eldersim_skeleton_w, load_eldersim,
)
from .filtering import joints2orientations, joints2projections

# NOTE: ``core.gpu`` is deliberately NOT re-exported here. It imports torch and
# nvgpu at module level, which would force every consumer of ``core`` -- the
# whole calibration, bundle-adjustment, evaluation and visualisation chain -- to
# depend on PyTorch. Only the VideoPose3D lifting step needs it, so it imports
# ``core.gpu`` directly. See docs/REFACTOR_PLAN.md T1.4.

# Explicit public API. Without this, every re-export below reads as an unused
# import to static analysers.
__all__ = [
    "OP_KEY",
    "COCO_KEY",
    "H36M32_KEY",
    "H36M17_KEY",
    "op_to_coco",
    "OP_BONE",
    "OP_KEY_SUB",
    "OP_BONE_SUB",
    "mk_bone_sub",
    "METRABS_KEY",
    "METRABS_BML87_INDICES",
    "MK",
    "METRABS_BONE",
    "METRABS_KEY_SUB",
    "METRABS_BONE_SUB",
    "BML87_KEY",
    "B",
    "BML87_BONE",
    "BML87_KEY_SUB",
    "BML87_BONE_SUB",
    "get_bone_config",
    "z_test_w2c",
    "triangulate_dlt",
    "triangulate_point",
    "triangulate_with_conf",
    "project",
    "project_cv2",
    "load_poses",
    "load_eldersim_camera",
    "load_eldersim_skeleton_w",
    "load_eldersim",
    "joints2orientations",
    "joints2projections",
]
