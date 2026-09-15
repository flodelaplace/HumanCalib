"""Metrics comparing an estimated camera rig with a gold one.

Rationale and choices are in docs/EVALUATION_PROTOCOL.md. In short, an
extrinsic calibration from a moving person is defined up to a similarity
(rotation, translation, scale); HumanCalib then fixes scale from the subject's
stature and "up" from their posture. So:

* the primary metrics are invariant to the similarity -- relative rotation
  and relative translation *direction* between cameras -- and need no alignment;
* scale and verticality are measured separately, since they are exactly the
  parts HumanCalib estimates from the person;
* absolute camera errors come after a 4-DoF alignment (yaw about the vertical
  + translation, scale fixed at 1), which leaves scale and tilt errors in, and
  after a 7-DoF similarity for shape alone. Both leave-one-out by default: a
  camera never takes part in the alignment it is scored against.

Rigs are lists of humancalib.evaluation.rig.Camera, in the same camera order.
"""
from itertools import combinations

import numpy as np

from humancalib.evaluation.rig import orthonormalize


# --- elementary geometry ----------------------------------------------------------------------

def rotation_angle_deg(R):
    """Geodesic angle of a rotation matrix: arccos((tr R - 1) / 2), in degrees.

    Refuses a matrix that is not a rotation. The trace formula does not fail on
    one -- it clips, and a scaled or sheared matrix silently reads as 0 degrees.
    """
    R = np.asarray(R, float)
    if np.abs(R @ R.T - np.eye(3)).max() > 1e-6 or np.linalg.det(R) <= 0:
        raise ValueError("not a rotation matrix; project it with rig.orthonormalize first")
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0))))


def angle_between_deg(u, v):
    u = np.asarray(u, float) / np.linalg.norm(u)
    v = np.asarray(v, float) / np.linalg.norm(v)
    return float(np.degrees(np.arccos(np.clip(u @ v, -1.0, 1.0))))


def rotation_between(u, v):
    """The smallest rotation taking direction u onto direction v."""
    u = np.asarray(u, float) / np.linalg.norm(u)
    v = np.asarray(v, float) / np.linalg.norm(v)
    axis, c = np.cross(u, v), float(u @ v)
    if np.linalg.norm(axis) < 1e-12:
        if c > 0:
            return np.eye(3)
        # Opposite directions: half-turn about any axis orthogonal to u.
        w = np.cross(u, [1.0, 0.0, 0.0] if abs(u[0]) < 0.9 else [0.0, 1.0, 0.0])
        w /= np.linalg.norm(w)
        return 2.0 * np.outer(w, w) - np.eye(3)
    S = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    return np.eye(3) + S + S @ S / (1.0 + c)


def umeyama(src, dst, with_scale=True):
    """(s, R, t) minimising sum ||dst - (s R src + t)||^2 (Umeyama 1991)."""
    src, dst = np.asarray(src, float), np.asarray(dst, float)
    mu_s, mu_d = src.mean(0), dst.mean(0)
    a, b = src - mu_s, dst - mu_d
    U, S, Vt = np.linalg.svd(b.T @ a / len(src))
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(U @ Vt))])
    R = U @ D @ Vt
    s = float(np.trace(np.diag(S) @ D) / (a ** 2).sum(1).mean()) if with_scale else 1.0
    return s, R, mu_d - s * R @ mu_s


def yaw_align(src, dst, up_src, up_dst):
    """(R, t) with dst ~ R src + t, where R maps up_src onto up_dst and is free
    only in yaw about that axis; scale is fixed at 1."""
    Ms, Md = rotation_between(up_src, [0, 0, 1]), rotation_between(up_dst, [0, 0, 1])
    a, b = np.asarray(src, float) @ Ms.T, np.asarray(dst, float) @ Md.T
    ac, bc = a - a.mean(0), b - b.mean(0)
    theta = np.arctan2((ac[:, 0] * bc[:, 1] - ac[:, 1] * bc[:, 0]).sum(),
                       (ac[:, 0] * bc[:, 0] + ac[:, 1] * bc[:, 1]).sum())
    c, s = np.cos(theta), np.sin(theta)
    Rz = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    t = b.mean(0) - Rz @ a.mean(0)
    return Md.T @ Rz @ Ms, Md.T @ t


def _poses(cameras):
    return np.array([c.R for c in cameras]), np.array([c.center for c in cameras])


def _check(est, gold):
    if len(est) != len(gold):
        raise ValueError(f"{len(est)} estimated cameras, {len(gold)} gold cameras")
    if len(est) < 3:
        raise ValueError("at least 3 cameras are needed")


# --- similarity-invariant metrics ---------------------------------------------------------------

def pairwise_errors(est, gold):
    """One row per camera pair: relative rotation error, relative translation
    direction error (in camera i's frame), and baseline length ratio est/gold.

    Rows are not independent -- C cameras give C(C-1)/2 pairs from 6C-7 degrees
    of freedom -- so they describe a distribution; they are not samples.
    """
    _check(est, gold)
    Re, Ce = _poses(est)
    Rg, Cg = _poses(gold)
    rows = []
    for i, j in combinations(range(len(est)), 2):
        rows.append({
            "cam_i": gold[i].name, "cam_j": gold[j].name,
            "rot_deg": rotation_angle_deg((Re[i] @ Re[j].T) @ (Rg[i] @ Rg[j].T).T),
            "dir_deg": angle_between_deg(Re[i] @ (Ce[j] - Ce[i]), Rg[i] @ (Cg[j] - Cg[i])),
            "baseline_gold_m": float(np.linalg.norm(Cg[j] - Cg[i])),
            "baseline_ratio": float(np.linalg.norm(Ce[j] - Ce[i]) / np.linalg.norm(Cg[j] - Cg[i])),
        })
    return rows


def auc(errors, threshold):
    """Area under the cumulative error curve up to `threshold`, normalised to [0, 1]."""
    errors = np.asarray(errors, float)
    grid = np.linspace(0.0, threshold, 1001)
    return float(np.mean([(errors <= g).mean() for g in grid]))


def rotation_gauge(est, gold):
    """Rotation Q from the estimated world to the gold world, from camera
    orientations alone (chordal mean of Rg_i^T Re_i). Orientations are the
    best-determined part of a calibration, so this avoids the error that fitting
    to a handful of camera centres would absorb."""
    return orthonormalize(sum(g.R.T @ e.R for e, g in zip(est, gold)))


def gravity_error_deg(est, gold, up_est, up_gold):
    """Angle between the estimated and the gold vertical, compared through the
    rotation gauge."""
    return angle_between_deg(rotation_gauge(est, gold) @ np.asarray(up_est, float), up_gold)


# --- alignment-based metrics --------------------------------------------------------------------

def absolute_errors(est, gold, method="4dof", up_est=None, up_gold=None, leave_one_out=True):
    """Per camera: centre error (m) and orientation error (deg) after alignment.

    method "4dof": yaw + translation, scale 1 -- needs up_est and up_gold.
    method "7dof": full similarity on centres -- shape only.
    """
    _check(est, gold)
    Re, Ce = _poses(est)
    Rg, Cg = _poses(gold)
    n = len(est)
    rows = []
    for k in range(n):
        fit = [i for i in range(n) if i != k] if leave_one_out else list(range(n))
        if method == "4dof":
            if up_est is None or up_gold is None:
                raise ValueError("4dof alignment needs up_est and up_gold")
            T, b = yaw_align(Ce[fit], Cg[fit], up_est, up_gold)
            s = 1.0
        elif method == "7dof":
            s, T, b = umeyama(Ce[fit], Cg[fit], with_scale=True)
        else:
            raise ValueError(f"unknown method {method!r}")
        C = s * T @ Ce[k] + b
        R = Re[k] @ T.T
        rows.append({
            "cam": gold[k].name,
            "pos_err_m": float(np.linalg.norm(C - Cg[k])),
            "rot_err_deg": rotation_angle_deg(R @ Rg[k].T),
        })
    return rows


# --- summary ------------------------------------------------------------------------------------

def _stats(values, prefix):
    v = np.asarray(values, float)
    return {f"{prefix}_median": float(np.median(v)), f"{prefix}_mean": float(v.mean()),
            f"{prefix}_max": float(v.max())}


def compare_rigs(est, gold, up_est, up_gold):
    """Every metric of the protocol for one estimated rig. Returns
    {"summary": {...}, "pairs": [...], "cameras": [...]}."""
    pairs = pairwise_errors(est, gold)
    rot = [p["rot_deg"] for p in pairs]
    dirs = [p["dir_deg"] for p in pairs]
    worst = np.maximum(rot, dirs)
    ratios = np.array([p["baseline_ratio"] for p in pairs])
    s_umeyama = umeyama(np.array([c.center for c in est]), np.array([c.center for c in gold]))[0]

    summary = {
        "n_cameras": len(est),
        **_stats(rot, "rel_rot_deg"),
        **_stats(dirs, "rel_dir_deg"),
        **{f"auc_{t}deg": auc(worst, t) for t in (1, 2, 5, 10)},
        "scale_ratio_median": float(np.median(ratios)),
        "scale_ratio_umeyama": float(1.0 / s_umeyama),
        **_stats(np.abs(ratios / np.median(ratios) - 1.0) * 100.0, "shape_baseline_pct"),
        "gravity_deg": gravity_error_deg(est, gold, up_est, up_gold),
    }

    cameras = [{"cam": g.name} for g in gold]
    for method in ("4dof", "7dof"):
        rows = absolute_errors(est, gold, method, up_est, up_gold, leave_one_out=True)
        summary.update(_stats([r["pos_err_m"] * 1000.0 for r in rows], f"abs{method}_pos_mm"))
        summary.update(_stats([r["rot_err_deg"] for r in rows], f"abs{method}_rot_deg"))
        for cam, r in zip(cameras, rows):
            cam[f"abs{method}_pos_mm"] = r["pos_err_m"] * 1000.0
            cam[f"abs{method}_rot_deg"] = r["rot_err_deg"]
    for cam in cameras:
        mine = [p for p in pairs if cam["cam"] in (p["cam_i"], p["cam_j"])]
        cam["pair_rot_median_deg"] = float(np.median([p["rot_deg"] for p in mine]))
        cam["pair_dir_median_deg"] = float(np.median([p["dir_deg"] for p in mine]))
    return {"summary": summary, "pairs": pairs, "cameras": cameras}
