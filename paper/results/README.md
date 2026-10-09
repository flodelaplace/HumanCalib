# Per-trial results of the article

**Calibrating markerless multi-camera motion capture from a single walk: accuracy against five
reference calibrations and effect on joint angles** (in preparation).

Results produced with HumanCalib v0.5, on 77 walking trials from five public datasets (BioCV,
I-MOVE-23, OpenCap, LBMC, COMFI). All files are comma-separated, with one header line. Angles are in
degrees and lengths in millimetres unless stated. Engines: HumanCalib-M (MeTRAbs) and HumanCalib-R
(RTMPose + VideoPose3D).

| File | Content |
|---|---|
| `calibrations_per_trial.csv` | one line per calibration (154): geometric metrics, scale, vertical, reprojection, acceptance, failure, induced reconstruction error (Table 2, Figs 3 and 5a, Supplementary Tables S1-S2). |
| `cameras.csv` | one line per camera (984): rotation after rig superposition, position after 7-DoF and 4-DoF alignment (Supplementary Fig. S4). |
| `camera_pairs.csv` | one line per camera pair (3 126): relative rotation, baseline direction error, ratio of our baseline to the reference baseline (pooled percentages in the Results). |
| `kinematics_rmsd_per_trial_dof.csv` | joint-angle RMSD between the chain run with the reference calibration and with HumanCalib, per trial and degree of freedom; frame = own (each chain in its own frame, primary) or shared_with_reference (sensitivity) (Table 3, Fig. 4a, Supplementary Table S4). |
| `comfi_angles_vs_mocap.csv` | COMFI joint-angle RMSD against the dataset's motion-capture kinematics, reference calibration vs HumanCalib (Fig. 4b). |
| `comfi_3d_vs_mocap.csv` | COMFI 3D error of triangulated keypoints against motion capture, reference calibration vs HumanCalib. |
| `comfi_3d_controls.csv` | same, with 2D detectors not used for the calibration, per-trial alignment and calibration from the other walk (Supplementary Table S5). |
| `walking_duration_sweep.csv` | calibration error for windows of 0.5 s to the full trial (Supplementary Table S3). |
| `criterion_perturbation.csv` | one camera rotated by 1-30 deg; acceptance decision, without (readjusted = no) and with (yes) a new bundle adjustment (Fig. 5b, Supplementary Table S2). |

These files contain derived metrics only: no video, no 2D or 3D keypoints, no motion-capture
markers and no element of the datasets' reference calibrations. The datasets themselves are
distributed by their authors under their own terms.

## Licence

The data in this folder are released under the
[Creative Commons Attribution 4.0 International licence (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
The code of the repository remains under the MIT licence. Please cite the archived release
(concept DOI [10.5281/zenodo.23143081](https://doi.org/10.5281/zenodo.23143081)) and the article.
