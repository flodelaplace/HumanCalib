"""Shared test setup.

The pipeline is still a collection of scripts rather than an installed package
(that is Phase 6), so the repository root has to be importable for `core`,
`calibration` and `postprocessing` to resolve.
"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
