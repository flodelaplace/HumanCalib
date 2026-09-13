#!/bin/bash
# Fetch the assets needed by the OPTIONAL RTMPose + VideoPose3D pose backend.
#
# The default backend (MeTRAbs) does NOT need this script: its model is fetched
# automatically from TensorFlow Hub on first run.
#
# ---------------------------------------------------------------------------
# LICENSING NOTICE
#   VideoPose3D is licensed CC BY-NC 4.0 (non-commercial), and the pretrained
#   weights downloaded here were trained on Human3.6M, which is restricted to
#   academic use. HumanCalib itself is MIT-licensed, but ANY use of this
#   optional backend inherits those restrictions. The MeTRAbs backend is not
#   affected. See README.md for details.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Pinned so every install reproduces the same code and weights.
VP3D_REPO="https://github.com/facebookresearch/VideoPose3D"
VP3D_COMMIT="1afb1ca0f1237776518469876342fc8669d3f6a9"
WEIGHTS_URL="https://dl.fbaipublicfiles.com/video-pose-3d/pretrained_h36m_detectron_coco.bin"
WEIGHTS_SHA256="d3219e005b50591f694da5cbaf6849f060d6b2cf895864a779f8a992ac63a232"

echo "=== 1/2  VideoPose3D source (pinned at ${VP3D_COMMIT:0:12}) ==="

if [ -d "./third_party/VideoPose3D/.git" ] && \
   [ "$(git -C ./third_party/VideoPose3D rev-parse HEAD 2>/dev/null)" = "${VP3D_COMMIT}" ]; then
    echo "  Already at the pinned commit."
else
    if [ -e "./third_party/VideoPose3D" ]; then
        echo "  ERROR: ./third_party/VideoPose3D exists but is not at the pinned commit."
        echo "         Remove it and re-run:  rm -rf ./third_party/VideoPose3D"
        exit 1
    fi
    mkdir -p ./third_party
    git clone --quiet "${VP3D_REPO}" ./third_party/VideoPose3D
    git -C ./third_party/VideoPose3D checkout --quiet "${VP3D_COMMIT}"
    echo "  Cloned and checked out."
fi

if [ ! -f "./third_party/VideoPose3D/common/model.py" ]; then
    echo "  ERROR: VideoPose3D checkout looks incomplete (common/model.py missing)."
    exit 1
fi

echo "=== 2/2  Pretrained weights ==="

mkdir -p ./model
WEIGHTS_PATH="./model/pretrained_h36m_detectron_coco.bin"

if [ ! -f "${WEIGHTS_PATH}" ]; then
    echo "  Downloading (65 MB)..."
    wget -q --show-progress -O "${WEIGHTS_PATH}" "${WEIGHTS_URL}"
fi

echo "  Verifying checksum..."
if ! echo "${WEIGHTS_SHA256}  ${WEIGHTS_PATH}" | sha256sum --check --status; then
    echo "  ERROR: checksum mismatch for ${WEIGHTS_PATH}."
    echo "         The download is corrupt or the upstream file changed."
    echo "         Delete it and re-run:  rm -f ${WEIGHTS_PATH}"
    exit 1
fi
echo "  Checksum OK."

echo
echo "Setup complete. Remember: this backend is CC BY-NC 4.0 (see notice above)."
