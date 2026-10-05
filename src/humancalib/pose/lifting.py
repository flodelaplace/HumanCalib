"""2D -> 3D lifting of the RTMPose backend: VideoPose3D on onnxruntime, no PyTorch.

Replaces pose/inference.py, which ran the original PyTorch code from a checkout of the
VideoPose3D repository and therefore needed PyTorch, that checkout and Python 3.8. The network is
the same one, converted to ONNX (scripts/export_videopose3d_onnx.py; ONNX = PyTorch to 1.2e-6);
what VideoPose3D does around it is reproduced here in numpy:

* coordinates normalised so that [0, width] maps to [-1, 1], keeping the aspect ratio;
* the sequence padded on both sides by repeating its first and last frames, half the receptive
  field (121 frames) each, so that every frame gets a prediction;
* test-time flip augmentation: the mirrored sequence (x negated, left and right swapped) is
  predicted too, mirrored back and averaged with the direct prediction.

Run by `humancalib run` (step 4) with the same arguments as the former module.
"""
import json
import os

import numpy as np

from humancalib.core import COCO_KEY, H36M17_KEY, OP_KEY, load_poses, op_to_coco
from humancalib.core.log import get_logger, setup_logging

log = get_logger(__name__)

RECEPTIVE_FIELD = 243
PAD = (RECEPTIVE_FIELD - 1) // 2
# COCO 2D input and Human3.6M 3D output: left/right pairs swapped by the flip augmentation
KPS_LEFT, KPS_RIGHT = [1, 3, 5, 7, 9, 11, 13, 15], [2, 4, 6, 8, 10, 12, 14, 16]
JOINTS_LEFT, JOINTS_RIGHT = [4, 5, 6, 11, 12, 13], [1, 2, 3, 14, 15, 16]


def model_path():
    """The ONNX model: HUMANCALIB_VP3D_ONNX if set, else the one scripts/setup_models.sh converted
    into a source checkout's model/ folder, else downloaded once and checked."""
    override = os.environ.get("HUMANCALIB_VP3D_ONNX")
    if override:
        return override
    from humancalib.core.models import VP3D_ONNX_FILE, VP3D_ONNX_SHA256, VP3D_ONNX_URL
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "model", VP3D_ONNX_FILE)
    if os.path.isfile(local):
        return os.path.normpath(local)
    if VP3D_ONNX_URL is None:
        raise RuntimeError(
            f"the VideoPose3D model ({VP3D_ONNX_FILE}) is not downloadable yet: run "
            "scripts/setup_models.sh in an environment with PyTorch (it converts it into model/), "
            "or set HUMANCALIB_VP3D_ONNX to the file.")
    from humancalib.pose.model_download import ensure_file
    return ensure_file(VP3D_ONNX_URL, VP3D_ONNX_FILE, VP3D_ONNX_SHA256, what="VideoPose3D model")


def session(path=None, device="cuda"):
    import onnxruntime as ort
    if device == "cuda":
        from humancalib.pose.onnx_gpu import preload_cuda_libraries
        preload_cuda_libraries()
    available = ort.get_available_providers()
    providers = (["CUDAExecutionProvider"] if device == "cuda" and "CUDAExecutionProvider" in available
                 else []) + ["CPUExecutionProvider"]
    sess = ort.InferenceSession(path or model_path(), providers=providers)
    used = sess.get_providers()[0]
    log.info(f"  -> VideoPose3D (ONNX) on {used.replace('ExecutionProvider', '')}")
    if device == "cuda" and used != "CUDAExecutionProvider":
        from humancalib.pose.onnx_gpu import cpu_fallback_hint
        log.warning("VideoPose3D runs on the CPU: onnxruntime could not create its CUDA provider. "
                    + cpu_fallback_hint())
    return sess


def lift(x2d_coco, width, height, sess):
    """(T, 17, 3) Human3.6M 3D pose, relative to the pelvis, from (T, 17, 2) COCO pixels."""
    x = np.asarray(x2d_coco, np.float32)[..., :2]
    x = x / width * 2 - np.array([1, height / width], np.float32)
    x = np.pad(x, ((PAD, PAD), (0, 0), (0, 0)), mode="edge")
    flipped = x.copy()
    flipped[..., 0] *= -1
    flipped[:, KPS_LEFT + KPS_RIGHT] = flipped[:, KPS_RIGHT + KPS_LEFT]
    pred = sess.run(None, {"keypoints_2d": np.stack([x, flipped])})[0]
    pred[1, :, :, 0] *= -1
    pred[1, :, JOINTS_LEFT + JOINTS_RIGHT] = pred[1, :, JOINTS_RIGHT + JOINTS_LEFT]
    return pred.mean(axis=0)


def convert_op_to_coco(kp_op):
    kp_coco = np.full((kp_op.shape[0], 17, kp_op.shape[2]), np.nan, dtype=np.float32)
    for k_op, k_coco in op_to_coco.items():
        kp_coco[:, COCO_KEY[k_coco], :] = kp_op[:, OP_KEY[k_op], :]
    return kp_coco


def h36m_17_to_op(pose_h36m):
    pose_op = np.full((pose_h36m.shape[0], len(OP_KEY), pose_h36m.shape[2]), np.nan, dtype=pose_h36m.dtype)
    for k, op_idx in OP_KEY.items():
        if k in H36M17_KEY:
            pose_op[:, op_idx, :] = pose_h36m[:, H36M17_KEY[k], :]
    pose_op[:, OP_KEY["Neck"], :] = (pose_op[:, OP_KEY["RShoulder"], :] + pose_op[:, OP_KEY["LShoulder"], :]) / 2.0
    pose_op[:, OP_KEY["MidHip"], :] = (pose_op[:, OP_KEY["RHip"], :] + pose_op[:, OP_KEY["LHip"], :]) / 2.0
    return pose_op


def save_json(out_dir, X3d_h36m, frames, aid, pid, gid, cid):
    """The 3D poses in the pipeline's JSON format (OpenPose-25 layout), as pose/inference.py did."""
    X3d_op = h36m_17_to_op(X3d_h36m)
    os.makedirs(os.path.join(out_dir, "3d_joint"), exist_ok=True)
    s3d = np.logical_not(np.all(np.isnan(X3d_op), axis=2)) * 1.0
    data = [{"frame_index": int(f), "skeleton": [{"pose": X3d_op[i].ravel().tolist(),
                                                  "score": s3d[i].tolist()}]}
            for i, f in enumerate(frames)]
    with open(os.path.join(out_dir, "3d_joint", f"A{aid:03d}_P{pid:03d}_G{gid:03d}_C{cid:03d}.json"), "w") as f:
        json.dump({"data": data}, f)


def main(argv=None):
    from humancalib import argument
    from humancalib.core.session import load_session_dir

    args = argument.parse_args(argv)
    prefix = os.path.join(args.prefix, args.target)
    session_info = load_session_dir(prefix)
    sess = session(device=args.device)
    for cid in session_info["camera_ids"]:
        log.info(f"############# - CAMID : {cid}")
        frames, x2d, _ = load_poses(os.path.join(
            prefix, "2d_joint", f"A{args.aid:03d}_P{args.pid:03d}_G{args.gid:03d}_C{cid:03d}.json"))
        x2d_coco = convert_op_to_coco(x2d.reshape(len(frames), len(OP_KEY), 2))
        X3d = lift(x2d_coco, session_info["width"], session_info["height"], sess)
        save_json(prefix, X3d, frames, args.aid, args.pid, args.gid, cid)


if __name__ == "__main__":
    setup_logging()
    main()
