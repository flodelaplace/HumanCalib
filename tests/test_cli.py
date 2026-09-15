"""The Python CLI that replaced calibrate.sh.

Acceptance for this change was that every command documented in HOWTO.md keeps
working exactly as written. The three commands are parsed here verbatim, so
that promise is checked rather than remembered.
"""
import os
import sys

import pytest

from humancalib import cli

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --- HOWTO.md, verbatim ------------------------------------------------------------------

def test_howto_metrabs_command():
    cfg = cli.parse_run_args(["demo", "demo/Calib_scene.toml", "output/demo_metrabs",
                              "cuda", "balanced", "--pose_engine", "metrabs",
                              "--height", "1.78", "--ref_frame", "5"])
    assert cfg.video_dir == os.path.abspath("demo")
    assert cfg.output_dir == os.path.abspath("output/demo_metrabs")
    assert (cfg.device, cfg.mode, cfg.pose_engine) == ("cuda", "balanced", "metrabs")
    assert (cfg.height, cfg.ref_frame) == (1.78, 5)
    assert (cfg.frame_skip, cfg.conf_threshold, cfg.ba_jac) == (10, 0.5, "analytic")
    assert cfg.auto_outlier_drop is True
    assert cfg.start_frame is None and cfg.end_frame is None


def test_howto_rtmpose_command_keeps_the_historical_default_engine(monkeypatch):
    monkeypatch.delenv("HUMANCALIB_DEFAULT_ENGINE", raising=False)
    cfg = cli.parse_run_args(["demo", "demo/Calib_scene.toml", "output/demo_rtmpose",
                              "cuda", "balanced", "--height", "1.78", "--ref_frame", "5"])
    assert cfg.pose_engine == "rtmpose"


def test_howto_real_world_command():
    cfg = cli.parse_run_args(["input/my_session", "input/my_session/Calib_scene.toml",
                              "output/my_session", "cuda", "balanced",
                              "--pose_engine", "metrabs", "--start_frame", "650",
                              "--end_frame", "1500", "--ref_frame", "1415",
                              "--height", "1.84", "--frame_skip", "5"])
    assert (cfg.start_frame, cfg.end_frame, cfg.ref_frame) == (650, 1500, 1415)
    assert (cfg.height, cfg.frame_skip) == (1.84, 5)


# --- command-line compatibility details --------------------------------------------------

def test_each_docker_image_can_declare_its_own_default_engine(monkeypatch):
    """Omitting --pose_engine must pick the backend the image actually contains."""
    monkeypatch.setenv("HUMANCALIB_DEFAULT_ENGINE", "metrabs")
    assert cli.parse_run_args(["v", "c.toml", "o"]).pose_engine == "metrabs"
    monkeypatch.setenv("HUMANCALIB_DEFAULT_ENGINE", "nonsense")
    assert cli.parse_run_args(["v", "c.toml", "o"]).pose_engine == "rtmpose"
    assert cli.parse_run_args(["v", "c.toml", "o", "--pose_engine", "metrabs"]).pose_engine == "metrabs"


def test_bare_device_and_mode_words_are_accepted_anywhere_after_the_paths():
    cfg = cli.parse_run_args(["v", "c.toml", "o", "--frame_skip", "5", "performance", "cpu"])
    assert (cfg.device, cfg.mode, cfg.frame_skip) == ("cpu", "performance", 5)


def test_a_trailing_carriage_return_does_not_break_a_number():
    cfg = cli.parse_run_args(["v", "c.toml", "o", "--height", "1.78\r"])
    assert cfg.height == 1.78


def test_outlier_drop_can_be_disabled():
    assert cli.parse_run_args(["v", "c.toml", "o", "--no_auto_outlier_drop"]).auto_outlier_drop is False


def test_output_dir_is_optional():
    cfg = cli.parse_run_args(["v", "c.toml", "cpu"])
    assert os.path.basename(os.path.dirname(cfg.output_dir)) == "data"
    assert os.path.basename(cfg.output_dir).startswith("session_")
    assert cfg.device == "cpu"


def test_an_unknown_option_is_refused():
    with pytest.raises(SystemExit):
        cli.parse_run_args(["v", "c.toml", "o", "--hieght", "1.78"])


# --- behaviour --------------------------------------------------------------------------

@pytest.mark.parametrize("ref,start,end,expected", [
    (5, None, None, 5),
    (1415, 650, 1500, 765),
    (700, 650, None, 50),
    (600, 650, 1500, None),
    (1600, 650, 1500, None),
])
def test_reference_frame_is_mapped_into_the_cropped_range(ref, start, end, expected):
    assert cli.map_ref_frame(ref, start, end) == expected


def test_best_calibration_is_the_lowest_mre_and_the_earlier_stage_on_a_tie():
    assert cli.best_calibration({"linear_1_0": 8.21, "linear_1_0_ba": 4.06}) == "linear_1_0_ba"
    assert cli.best_calibration({"linear_1_0": 4.0, "linear_1_0_ba": 4.0}) == "linear_1_0"
    assert cli.best_calibration({}) is None


def test_summary_does_not_claim_a_toml_that_was_never_written(tmp_path):
    """calibrate.sh announced a final TOML even when scaling had been skipped."""
    text = cli.format_summary({"linear_1_0_ba": 4.0}, "linear_1_0_ba", str(tmp_path), True)
    assert "Final TOML file generated" not in text
    assert "produced no final TOML" in text

    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "Calib_scene_calibrated.toml").write_text("")
    assert "Final TOML file generated" in cli.format_summary(
        {"linear_1_0_ba": 4.0}, "linear_1_0_ba", str(tmp_path), True)


def test_a_step_that_exits_with_an_error_fails_the_pipeline_by_name():
    def step(argv):
        sys.exit(1)
    with pytest.raises(cli.PipelineError, match="'demo-step'"):
        cli.run_step("demo-step", step, [])


def test_a_clean_exit_is_not_a_failure_and_return_values_pass_through():
    def exits_zero(argv):
        sys.exit(0)
    assert cli.run_step("x", exits_zero, []) is None
    assert cli.run_step("x", lambda argv: 4.25, []) == 4.25


def test_preflight_names_the_missing_input(tmp_path):
    cfg = cli.parse_run_args([str(tmp_path / "nope"), str(tmp_path / "c.toml"), str(tmp_path / "o"),
                              "--pose_engine", "metrabs"])
    with pytest.raises(cli.PipelineError, match="video directory not found"):
        cli.preflight(cfg)


def test_preflight_points_rtmpose_users_to_metrabs_when_the_backend_is_absent(tmp_path, monkeypatch):
    monkeypatch.delenv("HUMANCALIB_DEFAULT_ENGINE", raising=False)
    (tmp_path / "v").mkdir()
    (tmp_path / "v" / "cam01.mp4").write_bytes(b"")
    (tmp_path / "c.toml").write_text("")
    monkeypatch.setattr(cli.importlib.util, "find_spec", lambda name: None)
    cfg = cli.parse_run_args([str(tmp_path / "v"), str(tmp_path / "c.toml"), str(tmp_path / "o")])
    with pytest.raises(cli.PipelineError, match="--pose_engine metrabs"):
        cli.preflight(cfg)


# --- environment for the separate processes ----------------------------------------------

def test_metrabs_runs_in_the_current_interpreter_by_default():
    launcher = cli.resolve_metrabs_launcher(environ={}, which=lambda _: None)
    assert launcher == [sys.executable, "-u"]


def test_a_metrabs_opensim_environment_is_used_only_if_it_exists():
    has = cli.resolve_metrabs_launcher(environ={}, which=lambda _: "/usr/bin/conda",
                                       conda_env_names=lambda: {"base", "metrabs_opensim"})
    lacks = cli.resolve_metrabs_launcher(environ={}, which=lambda _: "/usr/bin/conda",
                                         conda_env_names=lambda: {"base"})
    assert has[:5] == ["conda", "run", "--live-stream", "-n", "metrabs_opensim"]
    assert lacks == [sys.executable, "-u"]


def test_the_metrabs_launcher_can_be_overridden():
    launcher = cli.resolve_metrabs_launcher(
        environ={"HUMANCALIB_METRABS_PYTHON": "/opt/conda/envs/humancalib/bin/python -u"})
    assert launcher == ["/opt/conda/envs/humancalib/bin/python", "-u"]


def test_child_processes_import_this_same_package():
    env = cli.child_env(environ={"PYTHONPATH": "/elsewhere"}, isdir=lambda _: False,
                        exists=lambda _: False)
    assert env["PYTHONPATH"].split(os.pathsep) == [str(cli.package_root()), "/elsewhere"]
    assert "LD_LIBRARY_PATH" not in env


def test_the_wsl_driver_path_is_added_only_where_it_exists():
    env = cli.child_env(environ={"LD_LIBRARY_PATH": "/opt/lib"}, isdir=lambda _: True,
                        exists=lambda _: False)
    assert env["LD_LIBRARY_PATH"] == os.pathsep.join(["/usr/lib/wsl/lib", "/opt/lib"])


def test_the_environments_cuda_runtime_reaches_the_gpu_steps(tmp_path):
    """conda activation does not put it on the loader path; the CLI must."""
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "libcudart.so.11.0").write_bytes(b"")
    lib = str(tmp_path / "lib")

    env = cli.child_env(environ={}, isdir=lambda _: False, prefix=str(tmp_path), torch_lib="")
    assert env["LD_LIBRARY_PATH"] == lib

    again = cli.child_env(environ={"LD_LIBRARY_PATH": lib}, isdir=lambda _: False, prefix=str(tmp_path), torch_lib="")
    assert again["LD_LIBRARY_PATH"] == lib, "added twice"


def test_pytorchs_bundled_cudnn_reaches_the_gpu_steps(tmp_path):
    """onnxruntime needs cuDNN, which PyTorch keeps inside its own package."""
    env_lib = tmp_path / "env" / "lib"
    env_lib.mkdir(parents=True)
    (env_lib / "libcudart.so.11.0").write_bytes(b"")
    torch_lib = tmp_path / "torch" / "lib"
    torch_lib.mkdir(parents=True)
    (torch_lib / "libcudnn.so.8").write_bytes(b"")

    env = cli.child_env(environ={}, isdir=lambda _: False,
                        prefix=str(tmp_path / "env"), torch_lib=str(torch_lib))
    assert env["LD_LIBRARY_PATH"].split(os.pathsep) == [str(env_lib), str(torch_lib)]


def test_empty_loader_path_entries_are_dropped():
    """An empty entry would make the loader search the current directory."""
    env = cli.child_env(environ={"LD_LIBRARY_PATH": "/a::/b:"}, isdir=lambda _: False,
                        exists=lambda _: False)
    assert env["LD_LIBRARY_PATH"] == os.pathsep.join(["/a", "/b"])


def test_no_cuda_runtime_means_the_loader_path_is_left_alone(tmp_path):
    env = cli.child_env(environ={}, isdir=lambda _: False, prefix=str(tmp_path), torch_lib="")
    assert "LD_LIBRARY_PATH" not in env


def test_gpu_steps_run_on_their_own_even_when_invoked_alone(monkeypatch):
    """`humancalib extract-metrabs` must not import TensorFlow in-process."""
    seen = {}

    def fake_call(cmd, env=None, cwd=None):
        seen.update(cmd=cmd, env=env)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    assert cli.main(["extract-metrabs", "--help"]) == 0
    assert seen["cmd"][1:3] == ["-m", "humancalib.pose.metrabs_inference"]
    assert "PYTHONPATH" in seen["env"]


# --- the shim --------------------------------------------------------------------------

def test_calibrate_sh_is_only_a_forwarder():
    """Logic in the shell script is logic no test can reach."""
    with open(os.path.join(REPO, "scripts", "calibrate.sh")) as f:
        code = [l for l in f if l.strip() and not l.lstrip().startswith("#")]
    assert any("-m humancalib.cli run" in l for l in code)
    assert len(code) <= 10, f"calibrate.sh has grown back to {len(code)} lines of code"


def test_method_v3_is_the_default():
    """Geometric person selection, leg-segment scale and whole-walk vertical: the
    methods validated against BioCV's lab calibration (docs/EVALUATION_PROTOCOL.md)."""
    cfg = cli.parse_run_args(["videos", "calib.toml"])
    assert (cfg.person_selection, cfg.scale_method, cfg.vertical_method) == ("geometric", "segments", "walk")
