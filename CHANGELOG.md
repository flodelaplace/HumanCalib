# Changelog

## 0.3.0 — 2026-09-29

Easier to install and to call from other software (e.g. Pose2Sim), on Linux, WSL2 and
native Windows, with GPU pose extraction from a plain `pip install`.

**Installation**
- `pip install "humancalib[gpu]"` installs GPU pose extraction: TensorFlow 2.15 with its CUDA
  libraries from pip on Linux / WSL2, TensorFlow 2.10 on Windows (in a conda environment with
  CUDA 11.8 + cuDNN 8.9). Checked on the demo against the validated environment
  (envs/calib.yaml, TensorFlow 2.12): same calibration. The `metrabs` extra now accepts
  TensorFlow 2.10 to 2.15.
- The MeTRAbs model is downloaded by HumanCalib with a progress bar, resumed after an
  interruption and retried, into the TF-Hub cache (an already cached model is reused). TF-Hub
  gave no progress and no resume: on a slow server the first run looked frozen.
- Runs on native Windows: console output no longer fails on a legacy code page, and the tests
  pass there.
- `requires-python` is 3.10 to 3.12 (numpy < 2 and scikit-image < 0.25 have no 3.13 wheels).
- TensorFlow allocates GPU memory on demand instead of reserving all of it, so HumanCalib can
  share the GPU with other software.

**Added**
- Python API: `humancalib.calibrate(video_dir, intrinsics_toml, output_dir, height)` runs the
  pipeline and returns the calibrated TOML (Pose2Sim format); failures raise
  `humancalib.CalibrationError`.
- `--ref_frame` is optional: by default the reference frame (origin and horizontal axis) is the
  one on which most cameras see the head and both heels -- the rule the evaluation used. Only
  `--height` is needed for a metric, gravity-aligned calibration.
- `--extract_fps`: pose extraction on regularly decimated copies of the videos (never below
  150 frames). Checked end to end on 31 trials at 50 to 200 Hz: same relative rotation error
  (±0.01°), 2 to 8 times faster. Off by default; on a treadmill the vertical was less accurate.

**Changed defaults**
- The calibration uses a frame budget (`--frame_budget 100`) instead of a fixed step of 10:
  the step follows from the trial's length. `--frame_skip` still forces a fixed step.
- Linear-initialisation chunks are sized in seconds (120 s, at least 1000 frames) instead of
  1000 frames, so an ordinary walk is initialised as a whole. At 200 Hz the old chunks cut the
  walk in two. Re-evaluated on all 77 trials: BioCV median relative rotation 0.62° → 0.43°
  (worst trial 2.61° → 0.95°), other datasets unchanged within ±0.05°.

## 0.2.0 — 2026-09-22

The defaults now run the method evaluated against five laboratory calibrations
(see [Validation](README.md#validation)).

**Changed defaults**
- `--pose_engine metrabs` (was `rtmpose` outside Docker). Pass `--pose_engine rtmpose` for the
  optional backend.
- `--person_selection motion`: the walking person, then geometric re-selection (was `geometric`).
- `--scale_method stature`: with MeTRAbs, the head-band height above the floor over the walk,
  against 0.9255 × `--height` (was thigh + shank against 0.491 × `--height`). Median scale error
  on four held-out datasets: 1.0 % instead of 1.9 %. RTMPose keeps the segment rule.

**Added**
- Person selection: `geometric` re-selection and `motion` (walking-person) selection.
- Whole-walk vertical (`--vertical_method walk`) and segment-based scale (`--scale_method segments`).
- Evaluation tooling against laboratory calibrations (`humancalib.evaluation`) for BioCV,
  IMOVE-23, OpenCap, LBMC and COMFI.
- Documentation: `docs/METHOD.md`, `docs/TROUBLESHOOTING.md`, a shorter README.

## 0.1.0 — 2026-09-14

First packaged release: `humancalib` command and package, pinned conda environments,
Docker images, CPU test suite with CI, analytic bundle-adjustment Jacobian.
