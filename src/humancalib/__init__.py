"""HumanCalib: multi-camera extrinsic calibration from human pose."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("humancalib")
except PackageNotFoundError:  # a source checkout that was never installed
    __version__ = "0+unknown"
