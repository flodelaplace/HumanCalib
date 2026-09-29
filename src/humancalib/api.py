"""Python API: calibrate from another program (e.g. Pose2Sim) without going through the shell.

    from humancalib import calibrate

    toml = calibrate("session/videos", "session/Calib_intrinsics.toml", "session/humancalib",
                     height=1.78)

It runs exactly ``humancalib run`` with the same defaults (the evaluated method) and returns
the path of the calibrated TOML, in Pose2Sim format.
"""
import os

__all__ = ["calibrate", "CalibrationError"]


class CalibrationError(RuntimeError):
    """The pipeline failed, or finished without writing the calibrated TOML."""


def calibrate(video_dir, intrinsics_toml, output_dir, height, *, ref_frame=None, device="cuda",
              pose_engine="metrabs", **options):
    """Calibrate the extrinsics of a multi-camera rig from a person walking in its view.

    Parameters
    ----------
    video_dir : str
        Folder of synchronised videos, one per camera. Their names (without extension) must
        match the sections of `intrinsics_toml`.
    intrinsics_toml : str
        Each camera's intrinsics, Pose2Sim format (the extrinsics in it are ignored).
    output_dir : str
        Where everything is written; poses are cached there, so a second call is fast.
    height : float
        The walking subject's height in metres. Sets the metric scale.
    ref_frame : int, optional
        Video frame with both heels visible, which sets the origin and horizontal axis.
        Chosen automatically by default.
    device : "cuda" or "cpu"
    pose_engine : "metrabs" (default, the evaluated method) or "rtmpose"
    **options
        Any other ``humancalib run`` option, by its name without dashes, e.g.
        ``extract_fps=25``, ``frame_budget=60``, ``start_frame=100``, ``person_selection="geometric"``.
        ``auto_outlier_drop=False`` gives ``--no_auto_outlier_drop``.

    Returns
    -------
    str
        Path of ``<output_dir>/results/Calib_scene_calibrated.toml``: metric, gravity-aligned
        (Z up), Pose2Sim format.

    Raises
    ------
    CalibrationError
        If a step fails or no calibrated TOML is produced.
    """
    import logging

    from humancalib.cli import PipelineError, parse_run_args, run_pipeline
    from humancalib.core.log import ROOT, setup_logging

    if not logging.getLogger(ROOT).handlers:     # show progress unless the caller set logging up
        setup_logging()

    argv = [os.fspath(video_dir), os.fspath(intrinsics_toml), os.fspath(output_dir),
            "--device", device, "--pose_engine", pose_engine, "--height", str(float(height))]
    if ref_frame is not None:
        argv += ["--ref_frame", str(int(ref_frame))]
    for name, value in options.items():
        if name == "auto_outlier_drop":
            if not value:
                argv.append("--no_auto_outlier_drop")
        elif value is True:
            argv.append(f"--{name}")
        elif value not in (None, False):
            argv += [f"--{name}", str(value)]
    try:
        cfg = parse_run_args(argv)
    except SystemExit as err:          # argparse rejects an unknown option or a bad value
        raise CalibrationError(f"invalid options {sorted(options)}") from err
    try:
        run_pipeline(cfg)
    except PipelineError as err:
        raise CalibrationError(str(err)) from err
    toml = os.path.join(cfg.output_dir, "results", "Calib_scene_calibrated.toml")
    if not os.path.isfile(toml):
        raise CalibrationError(f"the pipeline finished without writing {toml}; see the log above")
    return toml
