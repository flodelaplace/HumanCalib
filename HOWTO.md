# Usage guide

The full reference for the command line. It assumes HumanCalib is installed: see
[Installation](README.md#installation) — Docker is the simplest. How each step
works is explained in [docs/METHOD.md](docs/METHOD.md).

## 1. Prepare your data

1. Put your synchronised videos (`.mp4`, `.avi`, `.mov` or `.mkv`) in one folder,
   one per camera. Cameras must be static; the subject must walk across the
   capture volume.
2. Add a `Calib_scene.toml` with each camera's intrinsics, in
   [Pose2Sim](https://github.com/perfanalytics/pose2sim) format. Video names
   without extension must match its sections; cameras are numbered in
   alphabetical order, so pad numbers (`camera01 … camera10`).
   [`input/README.md`](input/README.md) has the details.

> ⚠ Intrinsic quality is the first driver of accuracy. Distortion coefficients
> k1, k2 above ~5 in absolute value are almost certainly wrong — re-calibrate
> that camera before continuing.

A ready-to-run `demo/` folder is provided: 4 synchronised videos and their
`Calib_scene.toml`.

Optional: a `<video>.dropped.json` sidecar next to a video lists absolute frame
indices to ignore everywhere (corrupted or black frames), as
`{"dropped_frame_indices": [1273, 1274]}`.

## 2. Run the full pipeline

`humancalib run` runs the 7 steps (pose extraction → intrinsics → person
selection and linear initialisation → outlier-frame drop → bundle adjustment →
evaluation → scaling). `scripts/calibrate.sh` takes exactly the same arguments
and works from a checkout without installing the package. `humancalib --help`
lists the steps that can be run on their own.

**With Docker**, give the same arguments after `docker compose run --rm calib`,
with the container's paths: the repository's `input/` is `/input` and `output/`
is `/output`.

```bash
docker compose run --rm calib \
    /input/my_session /input/my_session/Calib_scene.toml /output/my_session \
    --height 1.84 --ref_frame 1415
```

**MeTRAbs** (default, the evaluated method):

```bash
bash scripts/calibrate.sh \
    demo \
    demo/Calib_scene.toml \
    output/demo_metrabs \
    cuda balanced \
    --pose_engine metrabs \
    --height 1.78 \
    --ref_frame 5
```

**RTMPose + VideoPose3D** (optional backend, see [below](#optional-backend-rtmpose--videopose3d)):

```bash
bash scripts/calibrate.sh \
    demo \
    demo/Calib_scene.toml \
    output/demo_rtmpose \
    cuda balanced \
    --pose_engine rtmpose \
    --height 1.78 \
    --ref_frame 5
```

### Positional arguments

| Position | Description |
|---|---|
| 1 | Folder containing the synchronised videos |
| 2 | Path to the intrinsics TOML |
| 3 | Output directory (created if needed) |
| 4 | `cuda` or `cpu` (optional, default `cuda`) |
| 5 | `lightweight` / `balanced` / `performance` (optional, RTMPose only) |

### Options

| Option | Default | Effect |
|---|---|---|
| `--pose_engine metrabs\|rtmpose` | `metrabs` | Pose backend. Each Docker image defaults to the backend it contains |
| `--height <m>` | — | Subject height in metres (e.g. `1.84`). Enables step 7: metric scale and gravity-aligned frame |
| `--ref_frame <n>` | auto | A frame with both heels visible: sets the origin and horizontal axis. Default: the frame on which most cameras see the head and both heels. Must be inside `[start_frame, end_frame]` |
| `--person_selection motion\|geometric\|largest` | `motion` | `motion`: the walking person, then geometric re-selection (evaluated method). `geometric`: largest detection, then re-selection of the person the other cameras see. `largest`: the largest detection. See [METHOD](docs/METHOD.md#person-selection) |
| `--scale_method stature\|segments\|head` | `stature` | `stature`: head-band height above the floor over the walk against `--height` (MeTRAbs; RTMPose uses `segments`). `segments`: thigh + shank (+ trunk for RTMPose) against `--height`. `head`: head height on `--ref_frame` (former method, about 11 % off) |
| `--vertical_method walk\|frame` | `walk` | `walk`: body axis over the whole walk, walking direction removed. `frame`: head-to-feet on `--ref_frame`. Use `frame`, with a `--ref_frame` where the subject stands straight, when the subject does not walk |
| `--start_frame <n>` / `--end_frame <n>` | whole video | Frame range to process |
| `--frame_budget <n>` | `100` | About how many frames the calibration uses; the step between frames is computed from the trial's length. 30 to 60 frames spread over the walk already give the full accuracy |
| `--frame_skip <n>` | — | Fixed step between calibration frames, instead of the budget |
| `--extract_fps <hz>` | off | Extract poses at about this rate (e.g. `25`) on decimated copies of the videos, never below 150 frames. Same calibration, 2 to 8 times faster on video above 50 Hz; keep it off on a treadmill if the vertical matters |
| `--conf_threshold <t>` | `0.5` | Minimum keypoint confidence |
| `--ref_cam <id>` | auto | 1-based camera ID to force as Procrustes reference. Default: the camera with the lowest mean Procrustes residual |
| `--ba_jac analytic\|numeric` | `analytic` | Bundle-adjustment Jacobian; `numeric` is the slower finite-difference path, same result |
| `--no_auto_outlier_drop` | off | Disable the outlier-frame drop between the linear step and BA |
| `--outlier_abs_px <p>` / `--outlier_x_median <m>` | `50` / `5` | A frame is dropped for a camera when its error exceeds both `p` pixels and `m` × that camera's median |
| `--save_video` | off | Save a 2D pose overlay video (RTMPose only) |
| `--verbose` / `--quiet` | — | More detail, or only warnings and errors. Also `HUMANCALIB_LOG_LEVEL` |

### Full real-world example

```bash
bash scripts/calibrate.sh \
    input/my_session \
    input/my_session/Calib_scene.toml \
    output/my_session \
    cuda balanced \
    --pose_engine metrabs \
    --start_frame 650 --end_frame 1500 \
    --ref_frame 1415 \
    --height 1.84 \
    --frame_skip 5
```

Processes frames 650–1500 with MeTRAbs, and scales the scene for a 1.84 m
subject, with the origin under the heels at frame 1415.

**Faster, on high-rate video**: add `--extract_fps 25`. Poses are then extracted on
copies of the videos decimated to about 25 Hz (in `<output_dir>/videos_25hz/`), and
the calibration uses about 100 of them. Checked on 31 trials at 50 to 200 Hz: same
relative rotation error (±0.01°), in about 9 minutes instead of 45 on a 200 Hz BioCV
trial, and half the time at 50–60 Hz. On a treadmill the vertical was less accurate
(2 trials, 1.0° → 2.5°).

## 3. Check the results

The run ends with a table of the MRE (mean reprojection error) at each stage; the
best is starred. Everything is in `<output_dir>/results/`:

| File | Description |
|---|---|
| `Calib_scene_calibrated.toml` | Final calibration (metric, gravity-aligned), for Pose2Sim / OpenCap / OpenSim |
| `3d_skeleton_FINAL.trc` | Triangulated 3D skeleton |
| `camera/visu_3d_FINAL.gif` | 3D animation with the MRE overlaid |
| `camera/visu_3d_linear_1_0*.gif` | The same after the linear step, and after BA before scaling |
| `MRE_visualizations/` | Best and worst reprojection per camera |
| `ba_cost_live_iter*.png` | Bundle adjustment convergence |

## 4. Diagnose and improve

If one camera stays worse than the others (e.g. 9 px while the rest are at 5 px):

- Look at `MRE_visualizations/<calib>/camX_worst.png`: points systematically
  offset mean that camera's intrinsics are wrong.
- In the linear log, a **low Procrustes residual (≤ ~100 mm) with a high MRE**
  also points to the intrinsics: the 3D shape is right, its projection is not.
- Frames dropped as outliers are listed in
  `<output_dir>/noise_1_0/dropped_frames/`.
- Force the reference camera with `--ref_cam 3` if you know camera 3 has the
  cleanest view.

More in [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

## 5. Caching

Pose extraction results are cached in the output folder. Re-runs with the
**same frame range** skip inference (~2 min per camera saved). The cache checks
the frame range, **not** the intrinsics: after changing the TOML, delete the
cached poses.

```bash
rm -rf output/my_session/noise_1_0/2d_joint output/my_session/noise_1_0/3d_joint
```

## 6. Use from Python

`humancalib.calibrate` runs the whole pipeline, with the same defaults and options as
`humancalib run`, and returns the path of the calibrated TOML:

```python
from humancalib import calibrate, CalibrationError

try:
    toml = calibrate(
        "MyProject/videos",                          # one synchronised video per camera
        "MyProject/calibration/Calib_intrinsics.toml",  # Pose2Sim format, intrinsics only
        "MyProject/calibration/humancalib",          # work folder; poses are cached here
        height=1.72,                                 # subject height in metres
        extract_fps=25,                              # any `humancalib run` option, by name
    )
except CalibrationError as err:
    print("calibration failed:", err)
```

The returned file is a complete Pose2Sim calibration (intrinsics copied from the input,
extrinsics estimated), metric, with Z up and the origin under the subject's heels: copy it
into a Pose2Sim project's `calibration/` folder and run the triangulation as usual.

**Installing into a Pose2Sim environment** works: `pip install "humancalib[gpu]"` in a Pose2Sim
0.10.43 environment (Linux, Python 3.10) changed only `protobuf` (7.x → 4.25, required by
TensorFlow 2.15), `setuptools` and `wrapt`; afterwards both ran on the GPU in the same environment
(Pose2Sim's pose estimation with onnxruntime-gpu, then HumanCalib's with TensorFlow), and Pose2Sim
triangulated the demo from HumanCalib's TOML with the skeleton upright.

Progress is logged through the `humancalib` logger; if the calling program has not set up
logging, `calibrate` prints it as the command line would. Pose extraction runs in its own
process, so TensorFlow's GPU memory is released when it ends. To run that step in another
Python environment (e.g. to keep TensorFlow out of the caller's), set
`HUMANCALIB_METRABS_PYTHON` to that environment's interpreter.

## Optional backend: RTMPose + VideoPose3D

The original two-step backend (2D keypoints with RTMPose, then temporal lifting to 3D with
VideoPose3D), kept for comparison and for environments that already have RTMPose, such as
Pose2Sim's; MeTRAbs is recommended (0 failed calibrations out of 77, against 1 for this
backend since 0.5.1, 30 in 0.4). Both steps run on onnxruntime: no PyTorch. Its weights carry non-commercial licences.

```bash
pip install "humancalib[rtmpose]"
# GPU: replace the CPU onnxruntime that rtmlib pulls in. Up to 1.26, onnxruntime-gpu uses
# CUDA 12, like humancalib[gpu]; from 1.27 it needs CUDA 13 (onnxruntime-gpu[cuda,cudnn]).
pip uninstall -y onnxruntime && pip install "onnxruntime-gpu<1.27"
# Without humancalib[gpu] (e.g. on Windows), take the CUDA 12 libraries from pip as well; cuDNN
# 9.27 makes onnxruntime-gpu 1.26 fall back to the CPU, 9.10 works:
# pip install "onnxruntime-gpu[cuda,cudnn]<1.27" "nvidia-cudnn-cu12==9.10.*"
```

then run with `--pose_engine rtmpose`. The VideoPose3D model (68 MB, converted to ONNX from the
official weights by `scripts/export_videopose3d_onnx.py`) is downloaded on the first run;
`HUMANCALIB_VP3D_ONNX` points to a local copy instead.

The conda environment and Docker image of earlier versions (`envs/rtmpose.yaml`, `docker compose
--profile rtmpose`) still work; `scripts/setup_models.sh` converts the model locally there.

## Platform support

| Platform | Status |
|---|---|
| Linux (Ubuntu 22.04) | Tested |
| Windows via WSL2 | Tested |
| Windows native | Tested (GPU: conda for CUDA 11.8, then pip; see the [README](README.md#windows)) |
| macOS | Not supported (needs an NVIDIA GPU) |
