# How HumanCalib works

This page describes the method step by step, with the design choices and what
was measured to justify them. For the command line, see [HOWTO.md](../HOWTO.md).

## Pipeline

`humancalib run` (or `scripts/calibrate.sh`, which forwards to it) runs seven
steps in order. Each can also be run on its own with `humancalib <step>`.

| Step | `humancalib` step | Module (`humancalib.…`) | What it does |
|---|---|---|---|
| 1. Pose extraction | `extract-metrabs` / `extract-rtmpose` | `pose.metrabs_inference` / `pose.rtmlib_inference` | 2D keypoints in every view, plus metric 3D per camera with MeTRAbs |
| 2. Intrinsics | `cameras` | `pipeline.create_cameras_from_toml` | Reads the camera matrices and distortion from the Pose2Sim TOML |
| 3. Session | `session` | `pipeline.write_session` | Probes the videos, counts cameras and joints |
| 4. 3D lifting | `lift` | `pose.inference` | VideoPose3D 2D→3D, RTMPose only (MeTRAbs already gives 3D) |
| 5. Calibration | `reselect`, `linear`, `outliers`, `ba` | `pipeline.*`, `calibration.*` | Person selection → linear initialisation → outlier-frame drop → bundle adjustment |
| 6. Evaluation | `evaluate` | `postprocessing.evaluate_calibration` | Mean reprojection error (MRE) per camera, diagnostic images |
| 7. Scaling | `scale` | `postprocessing.scale_scene` | Metric scale from the subject's height, gravity-aligned frame |

Output: `Calib_scene_calibrated.toml`, the rotation and translation of every
camera in a metric, gravity-aligned frame, in Pose2Sim format.

## Pose engines

| | MeTRAbs *(default)* | RTMPose + VideoPose3D |
|---|---|---|
| Architecture | one network, image → 2D + metric 3D | two networks, image → 2D → temporal 3D lifting |
| Skeleton | `bml_movi_87` (87 points: 26 joints + virtual surface markers) | Halpe26 2D, OpenPose-25 for calibration |
| 3D scale | metric (mm), per camera | relative |
| Linear initialisation | Procrustes between per-camera 3D skeletons | bone collinearity constraints from 2D |
| Demo: MRE after linear / after BA | 8.1 / **4.0 px** | 178.3 / 8.5 px |

**MeTRAbs** ([Sárándi et al., 2021](https://github.com/isarandi/metrabs), model
`metrabs_l`) is used through TensorFlow Hub, unmodified. Of its 87 points, 26 are
joints; the other ~60 are virtual landmarks computed by the network as linear
combinations of the joints. Bundle adjustment therefore regularises bone lengths
on a 27-bone skeleton built from the 26 joints only (`core/skeletons.py`,
`METRABS_BONE`); treating the virtual points as independent would make the
system rank-deficient. The surface markers are used where they carry
information, e.g. the head band and soles for scaling (below).

**RTMPose + VideoPose3D** is the original two-step path, kept for comparison. It
needs Python 3.8 and PyTorch, hence its own environment and Docker image.

Across five datasets (77 paired trials), RTMPose produced an unusable calibration
in 29 trials, MeTRAbs in none: see [Validation](../README.md#validation).

### MeTRAbs quality filters

Before a detection is kept:

| Filter | Threshold | Effect |
|---|---|---|
| Dark frame | mean brightness < 15 | no detection |
| Small box | < 0.5 % of the image | rejected |
| Collapsed skeleton | 2D spread < 20 px | rejected |
| Joint near the image edge | < 10 px | 2D confidence × 0.1 |

The 3D confidence keeps the box confidence: MeTRAbs predicts a full-body 3D
skeleton even when joints fall outside the image. A Savitzky–Golay filter then
smooths the 2D and 3D trajectories of valid detections.

## Person selection

The subject must be the same person in every camera. Taking the largest
detection fails when a bystander is closer to one camera than the subject is.
Three modes (`--person_selection`):

- **`motion`** *(default, evaluated method)* — the subject is the person
  **walking**. In each camera, every detection is tracked over ±0.2 s and its leg
  swing (ankle relative to hip, in leg lengths per second) is measured. A frame
  is kept only while at least half the cameras see someone walking, and each
  camera keeps its fastest-swinging detection. Then geometric re-selection (next
  item) runs. On six BioCV walks: wrong person in 2–5 % of kept frames, against
  8–20 % for the largest box (`pipeline/motion_selection.py`).
- **`geometric`** — starts from the largest detection. After a first
  calibration, the subject is triangulated from the cameras that agree, and each
  camera re-selects the detection closest to its reprojection; the rig is then
  calibrated again (`pipeline/reselect_person.py`).
- **`largest`** — the largest detection per frame and camera.

## Linear initialisation

`calibration/calib_linear.py`, orchestrated by `pipeline/run_calib_linear.py`.

- **MeTRAbs — Procrustes.** Each camera's metric 3D skeleton is aligned to a
  reference camera's (Umeyama: rotation, translation, scale), which gives every
  camera's pose relative to the reference. The reference is chosen
  automatically: the camera whose alignments to all others have the lowest mean
  residual. `--ref_cam` forces one.
- **RTMPose — collinearity.** Bone orientation constraints from the 2D
  projections, as in Lee et al. (2022).
- **Chunks.** The sequence is cut into chunks of 1000 frames, each calibrated on
  the frames seen by at least two thirds of the cameras; the chunk with the
  lowest MRE is kept.

## Outlier-frame drop

Between the linear step and bundle adjustment
(`pipeline/detect_outlier_frames.py`), a frame is dropped for one camera when
its reprojection error exceeds both 50 px (`--outlier_abs_px`) and 5 × that
camera's median (`--outlier_x_median`). It catches corrupted or half-decoded
frames on which the detector still returns a plausible skeleton. Dropped
frames are recorded in `<output>/noise_1_0/dropped_frames/<video>.dropped.json`
and the linear step runs again. `--no_auto_outlier_drop` disables it.

A sidecar `<video>.dropped.json` placed next to an input video, of the form
`{"dropped_frame_indices": [1273, 1274]}`, flags frames to ignore from the start.

## Bundle adjustment

`calibration/ba.py`, run by `pipeline/run_ba.py`. `scipy.optimize.least_squares`
(Trust Region Reflective) refines all camera poses and 3D points by minimising:

1. the confidence-weighted 2D reprojection error (main term);
2. the variance of bone directions across cameras (λ₁);
3. the variance of bone lengths across frames (λ₂), rebalanced at each iteration
   to about 10 % of the reprojection term, and set to 0 when negligible (usual
   with MeTRAbs).

A term tying the triangulated 3D to each camera's MeTRAbs 3D is implemented but
disabled: MeTRAbs' per-camera depth is too noisy frame to frame and pulls
against the reprojection term.

Two passes: after the first, frames whose error exceeds twice the median are
removed. If memory runs out, the runner retries with fewer frames
(`frame_skip + 5`, up to 60).

**Analytic Jacobian** (`calibration/ba_jacobian.py`, default `--ba_jac analytic`).
The reprojection and bone-length terms have exact derivatives; the small
direction-variance term is finite-differenced over the rotations only. Same
result as finite differences (demo: 4.058 vs 4.057 px) with about 22 instead of
2940 objective evaluations. `--ba_jac numeric` restores finite differences.

More frames or more BA iterations were tested and do not improve accuracy.

## Metric scale and orientation

`postprocessing/scale_scene.py`. A calibration from images alone is defined up
to scale and orientation. Both are recovered from the subject, over the whole
walk rather than on one frame.

**Vertical** (`--vertical_method walk`, default). The median body axis
(head → mid-ankles) over the walk, with its component along the walking
direction removed; the walking direction comes from the stance-phase foot
keypoints. Removing it cancels the forward trunk lean. Median error against lab
calibrations: about 0.7°, against about 3° from a single frame.

**Scale** (`--scale_method stature`, default). With MeTRAbs, the body is measured
top to bottom: the height of the head-band markers (mid-point of the four virtual
head markers) above the floor (lowest sole marker: heels, toes, metatarsals),
95th centile over the walk, is set to **0.9255 × `--height`**. That ratio covers
the head band → vertex distance and the head's dip during gait; it was fixed
once on the BioCV development set and applied unchanged to the four other
datasets, where the median absolute scale error is **1.0 %**.

The previous rule (`--scale_method segments`: thigh + shank = 0.491 ×
`--height`, Drillis & Contini) lets each person's leg proportions into the scale
— real leg-to-stature ratios range from 0.44 to 0.47 — and gives 1.9 % on the
same datasets. RTMPose's skeleton has no head-band markers and its head point
gave no gain, so RTMPose keeps segments: thigh + shank + trunk = 0.779 ×
`--height` (its hip keypoints sit ~85 mm in front of the joint centre, which
lengthens the thigh and shortens the trunk by opposite amounts).

**Origin and horizontal axis** come from `--ref_frame`: centre of the heels at
floor level, heel-to-heel direction made orthogonal to the vertical.

Both default methods assume the subject walks. For a trial without walking, use
`--vertical_method frame` and a `--ref_frame` on which the subject stands
straight.

## Caching

Re-running on the same output folder and frame range reuses the extracted poses.
The cache checks the frame range, not the intrinsics or model versions: after
changing the TOML, delete `<output>/noise_1_0/2d_joint` and `3d_joint`.
