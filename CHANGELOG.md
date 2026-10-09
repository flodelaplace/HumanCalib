# Changelog

## 0.5.2 — 2026-10-09

**Added**
- `paper/results/`: the per-trial results of the article (9 CSV files and a README; derived metrics
  only, CC BY 4.0), so that each archived release carries them under the same DOI.

**Fixed**
- 0.5.1's entry counted 2 failed RTMPose calibrations: the second one, BioCV P18_WALK_02 (bystanders
  in two cameras), had not finished; its bundle adjustment converged after about 3 h (0.54°).
  Failures drop from 7 to 1 (COMFI 4665_StraightWalking). No code change.

## 0.5.1 — 2026-10-09

RTMPose backend: the cameras are now initialised like MeTRAbs', camera by camera. Failed
calibrations on the 77 evaluation trials drop from 7 to 1 (30 in 0.4); the calibrations that
succeeded with both initialisations are unchanged (median 1.37°, at most 0.13° apart).

**Changed**
- Linear initialisation, RTMPose backend (`calib_linear.place_in_camera`): each lifted,
  root-relative VideoPose3D pose is placed in its camera's space -- per frame, the pelvis
  position that makes it reproject onto its own 2D keypoints, a linear least squares -- and
  every camera is then aligned to a reference camera by Procrustes, the MeTRAbs path. A camera
  only needs frames in common with the reference, where the orientation-based solve wanted
  every bone seen by every camera at once, which 10-camera rigs rarely give.
  `HUMANCALIB_RTMPOSE_INIT=linear` restores the previous initialisation.

**Fixed**
- RTMPose's derived joints (neck, mid-hip) can be NaN with a confident score; the linear stage
  now skips them when triangulating and when computing its reprojection error (MeTRAbs
  unchanged).

## 0.5.0 — 2026-10-09

The RTMPose backend finds the walking person much more reliably: failed calibrations on the 77
evaluation trials drop from 30 to 7, with the same accuracy where both versions succeed (1.78°
median relative rotation before, 1.64° now). MeTRAbs is unchanged.

**Changed**
- Person selection, RTMPose backend: the leg swing that tells the walker from everyone else is
  now measured in 3D, as for MeTRAbs. Each person's track is lifted by VideoPose3D (the
  backend's own lifter) before selection (`motion_selection.tracks`, `lifted_leg_speeds`). The
  3D swing decides *who* walks -- in the image, a passer-by crossing the view out-swings a
  subject walking straight at the camera; a frame counts as walking when either the 2D or the
  3D swing says so, so a camera keeps at least the frames it had. Against the gold-oracle
  selection on 59 trials, wrong person 9.3 % -> 4.0 % of kept frames, and no camera is left
  empty any more (10 COMFI straight walks had one, which is why they gave no calibration).
  Same thresholds as before: nothing was tuned. Falls back to the 2D swing, with a warning,
  when onnxruntime or the VideoPose3D model is unavailable.

**Added**
- `humancalib run --no_visualize`: skips the evaluation images and 3D animations (the
  reprojection errors are still computed); rendering dominated batch runs on slow disks.
- `reselect_person --device`: where VideoPose3D lifts the tracks for the selection.

## 0.4.0 — 2026-10-05

Ready for Pose2Sim's `extrinsics_method = 'keypoints'`: installs in recent Pose2Sim environments
(numpy 2, Python 3.11 to 3.13), an RTMPose backend without PyTorch, and a tested setup on native
Windows. Checked end to end in Pose2Sim, on Linux and on native Windows: calibration, pose
estimation, triangulation, filtering, marker augmentation and OpenSim inverse kinematics.

**Added**
- `results/summary.json`: the kept stage and its reprojection error, per camera by name, for
  programs that call the pipeline (Pose2Sim reports it in its calibration recap).

**Fixed**
- Pose extraction always runs in the current environment (or the one named by
  `HUMANCALIB_METRABS_PYTHON`). It used to switch silently to a conda environment named
  `metrabs_opensim` whenever one existed, the layout of the development machine: called from
  another environment, such as Pose2Sim's, extraction then ran in the wrong one.

**Changed**
- numpy 2 is supported (no upper bound on numpy or scikit-image), and Python 3.13. The `gpu`
  extra installs TensorFlow 2.20 on Linux: the first without a numpy upper bound -- recent
  Pose2Sim, through `opensim`, needs numpy >= 2.1 -- and on cuDNN 9, like onnxruntime-gpu.
  Same accuracy as the validated environment within the method's own variation (4 trials,
  never worse). Windows keeps TensorFlow 2.10 (numpy < 2, Python 3.10).

**RTMPose backend without PyTorch**
- VideoPose3D, the 2D -> 3D lifting of the RTMPose backend, runs on onnxruntime
  (`pose/lifting.py`), converted to ONNX from the official weights by
  `scripts/export_videopose3d_onnx.py`: same 3D poses as the PyTorch original to 2e-4, same
  calibrations (BioCV P03 0.477 deg -> 0.477 deg, COMFI 1012 1.946 -> 1.944 deg). The backend now
  needs only rtmlib and onnxruntime -- `pip install "humancalib[rtmpose]"`, Python 3.10 to 3.13 --
  instead of PyTorch, a VideoPose3D checkout and Python 3.8.
- onnxruntime-gpu finds the CUDA libraries of the nvidia-* pip wheels (`preload_dlls`); a CPU
  fallback now says why (CPU build, or onnxruntime-gpu >= 1.27 needing CUDA 13).

**Windows**
- `HUMANCALIB_METRABS_PYTHON` accepts Windows paths and quoted commands (e.g.
  `"C:\...\conda.bat" run --no-capture-output -p D:\envs\metrabs python -u`): POSIX splitting
  used to drop the backslashes. This is how a Python 3.11 environment (recent Pose2Sim) runs MeTRAbs
  from the Python 3.10 environment that TensorFlow's Windows GPU build needs.
- A step run by another interpreter (`HUMANCALIB_METRABS_PYTHON`) no longer inherits this
  environment's package path, which made a Python 3.10 environment import the packages built for
  the calling one (numpy 2 from a Python 3.11 Pose2Sim environment). On Windows, pointing it to a
  conda environment's `python.exe` is enough: its DLL folders are put on PATH, as activation would.
- MeTRAbs inference out of GPU memory (smaller GPUs, TensorFlow 2.10 on Windows, another program
  using the GPU) redoes the camera with half the batch, down to one frame, instead of failing.

**Checked**
- `pip install "humancalib[gpu]"` inside a Pose2Sim 0.10.43 environment: both tools run on the
  GPU in the same environment, and Pose2Sim triangulates from HumanCalib's TOML (HOWTO, §6).

## 0.3.1 — 2026-09-30

**Fixed**
- The exported calibration (`Calib_scene_calibrated.toml`) is now in Pose2Sim's convention,
  Z up. It had Y pointing down, the internal convention: Pose2Sim, which assumes Z up and turns
  the points into Y-up for OpenSim, then produced a skeleton lying on its side. Checked by
  triangulating the demo with Pose2Sim from the exported file: the skeleton stands, feet at
  floor level. The exported `3d_skeleton_FINAL.trc` is now Y up, as OpenSim expects, with the
  same axes as the .trc Pose2Sim writes. The JSON calibrations, and every evaluation, keep the
  internal frame and are unchanged.

**Packaging**
- Ready for PyPI: metadata (classifiers, keywords, links), README with absolute links, and a
  GitHub Actions workflow that builds, checks and uploads a release with Trusted Publishing
  (docs/RELEASING.md).
- CI installs the package with plain pip and runs the tests on Linux and Windows, Python 3.10
  to 3.12.
- HOWTO: using HumanCalib from Python, and in a Pose2Sim project.

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
