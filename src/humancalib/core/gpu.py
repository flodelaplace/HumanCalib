"""GPU selection helper used by the inference scripts."""
import os

import nvgpu
import torch
from humancalib.core.log import get_logger
log = get_logger(__name__)


def select_gpu(i_selected_gpu=None):
    """Pick a GPU with free memory and set CUDA_VISIBLE_DEVICES accordingly.

    If `i_selected_gpu` is given, just sets that one. Otherwise, scans all
    visible GPUs (in reverse order) and picks the first one with mem_used < 18
    MiB; if none is free, falls back to the GPU with the most unused memory.

    An allocation made by the surrounding runtime wins over the automatic
    scan: if CUDA_VISIBLE_DEVICES is already set in the environment, and no
    explicit `i_selected_gpu` was requested, this function leaves it alone.
    Overwriting it used to break every context that hands out devices from the
    outside -- `docker run --gpus '"device=1"'`, Slurm's --gres=gpu, a job
    scheduler pinning one card per task -- because the index chosen here counts
    against the *already filtered* list, so writing "0" back could point at a
    different physical card, or at one the job was never allocated. Set
    CUDA_VISIBLE_DEVICES="" to force CPU.
    """
    external = os.environ.get("CUDA_VISIBLE_DEVICES")

    if i_selected_gpu is not None:
        if external is not None and external != f"{i_selected_gpu}":
            log.warning(f"overriding CUDA_VISIBLE_DEVICES={external} with "
                f"{i_selected_gpu} as explicitly requested. The index is read "
                f"against the full device list, not the allocated subset.")
        os.environ["CUDA_VISIBLE_DEVICES"] = f"{i_selected_gpu}"
        log.info(f"CUDA_VISIBLE_DEVICES={i_selected_gpu}")
        return

    if external is not None:
        log.info(f"CUDA_VISIBLE_DEVICES={external} (set by the environment, kept)")
        return

    unused_max = 0
    is_free_gpu = False
    gpu_info = []
    try:
        gpu_info = nvgpu.gpu_info()
    except Exception:
        # This caught BaseException, which includes KeyboardInterrupt and
        # SystemExit: Ctrl+C during GPU probing printed a traceback and the run
        # carried on as if nothing had happened.
        log.warning("GPU probing with nvgpu failed; falling back to device 0.", exc_info=True)

    unused_i_gpu = 0
    for i_gpu, gpu in reversed(list(enumerate(gpu_info))):
        unused = gpu["mem_total"] - gpu["mem_used"]
        if unused > unused_max:
            unused_i_gpu = i_gpu
            unused_max = unused
        # use this gpu
        if gpu["mem_used"] < 18:
            i_selected_gpu = i_gpu
            is_free_gpu = True
            break
    # There is no free GPU, use less used one.
    if i_selected_gpu is None:
        i_selected_gpu = unused_i_gpu
    os.environ["CUDA_VISIBLE_DEVICES"] = f"{i_selected_gpu}"
    log.info(f"CUDA_VISIBLE_DEVICES={i_selected_gpu}, is_free:{is_free_gpu}")
    # using flag
    if is_free_gpu:
        torch.zeros(2 * 10**4, dtype=torch.float64).cuda()
