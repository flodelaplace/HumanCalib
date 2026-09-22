# Changelog

## 0.2.0 — 2026-09-22

The defaults now run the method evaluated against five laboratory calibrations
(see [Validation](README.md#validation)).

**Changed defaults**
- `--pose_engine metrabs` (was `rtmpose` outside Docker). Pass `--pose_engine rtmpose` for the
  optional backend.
- `--person_selection motion`: the walking person, then geometric re-selection (was `geometric`).
- `--scale_method stature`: with MeTRAbs, the head-band height above the floor over the walk,
  against 0.9255 × `--height` (was thigh + shank against 0.491 × `--height`). Median scale error
  on four held-out datasets: 1.0 % instead of 1.9 %. RTMPose keeps the segment rule.

**Added**
- Person selection: `geometric` re-selection and `motion` (walking-person) selection.
- Whole-walk vertical (`--vertical_method walk`) and segment-based scale (`--scale_method segments`).
- Evaluation tooling against laboratory calibrations (`humancalib.evaluation`) for BioCV,
  IMOVE-23, OpenCap, LBMC and COMFI.
- Documentation: `docs/METHOD.md`, `docs/TROUBLESHOOTING.md`, a shorter README.

## 0.1.0 — 2026-09-14

First packaged release: `humancalib` command and package, pinned conda environments,
Docker images, CPU test suite with CI, analytic bundle-adjustment Jacobian.
