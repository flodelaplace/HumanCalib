"""The CI environment must not drift away from the real one.

envs/ci.yaml exists because installing 2.8 GB of CUDA on a CPU-only runner to
run tests that never import TensorFlow is wasteful. The cost of that decision is
a second list of pins, and a second list of pins is a thing that silently rots:
someone bumps scipy in one file, CI keeps testing the old one, and the suite
stops saying anything about what people actually install.

This test makes that impossible. It says nothing about which packages CI
carries -- only that where the two files agree to name a package, they must
agree on its version.
"""
import os
import re

import pytest
import yaml

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _pins(path):
    """{package: version} for both the conda list and the nested pip list."""
    with open(os.path.join(_REPO, path)) as f:
        doc = yaml.safe_load(f)

    pins = {}
    for entry in doc["dependencies"]:
        if isinstance(entry, str):
            name, _, version = entry.partition("=")
            if version:
                pins[name.strip().lower()] = version.strip()
        elif isinstance(entry, dict):
            for req in entry.get("pip", []):
                m = re.match(r"^([A-Za-z0-9._-]+)\s*==\s*(.+)$", req.strip())
                if m:
                    pins[m.group(1).lower()] = m.group(2).strip()
    return pins


def test_shared_pins_are_identical():
    main = _pins("envs/calib.yaml")
    ci = _pins("envs/ci.yaml")

    shared = sorted(set(main) & set(ci))
    assert shared, "the two environment files share no pinned package at all"

    mismatched = {p: (main[p], ci[p]) for p in shared if main[p] != ci[p]}
    assert not mismatched, (
        "envs/ci.yaml has drifted from envs/calib.yaml: "
        + ", ".join(f"{p} is {a} vs {b}" for p, (a, b) in mismatched.items())
    )


@pytest.mark.parametrize("package", ["numpy", "scipy", "opencv-contrib-python",
                                     "pycalib-simple", "pytest"])
def test_ci_carries_what_the_tests_import(package):
    """A package the suite needs must not be dropped from CI by accident."""
    assert package in _pins("envs/ci.yaml")


def test_ci_does_not_carry_the_gpu_stack():
    """If this ever fails, CI jobs just got gigabytes slower for no benefit."""
    ci = _pins("envs/ci.yaml")
    for heavy in ("cudatoolkit", "cudnn", "tensorflow", "jaxlib"):
        assert heavy not in ci, f"{heavy} does not belong in the CI environment"


def test_only_one_opencv_distribution_anywhere():
    """opencv-python and opencv-contrib-python share a cv2/ directory.

    Installing both leaves two dist-info records and one set of files: whichever
    installed last wins, silently. This is why pycalib's own dependency on the
    pair has to be neutralised.
    """
    for path in ("envs/calib.yaml", "envs/ci.yaml", "envs/rtmpose.yaml"):
        pins = _pins(path)
        assert "opencv-python" not in pins, f"{path} pulls a second cv2"
        assert "opencv-contrib-python" in pins, f"{path} pins no opencv at all"
