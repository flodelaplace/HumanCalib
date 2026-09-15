"""Initial person selection by walking motion, decided in continuous segments.

The largest detection is the subject only while the subject is in view. In a
camera the subject enters late, or leaves early, the largest detection is
whoever else is there -- the operator seated at the back of BioCV camera 05 --
and that pollutes the first calibration enough for geometric re-selection to
lock onto the wrong person (P18_WALK_01).

The subject is the person walking. Walking is recognised by the legs, not the
detection box: a box barely moves when the subject walks straight at the
camera, while the ankles keep swinging about the hips. So, per camera:

1. each detection is followed for +-WINDOW_S by nearest box centre -- short
   enough that identities cannot mix -- and its leg swing speed is measured
   (ankle relative to hip, in leg lengths per second; 3D for MeTRAbs, whose
   camera-frame skeleton makes it independent of the walking direction, 2D for
   RTMPose);
2. a frame is "walking" for that camera when some detection swings faster than
   SPEED_THR; the flag is then smoothed by a majority vote over +-SEGMENT_S, so
   a stance phase or a turn does not break a passage, and a stray frame does
   not start one;
3. a frame counts for the trial only when at least half the cameras are
   walking -- before the subject arrives and after they leave, it is dropped
   everywhere, however many cameras still see an operator;
4. in a walking segment the camera keeps its fastest-swinging detection; out
   of one it keeps no one.

Offline on six BioCV walks against the gold-oracle selection: wrong person
2-5 % of kept frames (largest box: 8-20 %), 84-96 % of the subject's frames
kept. Thresholds are physical and were set before that test.
"""
import math

import numpy as np

from humancalib.pose import candidates as cand

WINDOW_S = 0.2
SEGMENT_S = 0.25
SPEED_THR = 0.5      # leg lengths per second: walking about 1.5, standing still under 0.1

# (hip, knee, ankle) left and right
LEGS_3D_BML87 = ((73, 75, 71), (81, 83, 79))
LEGS_2D_HALPE26 = ((11, 13, 15), (12, 14, 16))


def leg_speeds(c, fps, engine):
    """(P,) leg swing speed of every detection, leg lengths per second; NaN if it cannot be followed."""
    box = np.asarray(c["box"], float)
    if engine == "metrabs":
        ctr = np.c_[box[:, 0] + box[:, 2] / 2, box[:, 1] + box[:, 3] / 2]
        hgt = box[:, 3]
        pose, legs = c["pose3d"], LEGS_3D_BML87
    else:
        ctr = np.c_[(box[:, 0] + box[:, 2]) / 2, (box[:, 1] + box[:, 3]) / 2]
        hgt = box[:, 3] - box[:, 1]
        pose, legs = c["pose2d"], LEGS_2D_HALPE26
    swing = np.concatenate([pose[:, a] - pose[:, h] for h, _, a in legs], axis=1)
    dim = pose.shape[2]
    leg = np.mean([np.linalg.norm(pose[:, h] - pose[:, k], axis=1) + np.linalg.norm(pose[:, k] - pose[:, a], axis=1)
                   for h, k, a in legs], axis=0)
    k = max(1, int(round(WINDOW_S * fps)))
    owner, start, F = c["owner"], c["start"], len(c["frames"])

    def follow(i, row):
        if row < 0 or row >= F or start[row + 1] == start[row]:
            return -1
        s, e = start[row], start[row + 1]
        d = np.linalg.norm(ctr[s:e] - ctr[i], axis=1)
        j = int(np.argmin(d))
        return s + j if d[j] < 0.5 * max(hgt[i], 1e-6) else -1

    speed = np.full(len(box), np.nan)
    for i in range(len(box)):
        r = owner[i]
        a, b = follow(i, r - k), follow(i, r + k)
        if a >= 0 and b >= 0:
            dv, dt = swing[b] - swing[a], 2 * k / fps
        elif a >= 0 or b >= 0:
            dv, dt = (swing[i] - swing[a]) if a >= 0 else (swing[b] - swing[i]), k / fps
        else:
            continue
        per_leg = [np.linalg.norm(dv[n * dim:(n + 1) * dim]) for n in range(len(legs))]
        speed[i] = np.mean(per_leg) / dt / max(leg[i], 1e-6)
    return speed


def select(cands, fps, engine, speed_thr=SPEED_THR, segment_s=SEGMENT_S):
    """Per camera, the detection index kept on each of its frames (-1 for none)."""
    C = len(cands)
    half = max(1, int(round(segment_s * fps)))
    walking, fastest = [], []
    for c in cands:
        F = len(c["frames"])
        speed = leg_speeds(c, fps, engine)
        flag, best = np.zeros(F, bool), np.full(F, -1)
        for r in range(F):
            s, e = c["start"][r], c["start"][r + 1]
            if c["status"][r] != cand.STATUS_OK or e == s:
                continue
            ok = cand.plausible(engine, c["box"][s:e], c["pose2d"][s:e], c["imshape"])
            sp = np.where(ok, np.nan_to_num(speed[s:e], nan=-1.0), -1.0)
            if sp.max() >= 0:
                best[r] = int(np.argmax(sp))
            flag[r] = sp.max() >= speed_thr
        csum = np.concatenate([[0], np.cumsum(flag)])
        idx = np.arange(F)
        lo, hi = np.clip(idx - half, 0, F), np.clip(idx + half + 1, 0, F)
        walking.append((csum[hi] - csum[lo]) * 2 > (hi - lo))
        fastest.append(best)

    count = {}
    for ci, c in enumerate(cands):
        for r, f in enumerate(c["frames"].tolist()):
            count[f] = count.get(f, 0) + int(walking[ci][r])
    need = math.ceil(C / 2)
    out = []
    for ci, c in enumerate(cands):
        sel = np.full(len(c["frames"]), -1)
        for r, f in enumerate(c["frames"].tolist()):
            if walking[ci][r] and count[f] >= need:
                sel[r] = fastest[ci][r]
        out.append(sel)
    return out
