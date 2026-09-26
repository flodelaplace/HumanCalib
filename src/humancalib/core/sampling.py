"""How many frames the pipeline extracts and calibrates on.

Two measured facts behind the defaults (docs/METHOD.md, "How many frames"):

* the geometric steps need about 30 to 60 frames spread over the walk; beyond that, more
  frames change nothing (58 runs on five datasets), while the choice of frames moves the
  result by 0.1-0.25 deg. So calibration uses a frame *budget*, and the step between
  frames follows from the trial's length, instead of one step for every trial: a fixed
  step of 10 kept 17 frames of a 2 s smartphone clip and 1 500 of a 30 s walk at 50 Hz;
* pose extraction dominates the run time, and extracting at 25 Hz instead of 200 Hz gave
  the same calibration on BioCV, 6 to 8 times faster. The steps that follow a person over
  time -- motion-based selection (+-0.2 s windows), smoothing, the scale over the gait
  cycle -- need consecutive frames, so extraction runs on a regularly decimated video,
  never on scattered frames, and never below MIN_EXTRACTED frames: a short clip is kept
  whole.
"""
import os

MIN_EXTRACTED = 150


def decimation_step(fps, n_frames, target_fps, min_frames=MIN_EXTRACTED):
    """Keep one frame in k: as many as reaching target_fps allows, without going below
    min_frames frames. 1 (no decimation) when target_fps is None."""
    if not target_fps or fps <= 0 or n_frames <= 0:
        return 1
    return max(1, min(int(fps // target_fps), n_frames // min_frames))


def budget_frame_skip(n_frames, budget):
    """Step that keeps about `budget` frames out of `n_frames`, at least 1."""
    if not budget or budget <= 0:
        raise ValueError("frame budget must be a positive number of frames")
    return max(1, round(n_frames / budget))


def decimated_dir(output_dir, fps, step):
    """Where the decimated copies of a session's videos go."""
    return os.path.join(output_dir, f"videos_{fps / step:g}hz")


def decimate_videos(videos, out_dir, step):
    """Write one frame in `step` of each video to out_dir/<name>.avi (Motion-JPEG), at
    fps / step. Existing outputs with the expected frame count are kept, so an interrupted
    run resumes. Returns the output paths, in the input order."""
    import cv2

    os.makedirs(out_dir, exist_ok=True)
    outputs = []
    for src in videos:
        dst = os.path.join(out_dir, os.path.splitext(os.path.basename(src))[0] + ".avi")
        cap = cv2.VideoCapture(src)
        fps, n = cap.get(cv2.CAP_PROP_FPS), int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        expected = (n + step - 1) // step
        if os.path.isfile(dst):
            done = cv2.VideoCapture(dst)
            complete = int(done.get(cv2.CAP_PROP_FRAME_COUNT)) == expected
            done.release()
            if complete:
                cap.release()
                outputs.append(dst)
                continue
        writer, i = None, 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                if writer is None:
                    h, w = frame.shape[:2]
                    writer = cv2.VideoWriter(dst, cv2.VideoWriter_fourcc(*"MJPG"), fps / step, (w, h))
                    writer.set(cv2.VIDEOWRITER_PROP_QUALITY, 95)
                writer.write(frame)
            i += 1
        cap.release()
        if writer is None:
            raise RuntimeError(f"could not read any frame from {src}")
        writer.release()
        outputs.append(dst)
    return outputs
