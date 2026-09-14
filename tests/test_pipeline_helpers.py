"""The logic that used to live inside calibrate.sh, now testable.

Two Python heredocs embedded in a shell script -- the pose-cache check and the
frame-mapping writer -- plus the camera ordering and the bundle-adjustment retry
loop. None of it could be tested while it was a string inside bash.
"""
import json
import os

import pytest

from humancalib.core.videos import camera_names, list_videos
from humancalib.pipeline import run_ba
from humancalib.pipeline.frame_mapping import write_frame_mapping
from humancalib.pipeline.poses_cache import poses_are_cached


# --- camera order -------------------------------------------------------------

def _touch(d, *names):
    d.mkdir(parents=True, exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"")


def test_camera_order_is_lexicographic_like_the_pose_step(tmp_path):
    """The tenth camera is where natural and lexicographic order part ways.

    calibrate.sh named cameras in natural order while the pose step numbered
    them lexicographically, so from cam10 on, intrinsics went to the wrong
    camera. One order, the pose step's, everywhere.
    """
    _touch(tmp_path, "cam1.mp4", "cam2.mp4", "cam10.mp4")
    assert camera_names(tmp_path) == ["cam1", "cam10", "cam2"]


def test_every_container_the_pose_step_reads_is_listed(tmp_path):
    _touch(tmp_path, "a.mp4", "b.avi", "c.mov", "d.mkv", "e.MP4", "f.AVI",
           "notes.txt", "calib.toml", "a.dropped.json")
    assert camera_names(tmp_path) == ["a", "b", "c", "d", "e", "f"]


def test_a_video_is_never_listed_twice(tmp_path):
    _touch(tmp_path, "cam01.mp4")
    assert len(list_videos(tmp_path)) == 1


# --- pose cache -------------------------------------------------------------------

def _poses(root, n_cams=2, frames=range(0, 10), sub3d=True):
    for kind in ("2d_joint", "3d_joint") if sub3d else ("2d_joint",):
        d = root / "noise_1_0" / kind
        d.mkdir(parents=True, exist_ok=True)
        for c in range(1, n_cams + 1):
            doc = {"data": [{"frame_index": f,
                             "skeleton": [{"pose": [0.0, 0.0], "score": [1.0]}]}
                            for f in frames]}
            (d / f"A001_P001_G001_C{c:03d}.json").write_text(json.dumps(doc))


def test_no_extraction_means_no_cache(tmp_path):
    assert poses_are_cached(tmp_path, "noise_1_0") is None


def test_a_full_run_is_reused_when_no_range_is_requested(tmp_path):
    _poses(tmp_path)
    hit = poses_are_cached(tmp_path, "noise_1_0")
    assert hit is not None and (hit.start, hit.end, hit.n_cameras) == (0, 9, 2)


def test_a_different_range_is_re_extracted(tmp_path):
    _poses(tmp_path, frames=range(650, 700))
    assert poses_are_cached(tmp_path, "noise_1_0", 650, 699) is not None
    assert poses_are_cached(tmp_path, "noise_1_0", 650, 800) is None
    assert poses_are_cached(tmp_path, "noise_1_0") is None       # start defaults to 0


def test_2d_without_matching_3d_is_not_a_cache(tmp_path):
    _poses(tmp_path, sub3d=False)
    assert poses_are_cached(tmp_path, "noise_1_0") is None


def test_a_corrupt_pose_file_is_not_a_cache(tmp_path):
    _poses(tmp_path)
    (tmp_path / "noise_1_0" / "2d_joint" / "A001_P001_G001_C001.json").write_text("{trunc")
    assert poses_are_cached(tmp_path, "noise_1_0") is None


# --- frame mapping --------------------------------------------------------------

def test_frame_mapping_uses_absolute_frame_numbers(tmp_path):
    _poses(tmp_path, frames=range(650, 660))
    path = write_frame_mapping(tmp_path, "noise_1_0", 1, 650, 659)

    doc = json.loads(open(path).read())
    assert os.path.basename(path) == "skeleton_w_G001.json"
    assert doc["frame_indices"] == list(range(650, 660))
    assert len(doc["skeleton"]) == 10
    assert len(doc["skeleton"][0]) == 1              # joint count read from the 2D poses
    assert doc["skeleton"][0][0] == [None, None, None]


def test_frame_mapping_defaults_to_25_joints_without_poses(tmp_path):
    path = write_frame_mapping(tmp_path, "noise_1_0", 1, 0, 2)
    assert len(json.loads(open(path).read())["skeleton"][0]) == 25


def test_frame_mapping_rejects_an_inverted_range(tmp_path):
    with pytest.raises(ValueError):
        write_frame_mapping(tmp_path, "noise_1_0", 1, 10, 5)


# --- bundle adjustment runner -------------------------------------------------------

def test_run_ba_named_options_have_the_pipeline_defaults():
    opts = run_ba.build_parser().parse_args(["--prefix", "/out"])
    assert (opts.frame_skip, opts.lambda1, opts.lambda2, opts.target) == (10, 1.0, 1.0, "linear_1_0")
    assert (opts.obs_mask, opts.save_obs_mask, opts.ba_jac) == ("false", "true", "analytic")


def test_run_ba_still_accepts_the_legacy_positional_form():
    legacy = ["/out", "1", "1", "1", "5", "1.", "1.", "linear_1_0", "MyDataset",
              "false", "true", "0.4", "numeric"]
    opts = run_ba.parse(legacy)
    assert (opts.prefix, opts.frame_skip, opts.conf_threshold, opts.ba_jac) == ("/out", 5, 0.4, "numeric")


class _Result:
    def __init__(self, rc):
        self.returncode = rc


def test_bundle_adjustment_retries_with_a_larger_frame_skip():
    seen = []

    def runner(cmd):
        seen.append(int(cmd[cmd.index("--frame_skip") + 1]))
        return _Result(0 if len(seen) == 3 else 1)

    opts = run_ba.build_parser().parse_args(["--prefix", "/out", "--frame_skip", "10"])
    assert run_ba.run(opts, runner=runner) == 20
    assert seen == [10, 15, 20]


def test_bundle_adjustment_gives_up_past_the_cap():
    seen = []

    def runner(cmd):
        seen.append(int(cmd[cmd.index("--frame_skip") + 1]))
        return _Result(1)

    opts = run_ba.build_parser().parse_args(["--prefix", "/out", "--frame_skip", "50"])
    with pytest.raises(run_ba.BundleAdjustmentFailed):
        run_ba.run(opts, runner=runner)
    assert seen == [50, 55, 60]


def test_each_attempt_is_a_fresh_interpreter():
    """A process that ran out of memory cannot be trusted to have released it."""
    opts = run_ba.build_parser().parse_args(["--prefix", "/out"])
    cmd = run_ba.ba_command(opts, 10)
    assert cmd[1:3] == ["-m", "humancalib.calibration.ba"]
    assert cmd[cmd.index("--th_obs_mask") + 1] == "20"
