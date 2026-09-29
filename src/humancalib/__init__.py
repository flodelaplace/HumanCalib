"""HumanCalib: multi-camera extrinsic calibration from human pose."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("humancalib")
except PackageNotFoundError:  # a source checkout that was never installed
    __version__ = "0+unknown"


def __getattr__(name):
    # `from humancalib import calibrate` without importing the whole pipeline at package import
    if name in ("calibrate", "CalibrationError"):
        from humancalib import api
        return getattr(api, name)
    raise AttributeError(f"module 'humancalib' has no attribute {name!r}")
