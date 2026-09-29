"""World-frame conventions at the boundary with Pose2Sim and OpenSim.

Internally, after scaling (postprocessing/scale_scene.py), the world has its origin under the
subject's heels, X along the heel-to-heel direction, and Y pointing DOWN, as camera axes do.
The JSON calibrations and every evaluation use that frame.

Outside, two other conventions apply:

* Pose2Sim reads a calibration TOML in a Z-UP world: its triangulation turns the points into
  Y-up with `zup2yup` before writing the .trc for OpenSim. A TOML in our Y-down frame would
  give a skeleton lying on its side, with gravity along the wrong axis in the inverse
  kinematics. The exported TOML is therefore rotated into Z-up.
* OpenSim reads .trc files in a Y-UP world. The exported .trc uses exactly the axes Pose2Sim
  would produce from our TOML, so the two can be mixed.
"""
import numpy as np

# internal (Y down) -> Pose2Sim calibration world (Z up); a rotation, det = +1
WORLD_TO_ZUP = np.array([[1.0, 0.0, 0.0],
                         [0.0, 0.0, 1.0],
                         [0.0, -1.0, 0.0]])

# Pose2Sim's zup2yup: (X, Y, Z) Z-up -> (Y, Z, X) Y-up
ZUP_TO_YUP = np.array([[0.0, 1.0, 0.0],
                       [0.0, 0.0, 1.0],
                       [1.0, 0.0, 0.0]])

# internal (Y down) -> .trc for OpenSim (Y up), as Pose2Sim would write it from our TOML
WORLD_TO_TRC = ZUP_TO_YUP @ WORLD_TO_ZUP


def extrinsics_in(frame, R_w2c, t_w2c):
    """Camera extrinsics after rotating the world by `frame` (x' = frame @ x).

    x_cam = R x + t = (R frame^T) x' + t: rotations change, translations do not.
    """
    return np.asarray(R_w2c) @ np.asarray(frame).T, np.asarray(t_w2c)


def points_in(frame, X):
    """Points (..., 3) expressed in the rotated world."""
    return np.asarray(X) @ np.asarray(frame).T
