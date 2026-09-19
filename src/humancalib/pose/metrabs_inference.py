"""
metrabs_inference.py
--------------------
Extract 2D and 3D poses from multi-camera videos using MeTRAbs (bml_movi_87)
and save them in the 26-joint calibration format expected by the pipeline.

This script is designed to run in the 'metrabs' conda environment (Python 3.10,
TensorFlow) and is called from calibrate.sh via:
    conda run --no-banner -n metrabs_opensim python metrabs_inference.py ...

It replaces both rtmlib_inference.py (2D) and inference.py (3D lifting) in a
single step with better accuracy.

Usage:
    conda run --no-banner -n metrabs_opensim python metrabs_inference.py \
        --video_dir  ./my_videos \
        --calib_toml ./Calib_scene.toml \
        --output_dir ./data/A001_P001_G001 \
        --aid 1 --pid 1 --gid 1 \
        --batch_size 8
"""

# --- Silence TensorFlow startup noise ------------------------------------
# These MUST be set BEFORE `import tensorflow` / `import tensorflow_hub`.
import os
from humancalib.core.log import get_logger, setup_logging
log = get_logger(__name__)
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'       # hide TF INFO/WARNING (keep ERROR+)
os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'      # silence the oneDNN custom-ops notice
# Persistent TF-Hub cache: without this, tfhub.load() caches to /tmp/tfhub_modules,
# which WSL wipes on restart -> the ~400MB metrabs_l model is re-downloaded every run.
# Pin it to a persistent dir (override with a pre-set TFHUB_CACHE_DIR if desired).
os.environ.setdefault('TFHUB_CACHE_DIR', os.path.expanduser('~/.cache/tfhub_modules'))
os.makedirs(os.environ['TFHUB_CACHE_DIR'], exist_ok=True)

import warnings
warnings.filterwarnings('ignore')              # silence pkg_resources deprecation, etc.
# ---------------------------------------------------------------------------

import argparse
import sys

from humancalib.core.models import METRABS_L_URL
from humancalib.core.toml_io import intrinsics_from_toml
from humancalib.core.sidecars import read_dropped
from humancalib.core.videos import list_videos
from humancalib.pose.candidates import (STATUS_DARK, STATUS_DROPPED, STATUS_OK,
                                        candidates_path, save_candidates)
from humancalib.pose.metrabs_outputs import save_skeleton_w, write_camera_outputs

import numpy as np
import imageio
from tqdm import tqdm

import tensorflow as tf
tf.get_logger().setLevel('ERROR')              # defensive: also silence Python-side TF logger
import tensorflow_hub as tfhub

# ---------------------------------------------------------------------------
# 26-joint calibration skeleton (subset of bml_movi_87): 20 virtual joint
# centres + backneck + sternum + 4 foot markers.
#
# Imported, not redefined. This file used to carry its own copy of the list,
# from when it ran in a separate conda environment that could not import the
# shared code. A second copy of an index list that must agree with the bone
# topology is a silent-divergence trap.
# ---------------------------------------------------------------------------
from humancalib.core.skeletons import METRABS_BML87_INDICES
N_CALIB_JOINTS = len(METRABS_BML87_INDICES)  # 26

# ---------------------------------------------------------------------------
# bml_movi_87 -> Halpe26 mapping (for scale_scene.py compatibility)
# Halpe26 indices: Head=17, Neck=18, MidHip=19, LBigToe=20, RBigToe=21,
#                  LSmallToe=22, RSmallToe=23, LHeel=24, RHeel=25
# ---------------------------------------------------------------------------


def get_best_person(poses3d, poses2d, boxes, imshape=None):
    """Select the best person based on bounding box area, with quality filtering."""
    if len(boxes) == 0:
        return None, None, 0.0

    areas = boxes[:, 2] * boxes[:, 3]  # width * height
    best_idx = int(np.argmax(areas))
    conf = float(boxes[best_idx, 4])

    # Filter: bbox too small relative to image → likely false positive
    if imshape is not None:
        img_area = imshape[0] * imshape[1]
        if areas[best_idx] < 0.005 * img_area:  # < 0.5% of image
            return None, None, 0.0

    return poses3d[best_idx], poses2d[best_idx], conf


def process_video(video_path, model, skeleton, intrinsic_matrix, output_dir, subset,
                  start_frame=None, end_frame=None, batch_size=8):
    """Run MeTRAbs on a video and return per-frame poses.

    Uses a streaming generator to avoid loading all frames into RAM.
    """
    reader = imageio.get_reader(video_path, 'ffmpeg')
    total_frames = reader.count_frames()
    imshape = reader.get_data(0).shape[:2]
    reader.close()

    sf = start_frame if start_frame is not None else 0
    ef = end_frame if end_frame is not None else total_frames - 1
    if sf > ef or sf < 0 or ef >= total_frames:
        log.error(f"Invalid frame range ({sf} to {ef}) for {video_path}")
        return [], [], [], [], None

    n_frames = ef - sf + 1
    log.info(f"  Video: {os.path.basename(video_path)} ({imshape[1]}x{imshape[0]}, frames {sf}-{ef})")

    # Deterministic list of frames to treat as missing (black / corrupted).
    dropped_set = read_dropped(output_dir, subset, video_path)
    if dropped_set:
        in_range = sum(1 for i in dropped_set if sf <= i <= ef)
        log.info(f"  Sidecar: {in_range}/{len(dropped_set)} dropped indices in range [{sf},{ef}]")

    # Generator that yields frames one by one (no bulk RAM allocation)
    def frame_generator():
        rd = imageio.get_reader(video_path, 'ffmpeg')
        for idx, frame in enumerate(rd):
            if idx < sf:
                continue
            if idx > ef:
                break
            yield frame
        rd.close()

    frame_ds = tf.data.Dataset.from_generator(
        frame_generator,
        output_signature=tf.TensorSpec(shape=(imshape[0], imshape[1], 3), dtype=tf.uint8)
    ).batch(batch_size).prefetch(1)

    all_poses3d = []
    all_poses2d = []
    all_confidences = []
    frame_indices = list(range(sf, sf + n_frames))
    n_dark = 0
    n_drop = 0
    # Every detection, for geometric person re-selection (pose/candidates.py).
    cand_status, cand_dets = [], []

    n_batches = int(np.ceil(n_frames / batch_size))
    for frame_batch in tqdm(frame_ds, total=n_batches, desc="  MeTRAbs inference"):
        pred = model.detect_poses_batched(
            frame_batch,
            intrinsic_matrix=intrinsic_matrix[tf.newaxis],
            skeleton=skeleton,
        )

        for i, (boxes, poses3d, poses2d) in enumerate(
            zip(pred['boxes'], pred['poses3d'], pred['poses2d'])
        ):
            current_idx = sf + len(all_poses3d)

            # Sidecar filter (authoritative — deterministic drop list)
            if current_idx in dropped_set:
                all_poses3d.append(None)
                all_poses2d.append(None)
                all_confidences.append(0.0)
                cand_status.append(STATUS_DROPPED)
                cand_dets.append(None)
                n_drop += 1
                continue

            # Brightness fallback (catches dark frames on videos without sidecar)
            frame_brightness = float(tf.reduce_mean(
                tf.cast(frame_batch[i], tf.float32)
            ).numpy())
            if frame_brightness < 15:
                all_poses3d.append(None)
                all_poses2d.append(None)
                all_confidences.append(0.0)
                cand_status.append(STATUS_DARK)
                cand_dets.append(None)
                n_dark += 1
                continue

            boxes_np = boxes.numpy()
            poses3d_np, poses2d_np = poses3d.numpy(), poses2d.numpy()
            cand_status.append(STATUS_OK)
            cand_dets.append({"box": boxes_np, "pose2d": poses2d_np, "pose3d": poses3d_np})
            p3d_best, p2d_best, conf = get_best_person(
                poses3d_np, poses2d_np, boxes_np, imshape=imshape
            )

            # --- Skeleton plausibility check ---
            if p2d_best is not None:
                spread = np.std(p2d_best, axis=0).mean()
                if spread < 20:  # all joints collapsed to same spot
                    p3d_best, p2d_best, conf = None, None, 0.0

            all_poses3d.append(p3d_best)
            all_poses2d.append(p2d_best)
            all_confidences.append(conf)

    if n_drop > 0:
        log.info(f"  Filtered {n_drop}/{n_frames} frames via sidecar")
    if n_dark > 0:
        log.info(f"  Filtered {n_dark}/{n_frames} dark frames (brightness fallback)")

    candidates = {"status": cand_status, "detections": cand_dets, "imshape": imshape}
    return frame_indices, all_poses3d, all_poses2d, all_confidences, candidates


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Extract 2D+3D poses with MeTRAbs (bml_movi_87) for multi-camera calibration."
    )
    parser.add_argument("--video_dir", required=True, help="Folder containing camera video files")
    parser.add_argument("--calib_toml", required=True, help="TOML file with camera intrinsics")
    parser.add_argument("--output_dir", required=True, help="Output folder (e.g. ./data/A001_P001_G001)")
    parser.add_argument("--aid", type=int, default=1, help="Action ID")
    parser.add_argument("--pid", type=int, default=1, help="Person ID")
    parser.add_argument("--gid", type=int, default=1, help="Group/Scene ID")
    parser.add_argument("--subset_name", default="noise_1_0", help="Subset folder name")
    parser.add_argument("--start_frame", type=int, default=None, help="Start frame index")
    parser.add_argument("--end_frame", type=int, default=None, help="End frame index")
    parser.add_argument("--batch_size", type=int, default=8, help="Batch size for inference")
    parser.add_argument("--skeleton", default="bml_movi_87", help="MeTRAbs skeleton name")
    args = parser.parse_args(argv)

    # Collect and sort video files
    video_files = list_videos(args.video_dir)

    if not video_files:
        log.error(f"No video files found in {args.video_dir}")
        sys.exit(1)

    log.info(f"Found {len(video_files)} video(s):")
    for i, v in enumerate(video_files):
        log.info(f"  [{i+1}] {os.path.basename(v)}")

    # Get camera names (same logic as calibrate.sh)
    cam_names = [os.path.splitext(os.path.basename(v))[0] for v in video_files]

    # Load intrinsics from TOML
    K_list, dist_list = intrinsics_from_toml(args.calib_toml, cam_names)
    log.info(f"\nLoaded intrinsics for {len(K_list)} cameras from {args.calib_toml}")

    # Say plainly which device this will run on. Falling back to CPU is not an
    # error and TensorFlow does it silently, so the only symptom is that a
    # 20-second job takes five minutes -- easy to blame on the model, the video
    # or the machine. On a GPU host, seeing "CPU" here means the CUDA runtime
    # libraries are not on the loader path (LD_LIBRARY_PATH).
    _gpus = tf.config.list_physical_devices('GPU')
    if _gpus:
        log.info(f"\nCompute device: GPU ({len(_gpus)} visible to TensorFlow)")
    else:
        log.warning(
            "Compute device: CPU -- no GPU visible to TensorFlow; inference will be "
            "roughly 15x slower. On a machine with a GPU this means TensorFlow cannot "
            "find the CUDA runtime libraries. `humancalib run` and scripts/calibrate.sh "
            "put the environment's lib/ on the loader path themselves; when running "
            "this step directly, do it first:\n"
            "  export LD_LIBRARY_PATH=\"$CONDA_PREFIX/lib:$LD_LIBRARY_PATH\"")

    # Load MeTRAbs model (this takes 30-60s: model loading + TF graph compilation)
    log.info(f"\nLoading MeTRAbs model (skeleton={args.skeleton}) — please wait...")
    model = tfhub.load(METRABS_L_URL)
    log.info("Model loaded. Running warmup inference...")
    # Warmup: first call triggers TF graph compilation (slow), subsequent calls are fast
    _dummy = np.zeros((1, 256, 256, 3), dtype=np.uint8)
    model.detect_poses_batched(tf.constant(_dummy), skeleton=args.skeleton)
    log.info("Warmup done. Starting pose extraction.\n")

    # Create output directories
    out_2d_dir = os.path.join(args.output_dir, args.subset_name, "2d_joint")
    out_3d_dir = os.path.join(args.output_dir, args.subset_name, "3d_joint")
    out_halpe26_dir = os.path.join(args.output_dir, args.subset_name, "2d_joint_halpe26")
    os.makedirs(out_2d_dir, exist_ok=True)
    os.makedirs(out_3d_dir, exist_ok=True)
    os.makedirs(out_halpe26_dir, exist_ok=True)

    skeleton_w_data = None  # Will store first camera's 3D for skeleton_w

    for cam_idx, (video_path, K, dist) in enumerate(zip(video_files, K_list, dist_list), start=1):
        cid = cam_idx
        base_name = f"A{args.aid:03d}_P{args.pid:03d}_G{args.gid:03d}_C{cid:03d}.json"

        log.info(f"\n[Camera {cid}]")

        # MeTRAbs only consumes the intrinsic matrix; lens distortion is handled
        # separately by undistort_points() on the predicted 2D keypoints below.
        # Run inference
        frame_indices, poses3d_raw, poses2d_raw, confidences, candidates = process_video(
            video_path, model, args.skeleton, K.astype(np.float32),
            args.output_dir, args.subset_name,
            start_frame=args.start_frame, end_frame=args.end_frame,
            batch_size=args.batch_size,
        )

        if not frame_indices:
            log.warning(f"No frames processed for camera {cid}")
            continue

        save_candidates(candidates_path(args.output_dir, args.subset_name, base_name),
                        frame_indices, candidates["status"], candidates["detections"],
                        candidates["imshape"])

        # Get image dimensions for per-joint quality scoring
        _reader = imageio.get_reader(video_path, 'ffmpeg')
        img_h, img_w = _reader.get_data(0).shape[:2]
        _reader.close()
        full87_3d_list = write_camera_outputs(
            frame_indices, poses3d_raw, poses2d_raw, confidences, K, dist, img_w, img_h,
            out_2d_dir, out_3d_dir, out_halpe26_dir, base_name)

        # Store first camera's 3D for skeleton_w
        if skeleton_w_data is None:
            skeleton_w_data = (frame_indices, full87_3d_list)

    # Save skeleton_w (reference 3D from first camera)
    if skeleton_w_data is not None:
        skel_path = os.path.join(args.output_dir, args.subset_name, f"skeleton_w_G{args.gid:03d}.json")
        save_skeleton_w(skel_path, skeleton_w_data[0], skeleton_w_data[1])
        log.info(f"\nSaved skeleton_w -> {skel_path}")

    log.info("\n" + "=" * 60)
    log.info("MeTRAbs pose extraction complete!")
    log.info(f"Output: {args.output_dir}/{args.subset_name}/")
    log.info(f"  2d_joint/        : bml_movi_87 2D poses (87 joints)")
    log.info(f"  3d_joint/        : bml_movi_87 3D poses (87 joints)")
    log.info(f"  2d_joint_halpe26/: Halpe26 2D poses (for scaling)")
    log.info("=" * 60)


if __name__ == "__main__":
    setup_logging()
    main()
