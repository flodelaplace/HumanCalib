# HumanCalib evaluation protocol

This protocol fixes, **before** looking at the
results, what is measured, how, and with which parameters, so that no setting is
tuned after the fact on the validation data.

Code: `src/humancalib/evaluation/` (reference calibration readers, metrics,
per-dataset drivers), tests: `tests/test_eval_*.py`. Results: one folder per
dataset and trial in the datasets' local copy (outside the repository).

---

## 1. Questions

| # | Question | Level |
|---|---|---|
| Q1 | How geometrically accurate are the estimated extrinsics, compared with a laboratory calibration? | Geometry |
| Q2 | What is the effect of this calibration on the joint kinematics and spatio-temporal parameters obtained with Pose2Sim? | Downstream |
| Q3 | What is the reliability: dispersion across several recordings of the same setup? | Reliability |
| Q4 | What do the two engines bring (MeTRAbs + Procrustes vs RTMPose + VideoPose3D), and what is the result sensitive to (reference image for the scale, type of movement)? | Sensitivity |

The literature on calibration from humans (Takahashi 2018, Lee 2022,
CasCalib, Xu 2021, Pätzold 2022, HSfM, Kineo, Yang 2026) stops at camera pose
errors or MPJPE, on vision datasets (Human3.6M, Panoptic, EgoHumans) or
synthetic ones. None evaluates biomechanical kinematics or compares against a
biomechanics laboratory calibration; none separates shape error from scale
error, or measures the vertical. The only precedent on the effect of a
calibration error on joint angles is Pose2Sim Part 1 (Pagnon et al. 2021:
~1 cm perturbation → < 0.5°), in simulation.

## 2. Data

| Dataset | Cameras | Video | Reference calibration | Reference calibration quality | Kinematic reference |
|---|---|---|---|---|---|
| **BioCV** | 9 | 1920×1080, 200 fps, hardware sync | Circle-grid target + BA, aligned to mocap, per participant | Good | reference `.mot` (`_RESULTS/_GOLD_BIOCV`), c3d |
| **LBMC** | 9 Miqus | 1088×1920 (portrait), 60 fps | QTM wand (σ 0.19 mm), Pose2Sim TOML | Very good | c3d (IK to be done) |
| **IMOVE-23** | 10 Miqus | 1920×1080, 100 fps, walking ~130 s | QTM XML, 13 sessions | Good | `ik.mot` |
| **OpenCap** | 5 iPhone | 720×1280 (portrait), 60 fps | Checkerboard on the wall, generic intrinsics | Poor | mocap `.mot` |

Excluded: **Toulouse** (no calibration or intrinsics), **Fukuchi** (no video).

Conversion pitfalls identified (each reader has a test):

* **BioCV**: the 3×3 block of the world→camera matrix equals s·R (s ≈ 0.998). The
  camera is read as `[R | t/s]`, which projects identically. We use
  `calibrationUpdate/` (refined mocap alignment).
* **LBMC**: distortions probably divided by 64 during conversion
  from QTM — to be settled by reprojecting the markers before use.
* **IMOVE-23, OpenCap**: k3 ≠ 0 (large on IMOVE 22/23), not representable in
  a 4-coefficient Pose2Sim TOML: the writer refuses rather than truncating.
* **Orientation**: portrait videos (LBMC, OpenCap) and rotated views (IMOVE) —
  the image size must match the intrinsics.

**Validation of each reader** before any result: reprojection of known 3D
points with the calibration as read, compared with the projections provided by
the dataset. BioCV P03, camera 08, ±1 m axis points from `markers2D`: deviation
0.35–1.9 px (a convention error would give hundreds of pixels).

## 3. Isolation principle

* **HumanCalib input**: the videos and the **reference intrinsics**. Only the
  extrinsics are estimated, which is the contribution being evaluated.
* **Common convention** (`evaluation/rig.py`): `x_cam = R·X + t`, world→camera,
  metres, centre `C = −Rᵀt`. Every calibration is converted on reading.
* **Downstream**: same video, same 2D detections, same frames, same Pose2Sim
  configuration; only the calibration file changes. Any difference is
  attributable to the calibration.

## 3b. Names of the evaluated configurations (for the paper)

The names "v1" to "v4" are development stages; the paper only compares the
configurations below. Each one is a set of `humancalib run` options.

| Name | Pose engine | Options | For whom |
|---|---|---|---|
| **HumanCalib-M** (reference) | MeTRAbs | `--person_selection motion --scale_method segments --vertical_method walk` | The best accuracy / time trade-off (~12 min for 9 cameras and 1250 frames) |
| **HumanCalib-R (full)** | RTMPose + VideoPose3D | same, at the native video frame rate | Without TensorFlow; the most accurate on this path, but the slowest |
| **HumanCalib-R (fast)** | RTMPose + VideoPose3D | same, video brought down to ~50 Hz | Fast option, lower accuracy |
| *Ablations* | — | `--person_selection largest`, `--scale_method head`, `--vertical_method frame` | Show what each component brings |

The three main configurations share the same person selection, the same
distortion correction, the same scale and the same vertical: only the pose
engine and the frame rate change.

## 4. Running HumanCalib (frozen parameters)

* Pipeline defaults: `frame_skip 10`, `conf_threshold 0.5`,
  automatic outlier-frame detection, automatic reference camera,
  analytical Jacobian. No per-trial tuning.
* Two engines: `metrabs` and `rtmpose` (RTMPose + VideoPose3D).
* Scale: stature provided by the dataset. Reference image: automatic rule
  using only HumanCalib's detections (never the reference calibration) —
  the frame where the most cameras see the head and heels with confidence,
  ties broken by mean confidence. Its sensitivity is measured (§8).
* **A failure counts**: the success rate is a result. A trial that
  fails is not rerun with other parameters; if it is rerun for a
  technical reason (crash, disk), this is recorded.

## 5. Level 1 — geometry

Notation: `d(R) = arccos((tr R − 1)/2)`; Rᵢ world→camera; Cᵢ centre.
Vertical: HumanCalib `−y` (OpenCV frame, y pointing down); BioCV, LBMC `+z`.

**Primary — similarity-invariant, no alignment.** For each pair (i, j):

* relative rotation error: `d( (R̂ᵢR̂ⱼᵀ)(RᵢRⱼᵀ)ᵀ )`;
* relative translation direction error, in the frame of camera i:
  `∠( R̂ᵢ(Ĉⱼ−Ĉᵢ), Rᵢ(Cⱼ−Cᵢ) )`.

Reported as median and maximum, AUC at 1/2/5/10° of max(rotation, direction),
and median per camera. The C(C−1)/2 pairs are not independent (6C−7
degrees of freedom): **no statistical test on the pairs**.

**Secondary — what HumanCalib estimates from the person.**

* Scale: median of the baseline ratios `‖Ĉⱼ−Ĉᵢ‖ / ‖Cⱼ−Cᵢ‖` (and Umeyama
  factor). Deviation from 1 in %.
* Vertical: angle between the estimated vertical and the reference vertical,
  compared through the gauge rotation estimated **from the orientations only**
  (chordal mean of RᵢᵀR̂ᵢ).
* Shape: deviation of the baseline ratios from their median (%); position
  and orientation errors after a 7-DoF similarity (Umeyama), leave-one-out.
* **End-to-end absolute error**: position (mm) and orientation (°) per
  camera after a **4-DoF** alignment (yaw about the vertical + translation,
  scale fixed to 1), leave-one-out. Scale and vertical errors deliberately
  remain in it.

Why not a 7-DoF similarity as the primary measure: it absorbs the
scale, which is precisely estimated by the method; and, on 4 to 10 centres,
it spreads one camera's error over the others (hence the leave-one-out).
Why not the baseline in mm as an invariant: it is not invariant under
similarity; it mixes shape and scale.

**Supplementary.** MRE in pixels (convergence criterion of the BA, not a
measure of accuracy — Lee 2025 and Pätzold 2022 show inverted rankings).

## 6. Level 1b — 3D error induced by the calibration

* Mocap markers (reference calibration's world frame) projected with the reference calibration →
  noise-free 2D → triangulated with the estimated calibration → 3D error in mm
  (mean, 95th percentile), after 4-DoF then 7-DoF alignment; error on
  inter-marker distances (invariant under rigid motion).
* Known length: BioCV `calib_00/*.grids` (circle-grid target, 78.5 mm pitch),
  LBMC checkerboard (60 mm), triangulated with the estimated calibration.

## 7. Level 2 — downstream (Pose2Sim)

Two identical Pose2Sim runs (2D detection, association, triangulation,
filtering, augmentation, scaling and OpenSim IK): reference calibration vs
HumanCalib calibration.

* **Primary measure**: paired difference HumanCalib − reference, per degree of
  freedom; bias and RMSE; sagittal plane separated from the frontal and
  transverse planes.
* Context: each one against the reference `.mot` (raw MAE and cMAE, since the
  Pose2Sim model is not the one used for the reference).
* Spatio-temporal (walking): step length and width, speed — sensitive to
  scale, unlike angles.
* Standard deviation of triangulated segment lengths (before IK): secondary
  indicator only.

Independent errors add in variance, with a covariance that is non-zero
a priori: we do not subtract "HumanCalib error − reference error"; we
report the direct paired difference.

## 8. Level 3 — reliability and sensitivity

* **Reliability**: several recordings of the same, unmoved setup.
  BioCV: one calibration per participant for all their trials; IMOVE: subjects
  sharing a calibration ({4,5,6}, {7,9,10}, {11,12,13}, {15,16,17}). Bias
  = mean against the reference calibration; precision = dispersion across calibrations.
  Rerunning the same sequence only measures the GPU non-determinism of the pose
  (MRE 4.03–4.06 px observed): done once, to quantify it.
* **Engines**: MeTRAbs vs RTMPose + VideoPose3D on the same trials. A
  result unfavourable to RTMPose + VideoPose3D is a result (it motivates the
  recommendation of MeTRAbs), provided that this path was run within its
  domain of use: VideoPose3D is a temporal model trained at 50 Hz, so
  a 100–200 Hz video is given to it brought down to ~50 Hz. This input
  condition is fixed here, before results, and applied to all trials; it
  is not a per-trial setting.
* **Reference image**: scale and vertical recomputed on several valid
  frames of the same trial.
* **Type of movement**: walking, running, countermovement jump (CMJ), treadmill (LBMC).
* Optional if time allows: camera subsets, duration.
* **Method v2 — geometric person selection** (`--person_selection
  geometric`), designed after seeing the failures of P06 and P10 (experimenter
  in the foreground of camera 08). Rule fixed before any v2 run: after a
  first calibration, robust triangulation of the subject by camera consensus
  (most consistent subset of 3 cameras, then cameras within
  max(50 px, 5 × its error)), re-selection in each camera of the detection
  closest to the reprojection, full recalibration. Thresholds = those of
  the outlier-frame detection, no per-trial tuning. The v1 results,
  failures included, remain the results of method v1. Because the rule
  was motivated by P06/P10, it is also validated on participants never
  examined (P04, P17, P18), in v1 and in v2.

## 9. Statistics

* **Unit: the subject** (nested trials). Never pooled frames
  (autocorrelation; artificially tight limits of agreement).
* Description: median, interquartile range, bootstrap confidence intervals
  by subject.
* Bland-Altman with repeated measures (Bland & Altman 2007) on the kinematic
  outputs.
* Equivalence: bound fixed a priori and justified (measurement error of the
  marker-based system, minimal detectable change, order of magnitude from Pose2Sim
  Part 1), not the thresholds of McGinley et al. 2009, which concern
  between-session reliability and not validity. With few subjects, confidence
  intervals rather than tests.

## 10. Experimental plan

To be confirmed after the first trial (measured computation time):

| Dataset | Subjects | Trials | Engines | Calibrations |
|---|---|---|---|---|
| BioCV | 6 (without errata) | 3 WALK + 2 RUN + 1 CMJ | 2 | 72 |
| IMOVE-23 | 6, including two groups with a shared calibration | walking (walk-past windows) | 2 | ~24 |
| LBMC | 2 | gait, sit-stand, mmh | 2 | 12 |
| OpenCap | 5 | walking | 2 | 10 |

BioCV P08 (frame drops) and P04 (WALK_05 missing) are avoided as first choices.

## 11. Results directory layout

```
<datasets' local copy>\<Dataset>\<Participant>_<Trial>\
  input\Calib_scene.toml     reference intrinsics (HumanCalib input)
  gold\Calib_gold.toml       full reference calibration (Pose2Sim)
  gold\meta.json             provenance, stature
  metrabs\  rtmpose\         HumanCalib outputs per engine
  eval\                      metrics (JSON/CSV)
```

## 12. Verified references

* Lee et al., Extrinsic Camera Calibration From a Moving Person, RA-L 2022, 10.1109/LRA.2022.3192629
* Takahashi et al., Human Pose as Calibration Pattern, CVPRW 2018
* Pätzold, Bultmann, Behnke, GCPR 2022, arXiv 2209.07393
* Lee, Nishino, Nobuhara 2025, arXiv 2502.12546
* Yang et al. 2026, arXiv 2604.17567; Kineo, arXiv 2510.24464; HSfM, CVPR 2025, arXiv 2412.17806; CasCalib, arXiv 2405.06845; Xu et al., CVPR 2021, arXiv 2104.08568
* Pagnon et al., Pose2Sim Part 1, Sensors 2021, 10.3390/s21196530; Part 2, Sensors 2022, 10.3390/s22072712
* Uhlrich et al., OpenCap, PLoS Comput Biol 2023, 10.1371/journal.pcbi.1011462
* Kanko et al., J Biomech 2021, 10.1016/j.jbiomech.2021.110665 and 10.1016/j.jbiomech.2021.110414
* Needham et al., J Biomech 2022, 10.1016/j.jbiomech.2022.111338
* McGinley et al., Gait Posture 2009, 10.1016/j.gaitpost.2008.09.003
* Bland & Altman, J Biopharm Stat 2007, 10.1080/10543400701329422
* Zhang & Scaramuzza, trajectory evaluation, IROS 2018; Umeyama, TPAMI 1991, 10.1109/34.88573
* Challis & Kerwin, J Biomech 1992, 10.1016/0021-9290(92)90040-8
