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
| `--ref_frame <n>` | — | A frame with both heels visible: sets the origin and horizontal axis. Must be inside `[start_frame, end_frame]` |
| `--person_selection motion\|geometric\|largest` | `motion` | `motion`: the walking person, then geometric re-selection (evaluated method). `geometric`: largest detection, then re-selection of the person the other cameras see. `largest`: the largest detection. See [METHOD](docs/METHOD.md#person-selection) |
| `--scale_method stature\|segments\|head` | `stature` | `stature`: head-band height above the floor over the walk against `--height` (MeTRAbs; RTMPose uses `segments`). `segments`: thigh + shank (+ trunk for RTMPose) against `--height`. `head`: head height on `--ref_frame` (former method, about 11 % off) |
| `--vertical_method walk\|frame` | `walk` | `walk`: body axis over the whole walk, walking direction removed. `frame`: head-to-feet on `--ref_frame`. Use `frame`, with a `--ref_frame` where the subject stands straight, when the subject does not walk |
| `--start_frame <n>` / `--end_frame <n>` | whole video | Frame range to process |
| `--frame_skip <n>` | `10` | Frame subsampling for bundle adjustment. Lower is denser and slower; `5` is a good choice with MeTRAbs |
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

## Optional backend: RTMPose + VideoPose3D

The original two-step backend (2D keypoints, then temporal lifting to 3D), kept
for comparison; MeTRAbs is recommended. It needs Python 3.8 and PyTorch, so it
has its own image and environment. Its weights carry non-commercial licences.

With Docker:

```bash
docker compose --profile rtmpose build
docker compose --profile rtmpose run --rm rtmpose demo      # results in output/demo_rtmpose/
```

With conda:

```bash
conda env create -f envs/rtmpose.yaml
conda activate humancalib-rtmpose
pip install --no-deps rtmlib==0.0.15   # --no-deps is required: see envs/rtmpose.yaml
bash scripts/setup_models.sh           # VideoPose3D source and weights, checksummed
```

then run with `--pose_engine rtmpose` as above.

## Platform support

| Platform | Status |
|---|---|
| Linux (Ubuntu 22.04) | Tested |
| Windows via WSL2 | Tested |
| Windows native | Not tested — use WSL2 |
| macOS | Not supported (needs an NVIDIA GPU) |
