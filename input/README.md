# Input directory

Put each calibration session in its own folder here:

```
input/
  my_session/
    camera01.mp4
    camera02.mp4
    camera03.mp4
    Calib_scene.toml
```

1. **Synchronised videos**, one per camera: `.mp4`, `.avi`, `.mov` or `.mkv`.
   The file name without its extension is the camera's name and must match a
   section of the TOML.

   Cameras are numbered in **alphabetical order** of those names. Pad numbers
   with zeros — `camera01 … camera10`, not `camera1 … camera10` — so that this
   order is the one you expect: `camera10` sorts before `camera2`.

2. **`Calib_scene.toml`**, the intrinsics of every camera in
   [Pose2Sim](https://github.com/perfanalytics/pose2sim) format:

   ```toml
   [camera01]
   name = "camera01"
   size = [1920.0, 1080.0]
   matrix = [[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]]
   distortions = [k1, k2, p1, p2]
   fisheye = false
   ```

   Intrinsic quality is the first driver of the final error: distortion
   coefficients k1, k2 above about 5 in absolute value are almost certainly
   wrong.

The pipeline never writes into this folder. With Docker it is mounted
read-only at `/input`.

## Optional: frames to ignore

A `<video>.dropped.json` file lists absolute frame numbers to ignore everywhere
in the pipeline — black, corrupted or half-decoded frames:

```json
{ "dropped_frame_indices": [1273, 1274, 1825] }
```

The automatic outlier-frame step writes its own under
`<output_dir>/noise_1_0/dropped_frames/`. To flag known bad frames before a first
run, place a hand-written one next to its video here (`camera01.dropped.json`):
it is read and merged with the automatic ones.

Videos and data files in this directory are ignored by git.
