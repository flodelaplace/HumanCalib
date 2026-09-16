"""Geometric person re-selection, on a rig whose right answer is known.

Four cameras watch a walking subject. A bystander stands one metre in front of
camera 0, so in that camera the bystander's box is the largest and extraction
keeps the wrong person on every frame -- BioCV P06 and P10, camera 08. Given a
calibration, re-selection must pick the subject back in camera 0 and leave the
other cameras alone.
"""
import json
import os

import numpy as np
import pytest

from humancalib.pipeline import reselect_person as rs
from humancalib.pose import candidates as cand

F, J = 12, 26
K = np.array([[1000.0, 0, 960], [0, 1000.0, 540], [0, 0, 1]])


def look_at(center, target):
    z = target - center
    z /= np.linalg.norm(z)
    x = np.cross(z, [0.0, 0.0, 1.0])
    x /= np.linalg.norm(x)
    return np.vstack([x, np.cross(z, x), z])


def rig():
    Rs, ts = [], []
    for a in np.radians([0, 90, 180, 270]):
        C = np.array([5 * np.cos(a), 5 * np.sin(a), 1.5])
        R = look_at(C, np.array([0.0, 0.0, 1.0]))
        Rs.append(R)
        ts.append(-R @ C)
    return np.array(Rs), np.array(ts)


def skeleton(center, rng):
    return center + rng.uniform([-0.25, -0.15, -0.9], [0.25, 0.15, 0.9], (J, 3))


def scene():
    rng = np.random.default_rng(3)
    R, t = rig()
    Ps = np.array([K @ np.hstack([R[c], t[c].reshape(3, 1)]) for c in range(4)])
    body = skeleton(np.zeros(3), rng)
    subject = [body + np.array([-1.0 + 2.0 * f / F, 0.0, 0.9]) for f in range(F)]
    cam0 = -R[0].T @ t[0]
    bystander = skeleton(cam0 + 1.2 * (np.array([0.0, 0.0, 0.9]) - cam0) / np.linalg.norm(cam0), rng)
    return R, t, Ps, subject, bystander


def proj(P, X):
    return rs.project(P, X)


def test_dlt_batch_recovers_exact_points():
    R, t, Ps, subject, _ = scene()
    pts = np.array([proj(P, subject[0]) for P in Ps])
    X = rs.dlt_batch(pts, np.ones((4, J)), Ps)
    assert X == pytest.approx(subject[0], abs=1e-6)


def test_robust_triangulation_drops_the_camera_seeing_someone_else():
    R, t, Ps, subject, bystander = scene()
    pts = np.array([proj(P, subject[0]) for P in Ps])
    pts[0] = proj(Ps[0], bystander)
    X, use = rs.robust_triangulate(pts, np.ones((4, J), bool), Ps, abs_px=50, x_median=5, min_cams=3)
    assert use.tolist() == [False, True, True, True]
    assert X == pytest.approx(subject[0], abs=1e-6)


def test_the_largest_box_is_the_bystander_and_geometry_picks_the_subject():
    R, t, Ps, subject, bystander = scene()
    cameras, current = [], np.zeros((4, F), dtype=int)
    for c in range(4):
        frames = []
        for f in range(F):
            dets = [proj(Ps[c], subject[f])]
            if c == 0:
                dets.insert(0, proj(Ps[0], bystander))
            pts = np.array(dets)
            boxes = np.array([[p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()] for p in pts])
            current[c, f] = cand.largest("rtmpose", boxes, pts, (1080, 1920))
            frames.append((pts, np.ones((len(pts), J), bool), np.ones(len(pts), bool)))
        cameras.append(frames)
    assert (current[0] == 0).all()          # extraction kept the bystander in camera 0
    new, _ = rs.select_by_geometry(cameras, Ps, current)
    assert (new[0] == 1).all()
    assert (new[1:] == 0).all()


def test_candidates_round_trip_and_extraction_rules(tmp_path):
    boxes = np.array([[0, 0, 100, 400, 0.9], [0, 0, 10, 10, 0.8]], float)
    pose2d = np.random.default_rng(0).uniform(0, 500, (2, 87, 2))
    path = tmp_path / "c.npz"
    cand.save_candidates(str(path), [5, 6, 7], [0, 1, 0],
                         [{"box": boxes, "pose2d": pose2d, "pose3d": np.zeros((2, 87, 3))}, None, None],
                         (1080, 1920))
    c = cand.load_candidates(str(path))
    assert c["start"].tolist() == [0, 2, 2, 2]
    assert cand.largest("metrabs", c["box"][:2], c["pose2d"][:2], c["imshape"]) == 0
    tiny = np.array([[0, 0, 10, 10, 0.9]])
    assert cand.largest("metrabs", tiny, pose2d[:1], (1080, 1920)) == -1


def test_main_rewrites_rtmpose_files_and_reports(tmp_path):
    R, t, Ps, subject, bystander = scene()
    prefix, sub = str(tmp_path), "noise_1_0"
    for d in ("2d_joint", "2d_joint_halpe26", "results", "dropped_frames"):
        os.makedirs(os.path.join(prefix, sub if d != "results" else "", d), exist_ok=True)
    cams = {"CAMID": [1, 2, 3, 4], "K": [K.tolist()] * 4, "R_w2c": R.tolist(), "t_w2c": t.reshape(4, 3, 1).tolist(),
            "dist_coeffs": [[0.0] * 5] * 4}
    json.dump(cams, open(os.path.join(prefix, sub, "cameras_G001.json"), "w"))
    json.dump(cams, open(os.path.join(prefix, "results", "linear_1_0_ba.json"), "w"))
    for c in range(4):
        dets = []
        for f in range(F):
            pts = [proj(Ps[c], subject[f])] + ([proj(Ps[0], bystander)] if c == 0 else [])
            pts = np.array(pts)
            boxes = np.array([[p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()] for p in pts])
            dets.append({"box": boxes, "pose2d": pts, "score2d": np.ones((len(pts), J))})
        name = f"A001_P001_G001_C{c + 1:03d}.json"
        cand.save_candidates(cand.candidates_path(prefix, sub, name), range(F), [0] * F, dets, (1080, 1920))

    changed = rs.main(["--prefix", prefix, "--engine", "rtmpose"])
    assert changed == F
    data = json.load(open(os.path.join(prefix, sub, "2d_joint_halpe26", "A001_P001_G001_C001.json")))["data"]
    written = np.array(data[3]["skeleton"][0]["pose"]).reshape(J, 2)
    assert written == pytest.approx(proj(Ps[0], subject[3]), abs=1e-3)
    report = json.load(open(os.path.join(prefix, "results", "person_selection.json")))
    assert report["cameras"]["1"]["changed"] == F and report["cameras"]["2"]["changed"] == 0
    assert not os.path.isdir(os.path.join(prefix, sub, "dropped_frames"))


def test_a_frame_whose_best_detection_is_far_from_the_subject_gets_no_person():
    """Camera 05 of BioCV: when the subject is out of view, the operator at the
    back is the only detection -- closest, and still wrong."""
    selection = np.zeros((2, 6), dtype=int)
    cost = np.array([[3.0, 4.0, 3.5, 900.0, 4.2, 3.8], [5.0, 6.0, 5.5, 60.0, 5.2, np.nan]])
    new = rs.drop_unmatched(selection, cost, abs_px=50, x_median=5)
    assert new[0].tolist() == [0, 0, 0, -1, 0, 0]
    assert new[1].tolist() == [0, 0, 0, -1, 0, 0]


def test_reset_to_largest_restores_extraction_selection(tmp_path):
    R, t, Ps, subject, bystander = scene()
    prefix, sub = str(tmp_path), "noise_1_0"
    for d in ("2d_joint", "2d_joint_halpe26"):
        os.makedirs(os.path.join(prefix, sub, d), exist_ok=True)
    cams = {"CAMID": [1, 2, 3, 4], "K": [K.tolist()] * 4, "R_w2c": R.tolist(), "t_w2c": t.reshape(4, 3, 1).tolist(),
            "dist_coeffs": [[0.0] * 5] * 4}
    json.dump(cams, open(os.path.join(prefix, sub, "cameras_G001.json"), "w"))
    for c in range(4):
        dets = []
        for f in range(F):
            pts = np.array([proj(Ps[c], subject[f])] + ([proj(Ps[0], bystander)] if c == 0 else []))
            boxes = np.array([[p[:, 0].min(), p[:, 1].min(), p[:, 0].max(), p[:, 1].max()] for p in pts])
            dets.append({"box": boxes, "pose2d": pts, "score2d": np.ones((len(pts), J))})
        cand.save_candidates(cand.candidates_path(prefix, sub, f"A001_P001_G001_C{c + 1:03d}.json"),
                             range(F), [0] * F, dets, (1080, 1920))
    assert rs.main(["--prefix", prefix, "--engine", "rtmpose", "--reset_to_largest"]) == 0
    data = json.load(open(os.path.join(prefix, sub, "2d_joint_halpe26", "A001_P001_G001_C001.json")))["data"]
    written = np.array(data[0]["skeleton"][0]["pose"]).reshape(J, 2)
    assert written == pytest.approx(proj(Ps[0], bystander), abs=1e-3)


def test_motion_selection_keeps_the_walker_and_drops_a_seated_operator(tmp_path):
    """Camera 0 sees a seated operator for the whole trial and the walker only in the
    middle; cameras 1-3 see the walker throughout. The operator's box is the largest."""
    from humancalib.pipeline import motion_selection
    fps, F = 50.0, 300
    t_ = np.arange(F) / fps
    cands = []
    for c in range(4):
        dets = []
        for f in range(F):
            swing = 0.5 * np.sin(2 * np.pi * t_[f])
            walker3d = np.zeros((87, 3))
            operator3d = np.zeros((87, 3))
            for side, (hip, knee, ankle) in enumerate(motion_selection.LEGS_3D_BML87):
                sgn = 1 if side == 0 else -1
                walker3d[hip] = [100 * sgn, 0.0, 4000.0]
                walker3d[knee] = [100 * sgn + 200 * sgn * swing, 450.0, 4000.0]
                walker3d[ankle] = [100 * sgn + 400 * sgn * swing, 900.0, 4000.0]
                operator3d[hip], operator3d[knee], operator3d[ankle] = [0, 0, 3000], [0, 450, 3000], [0, 900, 3000]
            rng = np.random.default_rng(f)
            boxes, p3, p2 = [[800 + f, 300, 200, 600, 0.9]], [walker3d], [rng.uniform(0, 1000, (87, 2))]
            if c == 0:
                in_view = 80 <= f < 220
                boxes = [[100, 200, 400, 800, 0.9]] + (boxes if in_view else [])
                p3 = [operator3d] + (p3 if in_view else [])
                p2 = [rng.uniform(0, 1000, (87, 2))] + (p2 if in_view else [])
            dets.append({"box": np.array(boxes), "pose2d": np.array(p2), "pose3d": np.array(p3)})
        path = str(tmp_path / f"c{c}.npz")
        cand.save_candidates(path, range(F), [0] * F, dets, (1080, 1920))
        cands.append(cand.load_candidates(path))
    sel = motion_selection.select(cands, fps, "metrabs")
    assert (sel[0][110:190] == 1).all()                    # the walker, not the larger operator
    assert (sel[0][:60] == -1).all() and (sel[0][240:] == -1).all()
    assert (sel[1][40:260] == 0).all()


def test_rtmpose_poses_are_written_undistorted(tmp_path):
    """The calibration is a pinhole model: the MeTRAbs path has always undistorted its
    keypoints, the RTMPose path did not, which biased every comparison between them."""
    import cv2
    from humancalib.pipeline.reselect_person import rewrite_rtmpose
    K = np.array([[1000.0, 0, 960], [0, 1000.0, 540], [0, 0, 1]])
    dist = np.array([-0.15, 0.08, 0.0, 0.0])
    raw = np.random.default_rng(0).uniform(100, 1500, (1, J, 2))
    path = str(tmp_path / "c.npz")
    cand.save_candidates(path, [0], [0], [{"box": np.array([[0, 0, 100, 200]]), "pose2d": raw,
                                           "score2d": np.ones((1, J))}], (1080, 1920))
    c = cand.load_candidates(path)
    for d in ("2d_joint", "2d_joint_halpe26"):
        os.makedirs(tmp_path / "noise_1_0" / d)
    rewrite_rtmpose(str(tmp_path), "noise_1_0", "A001_P001_G001_C001.json", c, [0], K, dist)
    written = np.array(json.load(open(tmp_path / "noise_1_0" / "2d_joint_halpe26" / "A001_P001_G001_C001.json")
                                 )["data"][0]["skeleton"][0]["pose"]).reshape(J, 2)
    expected = cv2.undistortPoints(raw[0].reshape(-1, 1, 2).astype(np.float64), K, dist, P=K).reshape(J, 2)
    assert written == pytest.approx(expected, abs=1e-3)
    assert np.abs(written - raw[0]).max() > 1.0        # it really moved the points


def test_motion_selection_keeps_a_camera_the_subject_walks_straight_at(tmp_path):
    """The swing is measured in the image for RTMPose, so the camera the subject walks
    towards sees it foreshortened and flags walking on a few frames only -- BioCV camera
    04, 8 % against 60-85 % for its neighbours. The linear stage wants every bone in
    every camera, so that camera must not be emptied: it still sees someone moving on
    every frame, unlike the camera that only has a seated operator, and follows the
    other cameras' window instead."""
    from humancalib.pipeline import motion_selection
    fps, F = 50.0, 300
    t_ = np.arange(F) / fps
    cands = []
    for c in range(4):
        scale, lift = (0.2, 30.0) if c == 0 else (1.0, 20.0)   # camera 0 sees the walk head-on
        dets = []
        for f in range(F):
            swing, foot = np.sin(2 * np.pi * t_[f]), abs(np.sin(4 * np.pi * t_[f]))
            pose = np.zeros((J, 2))
            for side, (hip, knee, ankle) in enumerate(motion_selection.LEGS_2D_HALPE26):
                sgn = 1 if side == 0 else -1
                pose[hip] = [500 + 20 * sgn, 300.0]
                pose[knee] = [500 + 20 * sgn + scale * 100 * sgn * swing, 500.0]
                pose[ankle] = [500 + 20 * sgn + scale * 200 * sgn * swing, 700.0 - lift * foot]
            dets.append({"box": np.array([[400.0, 250.0, 600.0, 750.0]]),
                         "pose2d": pose[None], "score2d": np.ones((1, J))})
        path = str(tmp_path / f"c{c}.npz")
        cand.save_candidates(path, range(F), [0] * F, dets, (1080, 1920))
        cands.append(cand.load_candidates(path))

    gated = motion_selection.select(cands, fps, "rtmpose", gate="camera")
    adaptive = motion_selection.select(cands, fps, "rtmpose")
    assert (gated[0] >= 0).mean() < 0.2                  # emptied by its own verdict
    assert (adaptive[0] >= 0).mean() > 0.7               # rescued by the other cameras'
    for c in range(1, 4):                                # cameras that see the swing: untouched
        assert (adaptive[c] == gated[c]).all()
