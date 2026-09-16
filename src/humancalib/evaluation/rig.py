"""One representation of a camera rig, whatever file it came from.

Every gold calibration is converted to this on reading, so the metrics never
see a dataset's conventions. The convention here is OpenCV's and Pose2Sim's:

    x_cam = R @ X_world + t        (R, t: world to camera; t in metres)

so a camera's optical centre is C = -R.T @ t.
"""
from dataclasses import dataclass, field

import cv2
import numpy as np
import toml

from humancalib.core.geometry import orthonormalize  # noqa: F401  (re-exported)


@dataclass
class Camera:
    name: str
    size: tuple                      # (width, height) in pixels
    K: np.ndarray                    # 3x3
    dist: np.ndarray                 # k1 k2 p1 p2 [k3]
    R: np.ndarray = field(default_factory=lambda: np.eye(3))
    t: np.ndarray = field(default_factory=lambda: np.zeros(3))

    @property
    def center(self):
        return -self.R.T @ self.t

    def projection(self):
        return self.K @ np.hstack([self.R, self.t.reshape(3, 1)])


def read_pose2sim_toml(path):
    """Cameras of a Pose2Sim calibration TOML, in file order; [metadata] is skipped."""
    data = toml.load(path)
    cameras = []
    for section, c in data.items():
        if section == "metadata" or not isinstance(c, dict) or "matrix" not in c:
            continue
        R = cv2.Rodrigues(np.asarray(c.get("rotation", [0, 0, 0]), dtype=float))[0]
        cameras.append(Camera(
            name=str(c.get("name", section)),
            size=tuple(float(v) for v in c["size"]),
            K=np.asarray(c["matrix"], dtype=float),
            dist=np.asarray(c["distortions"], dtype=float),
            R=R,
            t=np.asarray(c.get("translation", [0, 0, 0]), dtype=float).ravel(),
        ))
    return cameras


def write_pose2sim_toml(cameras, path, extrinsics=True):
    """Write a Pose2Sim calibration TOML.

    With extrinsics=False the poses are written as zeros: the file then carries
    intrinsics only, which is what HumanCalib takes as input. The rotation and
    translation lines are still present, because HumanCalib's exporter fills
    its result into exactly those lines.

    Pose2Sim reads four distortion coefficients. A non-zero k3 cannot be
    represented and is refused rather than dropped silently.
    """
    lines = []
    for cam in cameras:
        dist = np.asarray(cam.dist, dtype=float).ravel()
        if dist.size > 4 and np.any(np.abs(dist[4:]) > 0):
            raise ValueError(f"{cam.name}: k3 = {dist[4]} cannot be written to a Pose2Sim TOML")
        rvec = cv2.Rodrigues(cam.R)[0].ravel() if extrinsics else np.zeros(3)
        tvec = np.asarray(cam.t, dtype=float).ravel() if extrinsics else np.zeros(3)
        K = np.asarray(cam.K, dtype=float)
        lines += [
            f"[{cam.name}]",
            f'name = "{cam.name}"',
            f"size = [{float(cam.size[0])}, {float(cam.size[1])}]",
            "matrix = [" + ", ".join("[" + ", ".join(repr(float(v)) for v in row) + "]" for row in K) + "]",
            "distortions = [" + ", ".join(repr(float(v)) for v in dist[:4]) + "]",
            "rotation = [" + ", ".join(repr(float(v)) for v in rvec) + "]",
            "translation = [" + ", ".join(repr(float(v)) for v in tvec) + "]",
            "fisheye = false",
            "",
        ]
    lines += ["[metadata]", "adjusted = false", "error = 0.0", ""]
    with open(path, "w") as f:
        f.write("\n".join(lines))
