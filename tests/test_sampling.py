"""Frame budget and extraction-rate rules (core/sampling.py)."""
import cv2
import numpy as np
import pytest

from humancalib.core.sampling import (MIN_EXTRACTED, budget_frame_skip, decimate_videos,
                                      decimated_dir, decimation_step)


def test_decimation_reaches_the_target_rate_on_long_high_rate_videos():
    assert decimation_step(200, 1300, 25) == 8          # BioCV: 200 Hz -> 25 Hz
    assert decimation_step(50, 1500, 25) == 2           # I-MOVE-23
    assert decimation_step(60, 1200, 25) == 2           # LBMC


def test_short_clips_are_never_decimated_below_the_minimum():
    assert decimation_step(60, 170, 25) == 1            # a 2 s smartphone clip stays whole
    assert decimation_step(200, 600, 25) == 600 // MIN_EXTRACTED


def test_no_target_or_low_rate_means_no_decimation():
    assert decimation_step(200, 1300, None) == 1
    assert decimation_step(40, 1000, 25) == 1


def test_frame_budget_adapts_the_step_to_the_trial_length():
    assert budget_frame_skip(170, 100) == 2
    assert budget_frame_skip(1300, 100) == 13
    assert budget_frame_skip(60, 100) == 1
    with pytest.raises(ValueError):
        budget_frame_skip(100, 0)


def test_decimate_videos_keeps_one_frame_in_k(tmp_path):
    src = tmp_path / "cam01.avi"
    w = cv2.VideoWriter(str(src), cv2.VideoWriter_fourcc(*"MJPG"), 40.0, (64, 48))
    for i in range(20):
        w.write(np.full((48, 64, 3), i * 10, np.uint8))
    w.release()
    out = decimated_dir(str(tmp_path), 40.0, 4)
    (dst,) = decimate_videos([str(src)], out, 4)
    cap = cv2.VideoCapture(dst)
    assert int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) == 5
    assert cap.get(cv2.CAP_PROP_FPS) == pytest.approx(10.0)
    ok, frame = cap.read()
    assert ok and abs(int(frame.mean()) - 0) <= 3
    ok, frame = cap.read()
    assert ok and abs(int(frame.mean()) - 40) <= 3      # frame 4 of the source
    assert decimate_videos([str(src)], out, 4) == [dst]  # complete output reused


def test_linear_chunks_are_sized_in_seconds(tmp_path):
    from humancalib.pipeline.run_calib_linear import CHUNK_SIZE, chunk_frames
    (tmp_path / "noise_1_0").mkdir()
    (tmp_path / "noise_1_0" / "session.yaml").write_text("frame_rate: 200.0\n")
    assert chunk_frames(str(tmp_path), "noise_1_0", 120) == 24000     # a 7 s BioCV walk fits one chunk
    (tmp_path / "noise_1_0" / "session.yaml").write_text("frame_rate: 5.0\n")
    assert chunk_frames(str(tmp_path), "noise_1_0", 120) == CHUNK_SIZE  # never below the old size
    assert chunk_frames(str(tmp_path), "missing", 120) == CHUNK_SIZE    # no session file: old size
