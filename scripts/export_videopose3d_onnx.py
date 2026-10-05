"""Convert the VideoPose3D checkpoint used by the RTMPose backend to ONNX.

A development tool, run once; users download the resulting .onnx file. It needs PyTorch and the
VideoPose3D sources (scripts/setup_models.sh), e.g. in envs/rtmpose.yaml:

    python scripts/export_videopose3d_onnx.py \
        --checkpoint model/pretrained_h36m_detectron_coco.bin \
        --output model/videopose3d_h36m_detectron_coco.onnx

The network is exported alone, with dynamic batch and time axes. Everything around it --
normalisation, edge padding of the sequence, flip augmentation -- is numpy code in
humancalib/pose/lifting.py, so the runtime needs only onnxruntime. The script checks that ONNX
and PyTorch agree on random input before it reports success.
"""
import argparse
import hashlib
import os
import sys

import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.environ.get("HUMANCALIB_VP3D_DIR", os.path.join(REPO, "third_party", "VideoPose3D")))

# The architecture of pretrained_h36m_detectron_coco.bin (receptive field 243 frames)
ARCH = dict(num_joints_in=17, in_features=2, num_joints_out=17, filter_widths=[3, 3, 3, 3, 3],
            causal=False, dropout=0.25, channels=1024, dense=False)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--checkpoint", default=os.path.join(REPO, "model", "pretrained_h36m_detectron_coco.bin"))
    p.add_argument("--output", default=os.path.join(REPO, "model", "videopose3d_h36m_detectron_coco.onnx"))
    p.add_argument("--opset", type=int, default=13)
    args = p.parse_args()

    import torch
    from common.model import TemporalModel

    model = TemporalModel(**ARCH)
    state = torch.load(args.checkpoint, map_location="cpu")
    model.load_state_dict(state["model_pos"])
    model.eval()
    field = model.receptive_field()

    dummy = torch.zeros(2, field + 10, 17, 2)
    torch.onnx.export(model, dummy, args.output, opset_version=args.opset,
                      input_names=["keypoints_2d"], output_names=["keypoints_3d"],
                      dynamic_axes={"keypoints_2d": {0: "batch", 1: "frames"},
                                    "keypoints_3d": {0: "batch", 1: "frames_out"}})

    import onnxruntime as ort
    x = np.random.default_rng(0).uniform(-1, 1, size=(2, field + 37, 17, 2)).astype(np.float32)
    with torch.no_grad():
        ref = model(torch.from_numpy(x)).numpy()
    out = ort.InferenceSession(args.output, providers=["CPUExecutionProvider"]).run(None, {"keypoints_2d": x})[0]
    err = float(np.abs(out - ref).max())
    if out.shape != ref.shape or err > 1e-4:
        sys.exit(f"ONNX and PyTorch disagree: shapes {out.shape} vs {ref.shape}, max |diff| {err:.2e}")
    digest = hashlib.sha256(open(args.output, "rb").read()).hexdigest()
    print(f"receptive field {field} frames; ONNX = PyTorch to {err:.1e}")
    print(f"{args.output}  {os.path.getsize(args.output) / 1e6:.1f} MB  sha256 {digest}")


if __name__ == "__main__":
    main()
