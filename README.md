# HumanCalib

**Extrinsic calibration of a multi-camera rig from a person walking through it.**
No checkerboard, no wand: HumanCalib estimates the pose of every camera from the
human pose seen by all of them, then gives the rig a metric scale and a vertical
axis from the subject's height. The output is a
[Pose2Sim](https://github.com/perfanalytics/pose2sim)-format calibration, ready
for markerless motion capture.

![Overview](https://raw.githubusercontent.com/flodelaplace/HumanCalib/main/img/graphical_abstract.png)

## How it works

1. **Pose estimation** in every view with [MeTRAbs](https://github.com/isarandi/metrabs),
   which predicts a metric 3D skeleton per camera.
2. **Person selection**: the walking subject is kept in every camera, bystanders
   are discarded.
3. **Linear initialisation** by aligning the per-camera 3D skeletons (Procrustes).
4. **Bundle adjustment** of all cameras on the 2D keypoints.
5. **Metric scale and vertical** from the subject's height and walk.

Details, design choices and what was measured to justify them:
[docs/METHOD.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/METHOD.md).

![3D result](https://raw.githubusercontent.com/flodelaplace/HumanCalib/main/img/visu_3d_FINAL.gif)

## Validation

Five public datasets, 77 trials, default settings. The three reported here each
provide a laboratory-grade reference calibration and enough trials to summarise.

**Camera geometry.** Relative rotation between camera pairs, against the
dataset's own calibration, and reprojection error of our own reconstruction,
which needs no reference. Median over trials [min–max]:

| Dataset | Cameras | Trials | Relative rotation error | Reprojection error (MRE) |
|---|---|---|---|---|
| IMOVE-23 | 10 | 11 | 0.40° [0.30–0.96] | 3.30 px [2.95–3.83] |
| BioCV | 9 | 18 | 0.43° [0.25–0.95] | 2.77 px [2.35–4.07] |
| OpenCap | 5 | 18 | 1.89° [0.56–2.31] | 1.69 px [1.38–2.16] |

Pixels are not comparable between rigs of different focal lengths; in angular
terms the same errors are 2.4, 2.1 and 1.8 mrad. A low reprojection error means
the calibration is not broken, not that it is accurate: on OpenCap, five
smartphones on a tight arc and a walk of about two seconds cap the accuracy
while leaving the residual low.

**What it changes for the biomechanist.** The same
[Pose2Sim](https://github.com/perfanalytics/pose2sim) chain was run twice per
trial on the same 2D detections, with the laboratory calibration and with
HumanCalib's, changing nothing else. The table compares the joint angles the two
runs produce. Equivalence is declared when the upper bound of the 95 %
confidence interval stays below the margin, for each of the 9 degrees of freedom
(pelvis, hip, knee, ankle, subtalar):

| Dataset | Trials | RMSD between the two chains, median [min–max] | Worst degree of freedom | Equivalent within 2° |
|---|---|---|---|---|
| BioCV | 18 | 0.40° [0.20–2.45] | 0.94° | 9 / 9 |
| OpenCap | 18 | 0.58° [0.35–1.13] | 0.98° | 9 / 9 |
| IMOVE-23 | 11 | 0.82° [0.46–1.67] | 1.38° | 8 / 9 |

Changing the calibration therefore moves the reported angles by about half a
degree to one degree, below the 2° margin usually accepted in clinical gait
analysis, and roughly ten times less than the 4–11° that separates such a chain
from optical motion capture on the same trials.

- No failed calibration out of 77.
- Metric scale within 1.1 % (median, on the four datasets not used to set it).

**With RTMPose + VideoPose3D** instead of MeTRAbs (the backend Pose2Sim already installs),
1 calibration out of 77 fails (30 before 0.5: the walking person is now told apart in 3D and the
cameras initialised camera by camera, see [METHOD.md](https://github.com/flodelaplace/HumanCalib/blob/main/docs/METHOD.md)). On the 76 trials both
engines calibrate, median relative rotation error:

| | IMOVE-23 | BioCV | OpenCap | All five datasets |
|---|---|---|---|---|
| MeTRAbs | 0.40° | 0.43° | 1.89° | 0.95° |
| RTMPose + VideoPose3D | 0.33° | 0.49° | 1.95° | 1.27° |

No difference is detectable in rotation (paired Wilcoxon, p = 0.51); MeTRAbs remains more
reliable (no failure) and more accurate in scale (0.95 % against 1.5 %).

The two remaining datasets are reported in the paper: LBMC, whose two treadmill
trials are too few to summarise, and COMFI, where HumanCalib proved closer to
the laboratory's own motion capture than that dataset's own calibration, which
makes any comparison against that reference a measure of the reference rather
than of HumanCalib.

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
[source archive](https://github.com/flodelaplace/HumanCalib/archive/refs/tags/v0.5.2.zip)
(or `git clone` the repository), then

```bash
humancalib run HumanCalib-0.5.2/demo HumanCalib-0.5.2/demo/Calib_scene.toml output/demo --height 1.78
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
