"""VideoPose3D on onnxruntime: what surrounds the network reproduces VideoPose3D's own code."""
import os
import sys
import types

import numpy as np
import pytest

from humancalib.pose import lifting, onnx_gpu

ONNX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "model",
                    "videopose3d_h36m_detectron_coco.onnx")


class _Recorder:
    """Stands for the network: records its input, returns the central frames' x, y and a zero z."""

    def run(self, _, feeds):
        x = feeds["keypoints_2d"]
        self.seen = x
        core = x[:, lifting.PAD:x.shape[1] - lifting.PAD]
        return [np.concatenate([core, np.zeros(core.shape[:-1] + (1,), np.float32)], axis=-1)]


def test_input_is_normalised_padded_and_flipped_as_videopose3d_does():
    T, w, h = 30, 1920, 1080
    x = np.random.default_rng(0).uniform(0, 1000, size=(T, 17, 2)).astype(np.float32)
    rec = _Recorder()
    out = lifting.lift(x, w, h, rec)
    seen = rec.seen
    assert seen.shape == (2, T + 2 * lifting.PAD, 17, 2)
    norm = x / w * 2 - np.array([1, h / w], np.float32)
    assert np.allclose(seen[0, lifting.PAD:-lifting.PAD], norm)
    assert np.allclose(seen[0, :lifting.PAD], norm[0]) and np.allclose(seen[0, -lifting.PAD:], norm[-1])
    mirrored = seen[0].copy()
    mirrored[..., 0] *= -1
    mirrored[:, lifting.KPS_LEFT + lifting.KPS_RIGHT] = mirrored[:, lifting.KPS_RIGHT + lifting.KPS_LEFT]
    assert np.allclose(seen[1], mirrored)
    assert out.shape == (T, 17, 3)


def test_short_sequences_get_one_prediction_per_frame():
    assert lifting.lift(np.ones((5, 17, 2), np.float32), 640, 480, _Recorder()).shape == (5, 17, 3)


@pytest.mark.skipif(not os.path.isfile(ONNX), reason="ONNX model not downloaded")
def test_the_real_model_runs_on_cpu():
    pytest.importorskip("onnxruntime")
    sess = lifting.session(ONNX, device="cpu")
    x = np.random.default_rng(1).uniform(200, 800, size=(40, 17, 2)).astype(np.float32)
    out = lifting.lift(x, 1280, 720, sess)
    assert out.shape == (40, 17, 3) and np.isfinite(out).all()


def test_cpu_fallback_hint_names_the_cuda_13_boundary(monkeypatch):
    fake = types.SimpleNamespace(__version__="1.30.0",
                                 get_available_providers=lambda: ["CUDAExecutionProvider"])
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    assert "1.27" in onnx_gpu.cpu_fallback_hint()
    fake.get_available_providers = lambda: ["CPUExecutionProvider"]
    assert "CPU build" in onnx_gpu.cpu_fallback_hint()
