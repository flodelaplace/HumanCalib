# Troubleshooting

## Installation and Docker

| Problem | Cause | Solution |
|---|---|---|
| `could not select device driver "" with capabilities: [[gpu]]` | NVIDIA Container Toolkit missing | Install it, then restart the Docker daemon |
| `error getting credentials ... docker-credential-desktop.exe: exec format error` | WSL: Docker Desktop's credential helper cannot run from Linux | Remove `"credsStore": "desktop.exe"` from `~/.docker/config.json` |
| `Timeout was reached` during `docker compose build` | Slow or unstable connection | Run `docker compose build` again: downloads resume |
| `ERROR: /output is not writable by uid ...` | `output/` owned by another user, e.g. root | Create `.env` as in the [installation](../README.md#docker-recommended), or fix the ownership of `output/` |
| `ERROR: this container can see a GPU, but cannot load the CUDA runtime` | `LD_LIBRARY_PATH` overridden at run time | Append to it instead of replacing it; the message shows the value to use |
| `libcuda.so not found` (conda, WSL2) | CUDA driver path missing | `humancalib run` adds `/usr/lib/wsl/lib` automatically; otherwise `export LD_LIBRARY_PATH=/usr/lib/wsl/lib:$LD_LIBRARY_PATH` |
| `ImportError: libGL.so.1` | Minimal Linux without OpenCV's system libraries | `sudo apt-get install libgl1 libglib2.0-0` |
| MeTRAbs import error | TensorFlow not in the environment | Use the conda environment or Docker. `HUMANCALIB_METRABS_PYTHON` can point to another interpreter |
| `the RTMPose backend is not installed in this environment` | `--pose_engine rtmpose` without that backend | Use the RTMPose image or environment, or the default MeTRAbs |

## Calibration quality

| Problem | Cause | Solution |
|---|---|---|
| One camera much worse than the others | Wrong intrinsics for that camera, most often | In the linear log, a low Procrustes residual (≤ ~100 mm) with a high MRE points to a wrong camera matrix or distortion. Check k1, k2: beyond about ±5 they are almost certainly wrong. See `MRE_visualizations/` |
| High MRE on all cameras | Cameras not synchronised, or wrong intrinsics | A few frames of offset double the MRE. Check synchronisation first |
| A bystander is calibrated instead of the subject | Person selection | The default `--person_selection motion` keeps the walking person; check that the subject actually walks |
| `No valid orientations` | Too few frames where enough cameras see the subject | Lower `--conf_threshold`, or choose a frame range where the subject crosses the volume |
| Wrong vertical or scale | The subject does not walk (standing, balance task, treadmill) | `--vertical_method frame` with a `--ref_frame` on which the subject stands straight |
| Corrupted or half-decoded frames | Encoding artefacts | Dropped automatically between the linear step and BA; see `<output>/noise_1_0/dropped_frames/` |
| Out of memory during BA | Too many frames | Retried automatically with a larger `--frame_skip` (up to 60) |
| Poses not re-extracted after changing the TOML | The cache checks only the frame range | Delete `<output>/noise_1_0/2d_joint` and `3d_joint` |
