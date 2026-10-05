"""Identity of the pretrained models the pipeline downloads at run time.

Kept in a module of its own, with no imports, for two reasons: the URL has
exactly one definition, and the Docker build can read it to pre-populate the
TensorFlow-Hub cache without importing TensorFlow or the rest of the package.

Resolved from the upstream 'https://bit.ly/metrabs_l' shortener and hardcoded:
a third-party URL shortener in the critical path is unversioned, silently
retargetable and blocked by many institutional proxies. The filename encodes
the full model identity -- EfficientNetV2-L backbone, YOLOv4 detector, 384 px
input, 800k steps, 28 training datasets.

TF-Hub caches a module under a directory named after the SHA-1 of this string,
so changing the URL invalidates the cache and forces a fresh ~708 MB download.
"""

METRABS_L_URL = (
    "https://omnomnom.vision.rwth-aachen.de/data/metrabs/"
    "metrabs_eff2l_y4_384px_800k_28ds.tar.gz"
)

# VideoPose3D (Pavllo et al., CVPR 2019), the 2D -> 3D lifting of the RTMPose backend, converted to
# ONNX by scripts/export_videopose3d_onnx.py from the official pretrained_h36m_detectron_coco.bin
# (ONNX = PyTorch to 1.2e-6). Weights: CC BY-NC 4.0, Facebook Research. Hosted as an asset of the
# v0.3.1 GitHub release (docs/RELEASING.md) so that the backend needs only onnxruntime, no PyTorch.
VP3D_ONNX_FILE = "videopose3d_h36m_detectron_coco.onnx"
VP3D_ONNX_URL = "https://github.com/flodelaplace/HumanCalib/releases/download/v0.3.1/" + VP3D_ONNX_FILE
VP3D_ONNX_SHA256 = "c9703125e99c2ca93e233001446448ab57ec0305d2fccabf7f2c9c9dfa1de7d3"
