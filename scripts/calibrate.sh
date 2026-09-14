#!/bin/bash
# scripts/calibrate.sh -- compatibility shim.
#
# The pipeline is `humancalib run`, in src/humancalib/cli.py. This file only
# forwards to it, so every command in HOWTO.md keeps working exactly as written:
# same arguments, and relative paths still resolved from the repository root,
# because this script has always changed into it before reading them.
#
# All logic lives in Python now, where the test suite can reach it. Before, the
# pose-cache check, the frame mapping, the MRE comparison and the camera naming
# were shell or Python heredocs that no test could exercise -- and two of them
# were wrong (see B8 and the misleading final summary in docs/REFACTOR_PLAN.md).
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"
export PYTHONPATH="${REPO_ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}"
# HUMANCALIB_PYTHON pins an absolute interpreter (a bare python3 resolves to
# whichever conda environment is active).
exec "${HUMANCALIB_PYTHON:-python3}" -m humancalib.cli run "$@"
