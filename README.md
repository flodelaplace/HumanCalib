# HumanCalib

**Extrinsic calibration of a multi-camera rig from a person walking through it.**
No checkerboard, no wand: HumanCalib estimates the pose of every camera from the
human pose seen by all of them, then gives the rig a metric scale and a vertical
axis from the subject's height. The output is a
[Pose2Sim](https://github.com/perfanalytics/pose2sim)-format calibration, ready
for markerless motion capture.

![Overview](img/graphical_abstract.png)

## How it works

1. **Pose estimation** in every view with [MeTRAbs](https://github.com/isarandi/metrabs),
   which predicts a metric 3D skeleton per camera.
2. **Person selection**: the walking subject is kept in every camera, bystanders
   are discarded.
3. **Linear initialisation** by aligning the per-camera 3D skeletons (Procrustes).
4. **Bundle adjustment** of all cameras on the 2D keypoints.
5. **Metric scale and vertical** from the subject's height and walk.

Details, design choices and what was measured to justify them:
[docs/METHOD.md](docs/METHOD.md).

![3D result](img/visu_3d_FINAL.gif)

## Validation

Five public datasets, 77 trials, default settings. The three reported here each
provide a laboratory-grade reference calibration and enough trials to summarise.

**Camera geometry.** Relative rotation between camera pairs, against the
dataset's own calibration, and reprojection error of our own reconstruction,
which needs no reference. Median over trials [min–max]:

| Dataset | Cameras | Trials | Relative rotation error | Reprojection error (MRE) |
|---|---|---|---|---|
| IMOVE-23 | 10 | 11 | 0.42° [0.28–1.21] | 3.27 px [3.04–3.97] |
| BioCV | 9 | 18 | 0.62° [0.22–2.61] | 2.94 px [2.41–5.20] |
| OpenCap | 5 | 18 | 1.75° [0.82–2.20] | 1.67 px [1.38–2.14] |

Pixels are not comparable between rigs of different focal lengths; in angular
terms the same errors are 2.5, 2.3 and 1.8 mrad. A low reprojection error means
the calibration is not broken, not that it is accurate: on OpenCap the generic
smartphone intrinsics cap the accuracy while leaving the residual low.

**What it changes for the biomechanist.** The same
[Pose2Sim](https://github.com/perfanalytics/pose2sim) chain was run twice per
trial on the same 2D detections, with the laboratory calibration and with
HumanCalib's, changing nothing else. The table compares the joint angles the two
runs produce. Equivalence is declared when the upper bound of the 95 %
confidence interval stays below the margin, for each of the 9 degrees of freedom
(pelvis, hip, knee, ankle, subtalar):

| Dataset | Trials | RMSD between the two chains, median [min–max] | Worst degree of freedom | Equivalent within 2° |
|---|---|---|---|---|
| BioCV | 18 | 0.58° [0.24–2.54] | 1.09° | 9 / 9 |
| OpenCap | 18 | 0.57° [0.28–1.01] | 0.84° | 9 / 9 |
| IMOVE-23 | 11 | 0.90° [0.33–2.05] | 1.63° | 7 / 9 |

Changing the calibration therefore moves the reported angles by about half a
degree to one degree, below the 2° margin usually accepted in clinical gait
analysis, and roughly ten times less than the 4–11° that separates such a chain
from optical motion capture on the same trials.

- No failed calibration out of 77 (with RTMPose + VideoPose3D instead of MeTRAbs: 29).
- Metric scale within 1.0 % (median, on the four datasets not used to set it).

The two remaining datasets are reported in the paper: LBMC, whose two treadmill
trials are too few to summarise, and COMFI, where HumanCalib proved closer to
the laboratory's own motion capture than that dataset's own calibration, which
makes any comparison against that reference a measure of the reference rather
than of HumanCalib.

A paper is in preparation. The evaluation protocol is in
[docs/EVALUATION_PROTOCOL.md](docs/EVALUATION_PROTOCOL.md).

## Installation

Linux or Windows (WSL2), with an NVIDIA GPU (driver ≥ 525) for pose estimation.

### Docker (recommended)

Runs exactly the environment the results were obtained with. Requires Docker
with Compose v2 and the
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

```bash
git clone https://github.com/flodelaplace/HumanCalib.git
cd HumanCalib
printf 'HOST_UID=%s\nHOST_GID=%s\n' "$(id -u)" "$(id -g)" > .env   # results owned by you, not root
docker compose build                                                 # ~2 GB download, resumable
docker compose run --rm calib demo
```

It worked if the run ends with an MRE summary table and
`output/demo/results/Calib_scene_calibrated.toml` exists. The MeTRAbs model
(~700 MB) is downloaded on the first run and kept in a Docker volume.

### conda

```bash
git clone https://github.com/flodelaplace/HumanCalib.git
cd HumanCalib
conda env create -f envs/calib.yaml        # every version pinned
conda activate humancalib
pip install --no-deps -e .                 # adds the `humancalib` command, keeps the pins
humancalib run demo demo/Calib_scene.toml output/demo --height 1.78 --ref_frame 5
```

It worked if the log shows `Compute device: GPU` and ends with an MRE summary
table. The model is cached in `~/.cache/tfhub_modules` (set `TFHUB_CACHE_DIR` to
change it).

### pip (CPU steps only)

```bash
pip install "git+https://github.com/flodelaplace/HumanCalib"
```

Installs the library and the `humancalib` command: calibration, bundle
adjustment, evaluation and scaling from existing pose files, on a CPU. Pose
extraction needs CUDA libraries that pip cannot provide: use Docker or conda for
the full pipeline.

The optional RTMPose + VideoPose3D backend has its own image and environment:
see [HOWTO.md](HOWTO.md#optional-backend-rtmpose--videopose3d).

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
matter more than anything else: see [input/README.md](input/README.md).

**3. Run.**

```bash
humancalib run input/my_session input/my_session/Calib_scene.toml output/my_session \
    --height 1.84 --ref_frame 1415

# Docker: same arguments, with the container's paths
docker compose run --rm calib \
    /input/my_session /input/my_session/Calib_scene.toml /output/my_session \
    --height 1.84 --ref_frame 1415
```

`--height` is the subject's height in metres; `--ref_frame` a frame where both
heels are visible (it sets the origin). Every option is described in
[HOWTO.md](HOWTO.md).

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
| [HOWTO.md](HOWTO.md) | Full command-line reference, examples, diagnosis |
| [docs/METHOD.md](docs/METHOD.md) | How each step works and why |
| [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common errors and fixes |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development setup, tests, conventions |
| [CHANGELOG.md](CHANGELOG.md) | Changes between versions |
| [docs/](docs/README.md) | Evaluation protocol and research notes |

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
| HumanCalib | MIT ([LICENSE](LICENSE)) |
| MeTRAbs model (`metrabs_l`) | Non-commercial use only (training data licences) |
| VideoPose3D code and weights (optional backend) | CC BY-NC 4.0 |
| rtmlib (optional backend) | Apache-2.0; RTMPose weight licence not stated upstream |

The Docker images contain no MeTRAbs weights unless built with `BAKE_MODELS=1`.
This summary is not legal advice; check the upstream licences for your use.

## Citation

Use GitHub's *Cite this repository* button ([CITATION.cff](CITATION.cff)). Please
also cite the method HumanCalib builds on and the pose estimator:

- S.-E. Lee, K. Shibata, S. Nonaka, S. Nobuhara, K. Nishino. *Extrinsic Camera
  Calibration From a Moving Person.* IEEE Robotics and Automation Letters 7(4),
  2022. [doi:10.1109/LRA.2022.3192629](https://doi.org/10.1109/LRA.2022.3192629) —
  [original code](https://github.com/kyotovision-public/extrinsic-camera-calibration-from-a-moving-person)
- I. Sárándi, T. Linder, K. O. Arras, B. Leibe. *MeTRAbs: Metric-Scale
  Truncation-Robust Heatmaps for Absolute 3D Human Pose Estimation.* IEEE T-BIOM,
  2021.
