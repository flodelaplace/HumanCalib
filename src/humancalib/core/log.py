"""Logging for HumanCalib.

The pipeline's printed output is its user interface -- banners, tables,
progress -- so this configuration keeps it looking exactly as it did when every
line was a print(): INFO goes to stdout with no decoration, WARNING and above go
to stderr prefixed with their level. What logging adds is control. `--quiet`
shows only problems, `--verbose` adds DEBUG detail, and library use -- tests, a
notebook -- prints nothing unless it asks.

HUMANCALIB_LOG_LEVEL carries the chosen level into the steps that run in their
own process, so `humancalib run --quiet` is quiet all the way down.

Use in a module:

    from humancalib.core.log import get_logger
    log = get_logger(__name__)
"""
import logging
import os
import sys

ENV_VAR = "HUMANCALIB_LOG_LEVEL"
ROOT = "humancalib"


class _Below(logging.Filter):
    """Pass only records below a level, so stdout never repeats a warning."""

    def __init__(self, level):
        super().__init__()
        self.level = level

    def filter(self, record):
        return record.levelno < self.level


def get_logger(name):
    """Logger under the `humancalib` hierarchy, whatever `name` is.

    `__name__` is "__main__" when a step runs as `python -m humancalib...`; a
    logger of that name would sit outside the configured hierarchy and every
    INFO message would silently vanish. The module's real name is recovered
    from its import spec instead.
    """
    if name == "__main__":
        spec = getattr(sys.modules.get("__main__"), "__spec__", None)
        name = spec.name if spec is not None and spec.name else f"{ROOT}.__main__"
    if name != ROOT and not name.startswith(ROOT + "."):
        name = f"{ROOT}.{name}"
    return logging.getLogger(name)


def _level(value):
    if isinstance(value, int):
        return value
    resolved = logging.getLevelName(str(value).upper())
    return resolved if isinstance(resolved, int) else logging.INFO


def setup_logging(level=None):
    """Configure the `humancalib` logger for a command-line run.

    Args:
        level: int or level name; None reads HUMANCALIB_LOG_LEVEL, then INFO.

    Returns:
        The effective level. It is also exported to the environment, so child
        processes started afterwards inherit it.
    """
    level = _level(os.environ.get(ENV_VAR, "INFO") if level is None else level)
    logger = logging.getLogger(ROOT)
    for handler in [h for h in logger.handlers if getattr(h, "_humancalib", False)]:
        logger.removeHandler(handler)

    out = logging.StreamHandler(sys.stdout)
    out.setFormatter(logging.Formatter("%(message)s"))
    out.addFilter(_Below(logging.WARNING))

    err = logging.StreamHandler(sys.stderr)
    err.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    err.setLevel(logging.WARNING)

    for handler in (out, err):
        handler._humancalib = True
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    os.environ[ENV_VAR] = logging.getLevelName(level)
    return level
