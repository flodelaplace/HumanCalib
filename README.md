# HumanCalib

**Extrinsic calibration of a multi-camera rig from a person walking through it.**
No checkerboard, no wand: HumanCalib estimates the pose of every camera from the
human pose seen by all of them, then gives the rig a metric scale and a vertical
axis from the subject's height. The output is a
[Pose2Sim](https://github.com/perfanalytics/pose2sim)-format calibration, ready
for markerless motion capture.

![HumanCalib pipeline](https://raw.githubusercontent.com/flodelaplace/HumanCalib/main/img/pipeline.png)

## How it works

1. **Inputs**: synchronised videos from N fixed cameras, their known intrinsics and the
   participant's stature. No calibration target.
2. **Pose estimation** in every view, with one of two engines: **HumanCalib-M**
   ([MeTRAbs](https://github.com/isarandi/metrabs), 2D and metric 3D from one network, the
   default) or **HumanCalib-R** (RTMPose 2D lifted to 3D by VideoPose3D).
3. **Person selection**: the person walking is kept in every camera (leg swing about the hip,
   agreement between cameras, geometric check); bystanders are discarded.
4. **Extrinsic calibration**: camera poses initialised by superposing the per-camera 3D
   skeletons (Procrustes), badly reprojected frames dropped, then bundle adjustment of all
   cameras and 3D joints on the 2D keypoints.
5. **Metric world frame** from the body itself: the vertical is the median head-to-feet axis
   over the walk, the scale comes from the stature.
6. **Check and export**: a calibration is accepted when its worst camera reprojects within
   15 mrad, with no reference needed, and is written in the Pose2Sim format (gravity-aligned,
   metric).

Details, design choices and what was measured to justify them:
[docs/METHOD.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/METHOD.md).

![3D result](https://raw.githubusercontent.com/flodelaplace/HumanCalib/main/img/visu_3d_FINAL.gif)

## Validation

Five public datasets, 97 trials, default settings. The three reported here each
provide a laboratory-grade reference calibration and enough trials to summarise.

**Camera geometry.** Relative rotation between camera pairs, against the
dataset's own calibration, and reprojection error of our own reconstruction,
which needs no reference. Median over trials [min–max]:

| Dataset | Cameras | Trials | Relative rotation error | Reprojection error (MRE) |
|---|---|---|---|---|
| I-MOVE-23 | 10 | 23 | 0.51° [0.29–1.06] | 3.34 px [2.93–5.47] |
| BioCV | 9 | 26 | 0.47° [0.25–0.95] | 2.75 px [2.35–4.07] |
| OpenCap | 5 | 18 | 1.89° [0.56–2.31] | 1.69 px [1.38–2.16] |

<p align="center">
  <img src="https://raw.githubusercontent.com/flodelaplace/HumanCalib/main/img/rigs.png" width="720"
       alt="Camera rigs estimated by HumanCalib-M (red) over the reference calibrations (green)">
  <br><em>HumanCalib-M cameras (red) over each dataset's reference calibration (green), for the trial
  closest to the dataset median among the first 77 trials; the angle is that trial's median relative
  rotation error.</em>
</p>

Pixels are not comparable between rigs of different focal lengths; in angular
terms the same errors are 2.5, 2.1 and 1.8 mrad. A low reprojection error means
the calibration is not broken, not that it is accurate: on OpenCap, five
smartphones on a tight arc and a walk of about two seconds cap the accuracy
while leaving the residual low.

**What it changes for the biomechanist.** The same
[Pose2Sim](https://github.com/perfanalytics/pose2sim) chain was run twice per
trial on the same 2D detections, with the laboratory calibration and with
HumanCalib's, changing nothing else, each run in its own frame. The table compares
the joint angles the two runs produce. Equivalence is declared when the upper bound of the 95 %
confidence interval (participant level, Bonferroni-corrected) stays below the margin,
for each of the 9 degrees of freedom (pelvis, hip, knee, ankle, subtalar):

| Dataset | Trials | RMSD between the two chains, median [min–max] | Worst degree of freedom | Equivalent within 2° |
|---|---|---|---|---|
| BioCV | 26 | 0.34° [0.18–2.50] | 0.83° | 9 / 9 |
| OpenCap | 18 | 0.48° [0.31–0.93] | 0.85° | 9 / 9 |
| I-MOVE-23 | 23 | 0.82° [0.46–1.89] | 1.43° | 8 / 9 |

Changing the calibration therefore moves the reported angles by about half a
degree to one degree, below the 2° margin usually accepted in clinical gait
analysis, and roughly ten times less than the 4–12° that separates such a chain
from optical motion capture on the same trials. Against motion capture, the two
calibrations are tied (median RMSD within 0.02° on each dataset).

- No failed calibration out of 97.
- Metric scale within 1.1 % (median, on the four datasets not used to set it).

**With RTMPose + VideoPose3D** instead of MeTRAbs (the backend Pose2Sim already installs),
1 calibration out of 97 fails (30 out of 77 before 0.5: the walking person is now told apart in 3D and the
cameras initialised camera by camera, see [METHOD.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/METHOD.md)). On the 96 trials both
engines calibrate, median relative rotation error:

| | I-MOVE-23 | BioCV | OpenCap | All five datasets |
|---|---|---|---|---|
| MeTRAbs | 0.51° | 0.47° | 1.89° | 0.84° |
| RTMPose + VideoPose3D | 0.34° | 0.49° | 1.95° | 0.66° |

No difference is detectable in rotation (paired Wilcoxon, p = 0.77); MeTRAbs remains more
reliable (no failure) and more accurate in scale (1.1 % against 1.7 %). The joint angles
are unchanged by the choice of engine: with RTMPose calibrations, all 9 degrees of
freedom are equivalent within 2° on each of the three datasets.

The two remaining datasets are reported in the paper: LBMC, whose two treadmill
trials are too few to summarise, and COMFI, where HumanCalib proved closer to
the laboratory's own motion capture than that dataset's own calibration, which
makes any comparison against that reference a measure of the reference rather
than of HumanCalib.

**Out of sample.** 20 of the 97 trials come from participants never opened during development
(I-MOVE-23 subjects 14-25, BioCV P19, P24, P26 and P27): no failed calibration with either engine, median
relative rotation error 0.52° (MeTRAbs) and 0.44° (RTMPose + VideoPose3D), and 39 of the 40
calibrations accepted by the reference-free criterion.

**Sensitivity.** Calibrations redone from the same detections still succeed with 2 cameras, the
median relative rotation error growing from about 0.4° with all cameras to about 0.9° with 2. One
camera out of sync by up to 20 ms changes nothing; by 80 ms, the error grows from 0.44° to 0.52°.
The intrinsics must be right: a focal length 5 % off passes almost unchanged into the scale, and a
principal point 30 px off brings the error to about 2°. Each centimetre of error in the stature
given moves the scale by about 0.6 %.

A paper is in preparation; its per-trial results are in
[paper/results/](https://github.com/flodelaplace/HumanCalib/tree/main/paper/results) (CC BY 4.0).
The evaluation protocol is in
[docs/EVALUATION_PROTOCOL.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/EVALUATION_PROTOCOL.md).

## Installation

An NVIDIA GPU is needed for pose estimation (driver ≥ 525). Linux, WSL2 and
Windows are supported.

### pip — Linux or WSL2

Python 3.10 to 3.13. The CUDA libraries come from pip, nothing else to install.

```bash
python -m venv .venv && source .venv/bin/activate
pip install "humancalib[gpu]"
```

### Windows

Python 3.10, in a conda environment that provides CUDA: TensorFlow 2.10 is the
last version with GPU support on native Windows. CUDA 11.8 also covers recent
GPUs (RTX 40xx), which CUDA 11.2 does not.

```bat
conda create -n humancalib -c conda-forge python=3.10 cudatoolkit=11.8 cudnn=8.9
conda activate humancalib
pip install "humancalib[gpu]"
```

### Check the install

The demo videos are in the repository: download and unzip the
[source archive](https://github.com/flodelaplace/HumanCalib/archive/refs/tags/v0.5.4.zip)
(or `git clone` the repository), then

```bash
humancalib run HumanCalib-0.5.4/demo HumanCalib-0.5.4/demo/Calib_scene.toml output/demo --height 1.78
```

It worked if the log shows `Compute device: GPU` and ends with an MRE summary
table, and `output/demo/results/Calib_scene_calibrated.toml` exists. The first
run downloads the MeTRAbs model (~700 MB, with a progress bar, resumed if
interrupted) into `~/.cache/tfhub_modules`; set `TFHUB_CACHE_DIR` to put it
elsewhere.

### From Python (e.g. inside Pose2Sim)

```python
from humancalib import calibrate

toml = calibrate("session/videos", "session/Calib_intrinsics.toml", "session/humancalib",
                 height=1.78)
```

`calibrate` runs the same pipeline as `humancalib run`, with the same defaults,
and returns the path of the calibrated TOML in Pose2Sim format. Any command-line
option can be passed by name (`extract_fps=25`, `ref_frame=120`...); a failure
raises `humancalib.CalibrationError`.

### Docker

The exact environment the published results were obtained with. Requires Docker
with Compose v2 and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

```bash
git clone https://github.com/flodelaplace/HumanCalib.git
cd HumanCalib
printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env   # results owned by you, not root
docker compose build                                                 # ~2 GB download, resumable
docker compose run --rm calib demo
```

The model is kept in a Docker volume after the first run.

### conda, exact environment

Every version pinned, as validated (TensorFlow 2.12, CUDA 11.8 from conda):

```bash
git clone https://github.com/flodelaplace/HumanCalib.git
cd HumanCalib
conda env create -f envs/calib.yaml
conda activate humancalib
pip install --no-deps -e .                 # adds the `humancalib` command, keeps the pins
```

The pip installs above use TensorFlow 2.20 with numpy 2 (Linux) and TensorFlow
2.10 (Windows). Windows gives the same calibration as this environment (0.02°
median difference on the demo); TensorFlow 2.20 the same accuracy within the
method's own variation, never worse on the four trials checked (e.g. BioCV 0.42°
→ 0.37°, COMFI 2.06° → 2.06°).

Without a GPU, `pip install humancalib`
installs calibration, bundle adjustment, evaluation and scaling from existing
pose files. The optional RTMPose + VideoPose3D backend, on onnxruntime with no PyTorch:
`pip install "humancalib[rtmpose]"`, see [HOWTO.md](https://github.com/flodelaplace/HumanCalib/blob/main/HOWTO.md#optional-backend-rtmpose--videopose3d).

## Calibrating your own rig

**1. Record.** Synchronised videos from static cameras, while one person walks
across the capture volume for a few passes.

**2. Prepare a session folder** with one video per camera and a
`Calib_scene.toml` holding each camera's intrinsics in Pose2Sim format:

```toml
[camera01]
name = "camera01"
size = [1920.0, 1080.0]
matrix = [[1057.46, 0.0, 942.23], [0.0, 1056.83, 535.6], [0.0, 0.0, 1.0]]
distortions = [-0.041, 0.0086, -0.0002, 0.0002]
fisheye = false
```

Video names (without extension) must match the TOML sections. Good intrinsics
matter more than anything else: see [input/README.md](https://github.com/flodelaplace/HumanCalib/blob/main/input/README.md).

**3. Run.**

```bash
humancalib run input/my_session input/my_session/Calib_scene.toml output/my_session \
    --height 1.84

# Docker: same arguments, with the container's paths
docker compose run --rm calib \
    /input/my_session /input/my_session/Calib_scene.toml /output/my_session --height 1.84
```

`--height` is the subject's height in metres; it sets the metric scale. The
origin and horizontal axis come from a frame where every camera sees the head and
both heels, chosen automatically (or `--ref_frame N`). On video faster than
50 Hz, add `--extract_fps 25`: same calibration, 2 to 8 times faster. Every
option is described in [HOWTO.md](https://github.com/flodelaplace/HumanCalib/blob/main/HOWTO.md).

**4. Results**, in `output/my_session/results/`:

| File | Contents |
|---|---|
| `Calib_scene_calibrated.toml` | The calibration: metric, gravity-aligned, Pose2Sim format |
| `3d_skeleton_FINAL.trc` | Triangulated skeleton |
| `camera/visu_3d_FINAL.gif` | 3D animation of the skeleton and cameras |
| `MRE_visualizations/` | Best and worst reprojection per camera, for diagnosis |

## Documentation

| | |
|---|---|
| [HOWTO.md](https://github.com/flodelaplace/HumanCalib/blob/main/HOWTO.md) | Full command-line reference, examples, diagnosis |
| [docs/METHOD.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/METHOD.md) | How each step works and why |
| [docs/TROUBLESHOOTING.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/TROUBLESHOOTING.md) | Common errors and fixes |
| [CONTRIBUTING.md](https://github.com/flodelaplace/HumanCalib/blob/main/CONTRIBUTING.md) | Development setup, tests, conventions |
| [CHANGELOG.md](https://github.com/flodelaplace/HumanCalib/blob/main/CHANGELOG.md) | Changes between versions |
| [docs/](https://github.com/flodelaplace/HumanCalib/blob/main/docs/README.md) | Evaluation protocol and research notes |

## Repository layout

```
src/humancalib/     the Python package: cli.py (the `humancalib` command), core/, pose/,
                    calibration/, pipeline/, postprocessing/, evaluation/
tests/              pytest suite, runs on a CPU in seconds
envs/               exact conda environments (calib, rtmpose, ci)
Dockerfile, compose.yaml, docker/    container images and entry point
demo/               4-camera demo session
docs/               documentation and research notes
input/, output/     your sessions and results (not tracked)
```

## Licensing

The HumanCalib code is **MIT**. The pretrained pose models are **not free for
commercial use**:

| Component | Licence |
|---|---|
| HumanCalib | MIT ([LICENSE](https://github.com/flodelaplace/HumanCalib/blob/main/LICENSE)) |
| MeTRAbs model (`metrabs_l`) | Non-commercial use only (training data licences) |
| VideoPose3D code and weights (optional backend) | CC BY-NC 4.0 |
| rtmlib (optional backend) | Apache-2.0; RTMPose weight licence not stated upstream |

The Docker images contain no MeTRAbs weights unless built with `BAKE_MODELS=1`.
This summary is not legal advice; check the upstream licences for your use.

## Citation

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23143081.svg)](https://doi.org/10.5281/zenodo.23143081)
Archived on Zenodo: [doi:10.5281/zenodo.23143081](https://doi.org/10.5281/zenodo.23143081)
(all versions; each release also has its own DOI, listed on that page).

Use GitHub's *Cite this repository* button ([CITATION.cff](https://github.com/flodelaplace/HumanCalib/blob/main/CITATION.cff)). Please
also cite the method HumanCalib builds on and the pose estimator:

- S.-E. Lee, K. Shibata, S. Nonaka, S. Nobuhara, K. Nishino. *Extrinsic Camera
  Calibration From a Moving Person.* IEEE Robotics and Automation Letters 7(4),
  2022. [doi:10.1109/LRA.2022.3192629](https://doi.org/10.1109/LRA.2022.3192629) —
  [original code](https://github.com/kyotovision-public/extrinsic-camera-calibration-from-a-moving-person)
- I. Sárándi, T. Linder, K. O. Arras, B. Leibe. *MeTRAbs: Metric-Scale
  Truncation-Robust Heatmaps for Absolute 3D Human Pose Estimation.* IEEE T-BIOM,
  2021.
- With the optional backend: T. Jiang et al. *RTMPose: Real-Time Multi-Person Pose
  Estimation based on MMPose.* arXiv:2303.07399, 2023; and D. Pavllo, C. Feichtenhofer,
  D. Grangier, M. Auli. *3D human pose estimation in video with temporal convolutions and
  semi-supervised training.* CVPR, 2019.

### Datasets of the evaluation

The validation above uses five public datasets, distributed by their authors under their own
terms. We thank them for making their recordings and calibrations available.

- **BioCV**: M. Evans et al. *Synchronised video, motion capture and force plate dataset for
  validating markerless human movement analysis.* Scientific Data 11, 1300, 2024; and
  L. Needham et al. *The development and evaluation of a fully automated markerless motion
  capture workflow.* Journal of Biomechanics 144, 111338, 2022.
- **I-MOVE-23**: Z. Li, S. Shin, V. Phan, E. Meinders, E. Halilaj. *Impact of multi-view fusion
  and biomechanical modeling on markerless motion tracking.* IEEE Transactions on Biomedical
  Engineering 73, 2054–2062, 2026.
- **OpenCap**: S. D. Uhlrich et al. *OpenCap: Human movement dynamics from smartphone videos.*
  PLoS Computational Biology 19, e1011462, 2023.
- **LBMC**: A. Muller, A. Naaïm, R. Dumas, T. Robert. *Benchmarking raw datasets and
  collaboratively-evolving processed data for markerless motion capture analysis.* Data in Brief
  62, 112044, 2025; data: [doi:10.57745/LQI2MJ](https://doi.org/10.57745/LQI2MJ).
- **COMFI**: K. Chalabi et al. *COMFI: a multimodal industrial human motion dataset for
  markerless motion capture and collaborative robotics.* International Journal of Robotics
  Research, 2026. [doi:10.1177/02783649261468361](https://doi.org/10.1177/02783649261468361)

The joint angles were computed with [Pose2Sim](https://github.com/perfanalytics/pose2sim)
(D. Pagnon, M. Domalain, L. Reveret, Sensors 21, 6530, 2021 and 22, 2712, 2022) and
OpenSim (A. Seth et al., PLoS Computational Biology 14, e1006223, 2018).
