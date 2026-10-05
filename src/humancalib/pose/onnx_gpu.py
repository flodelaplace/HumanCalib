"""onnxruntime on the GPU, for the RTMPose backend (rtmlib's 2D models, VideoPose3D).

onnxruntime-gpu finds CUDA and cuDNN on the loader path, or, from version 1.21, in the nvidia-*
pip wheels once `onnxruntime.preload_dlls()` has loaded them. Those wheels are what
`tensorflow[and-cuda]` (the `gpu` extra) installs, for CUDA 12: onnxruntime-gpu up to 1.26 uses
CUDA 12 and shares them, from 1.27 it needs CUDA 13 and its own (`onnxruntime-gpu[cuda,cudnn]`).
Each of these runs in its own process, never in TensorFlow's: loading two sets of CUDA libraries
into one process can leave one of them without a GPU.
"""


def preload_cuda_libraries():
    """Load CUDA/cuDNN from the nvidia-* pip wheels, if this onnxruntime can (>= 1.21)."""
    try:
        import onnxruntime as ort
        if hasattr(ort, "preload_dlls"):
            ort.preload_dlls()
    except Exception:       # missing wheels or libraries: the CPU fallback is reported later
        pass


def cpu_fallback_hint():
    """What to check when onnxruntime falls back to the CPU."""
    try:
        import onnxruntime as ort
        version = ort.__version__
    except Exception:
        return "onnxruntime is not installed."
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        return (f"This is the CPU build of onnxruntime ({version}): pip uninstall onnxruntime, "
                'then pip install "onnxruntime-gpu<1.27".')
    major_minor = tuple(int(x) for x in version.split(".")[:2])
    if major_minor >= (1, 27):
        return (f"onnxruntime-gpu {version} needs CUDA 13: pip install \"onnxruntime-gpu<1.27\" to "
                "use the CUDA 12 libraries of humancalib[gpu], or pip install "
                '"onnxruntime-gpu[cuda,cudnn]" for its own.')
    return (f"onnxruntime-gpu {version} needs CUDA 12 and cuDNN 9: pip install \"humancalib[gpu]\" "
            "on Linux provides them, or put a system CUDA 12 on the loader path.")
