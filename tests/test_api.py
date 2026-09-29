"""humancalib.calibrate(): the options reach the pipeline as `humancalib run` would get them."""
import os

import pytest

import humancalib
from humancalib import api, cli


@pytest.fixture
def captured(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cfg):
        seen["cfg"] = cfg
        os.makedirs(os.path.join(cfg.output_dir, "results"), exist_ok=True)
        open(os.path.join(cfg.output_dir, "results", "Calib_scene_calibrated.toml"), "w").close()
        return 0

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    return seen


def test_defaults_are_the_evaluated_method(captured, tmp_path):
    out = tmp_path / "out"
    toml = humancalib.calibrate("videos", "intr.toml", out, 1.78)
    cfg = captured["cfg"]
    assert toml == os.path.join(str(out), "results", "Calib_scene_calibrated.toml")
    assert (cfg.pose_engine, cfg.person_selection, cfg.scale_method) == ("metrabs", "motion", "stature")
    assert cfg.height == 1.78 and cfg.ref_frame is None and cfg.device == "cuda"
    assert cfg.frame_budget == 100 and cfg.frame_skip is None and cfg.extract_fps is None


def test_options_are_forwarded(captured, tmp_path):
    humancalib.calibrate("videos", "intr.toml", tmp_path, 1.6, ref_frame=12, device="cpu",
                         extract_fps=25, frame_budget=60, auto_outlier_drop=False, save_video=True)
    cfg = captured["cfg"]
    assert cfg.ref_frame == 12 and cfg.device == "cpu"
    assert cfg.extract_fps == 25 and cfg.frame_budget == 60
    assert cfg.auto_outlier_drop is False and cfg.save_video is True


def test_unknown_option_is_a_calibration_error(captured, tmp_path):
    with pytest.raises(api.CalibrationError):
        humancalib.calibrate("videos", "intr.toml", tmp_path, 1.7, not_an_option=1)


def test_pipeline_failure_is_a_calibration_error(monkeypatch, tmp_path):
    def fail(cfg):
        raise cli.PipelineError("step 'ba' failed")
    monkeypatch.setattr(cli, "run_pipeline", fail)
    with pytest.raises(api.CalibrationError, match="ba"):
        humancalib.calibrate("videos", "intr.toml", tmp_path, 1.7)


def test_missing_toml_is_a_calibration_error(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "run_pipeline", lambda cfg: 0)
    with pytest.raises(api.CalibrationError, match="without writing"):
        humancalib.calibrate("videos", "intr.toml", tmp_path, 1.7)
