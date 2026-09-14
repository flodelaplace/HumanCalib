"""TOML loading for calibration files.

Single source of truth for reading Pose2Sim-style calibration TOMLs. This
replaces two byte-identical hand-rolled parsers that fell back to ``eval()``
on the file's values -- arbitrary code execution from a calibration file, which
is exactly the kind of artefact labs email to each other.
"""
try:  # Python 3.11+
    import tomllib
except ImportError:  # Python <= 3.10
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


def load_toml(path):
    """Read a TOML file and return it as a dict.

    Raises:
        RuntimeError: if no TOML parser is available.
        tomllib.TOMLDecodeError: if the file is not valid TOML.
    """
    if tomllib is None:
        raise RuntimeError(
            "No TOML parser available. Python 3.11+ provides tomllib in the "
            "standard library; on 3.10 and older, install tomli "
            "(`pip install tomli`). It is pinned in envs/calib.yaml and "
            "envs/rtmpose.yaml, so this usually means the environment is not "
            "active."
        )
    with open(path, "rb") as f:
        return tomllib.load(f)
