"""Logging: the output must look the same, and must not silently disappear.

The pipeline's printed output is its interface, so switching 262 print() calls
to logging is only acceptable if INFO still reaches stdout undecorated and
problems still reach stderr. The less obvious risk is losing messages entirely:
a module run as `python -m ...` is named "__main__", outside the configured
logger hierarchy, and every INFO it logs would vanish without a trace.
"""
import ast
import glob
import logging
import os
import subprocess
import sys

import pytest

from humancalib.core import log as hlog

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _isolated_logging(monkeypatch):
    monkeypatch.delenv(hlog.ENV_VAR, raising=False)
    yield
    root = logging.getLogger(hlog.ROOT)
    for h in [h for h in root.handlers if getattr(h, "_humancalib", False)]:
        root.removeHandler(h)


def test_info_reaches_stdout_undecorated_and_problems_reach_stderr(capsys):
    hlog.setup_logging("INFO")
    logger = hlog.get_logger("humancalib.test")
    logger.info("  -> Global MRE: 4.034 pixels")
    logger.warning("frame size differs across cameras")
    logger.error("linear calibration result not found")

    out, err = capsys.readouterr()
    assert out == "  -> Global MRE: 4.034 pixels\n"
    assert err == ("WARNING: frame size differs across cameras\n"
                   "ERROR: linear calibration result not found\n")


def test_quiet_keeps_only_problems(capsys):
    hlog.setup_logging("WARNING")
    logger = hlog.get_logger("humancalib.test")
    logger.info("progress")
    logger.warning("problem")
    out, err = capsys.readouterr()
    assert out == "" and err == "WARNING: problem\n"


def test_the_level_is_exported_for_child_processes():
    hlog.setup_logging(logging.DEBUG)
    assert os.environ[hlog.ENV_VAR] == "DEBUG"


def test_every_logger_lands_under_the_configured_hierarchy():
    assert hlog.get_logger("humancalib.pipeline.run_ba").name == "humancalib.pipeline.run_ba"
    assert hlog.get_logger("somewhere").name == "humancalib.somewhere"
    assert hlog.get_logger("__main__").name.startswith("humancalib.")


def test_a_step_run_as_a_module_still_reports_its_errors(tmp_path):
    """The `python -m` case: the message must reach stderr, not vanish."""
    env = dict(os.environ, PYTHONPATH=os.path.join(REPO, "src"))
    env.pop(hlog.ENV_VAR, None)
    result = subprocess.run(
        [sys.executable, "-m", "humancalib.pipeline.write_session",
         "--output_dir", str(tmp_path), "--subset", "s", "--video_dir", str(tmp_path),
         "--aid", "1", "--pid", "1", "--gid", "1"],
        capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert "ERROR:" in result.stderr and "not found" in result.stderr
    assert "ERROR: ERROR" not in result.stderr, "level prefix doubled"


def test_no_print_calls_remain_outside_program_output():
    """print() bypasses levels, --quiet and redirection. Only the CLI's own
    --help and --version text, which is requested output, may use it."""
    offenders = []
    for path in glob.glob(os.path.join(REPO, "src", "humancalib", "**", "*.py"), recursive=True):
        tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "print":
                src = ast.unparse(node)
                if path.endswith("cli.py") and ("_usage()" in src or "__version__" in src):
                    continue
                offenders.append(f"{os.path.relpath(path, REPO)}:{node.lineno}")
    assert not offenders, offenders
