# Per-trial results of the article

**Calibrating markerless multi-camera motion capture from a single walk: accuracy against five
reference calibrations and effect on joint angles** (in preparation).

Results produced with HumanCalib v0.5 on 97 walking trials from five public datasets (BioCV,
I-MOVE-23, OpenCap, LBMC, COMFI): the 77 evaluation trials of the first submission, plus 20 trials of
participants never opened during development (I-MOVE-23 subjects 14-25; BioCV P19, P24, P26 and P27,
WALK_01 and WALK_02), flagged by the column `out_of_sample`. The rows of the 77 original trials are
unchanged from release 0.5.2. All files are comma-separated, with one header line. Angles are in
degrees and lengths in millimetres unless stated. Engines: HumanCalib-M (MeTRAbs) and HumanCalib-R
(RTMPose + VideoPose3D). Table and figure numbers refer to the first submission.

## Main evaluation

| File | Content |
|---|---|
| `calibrations_per_trial.csv` | one line per calibration (194): geometric metrics, scale, vertical, reprojection, acceptance, failure, induced reconstruction error (Table 2, Figs 3 and 5a, Supplementary Tables S1-S2). |
| `cameras.csv` | one line per camera (1 368): rotation after rig superposition, position after 7-DoF and 4-DoF alignment (Supplementary Fig. S4). |
| `camera_pairs.csv` | one line per camera pair (4 782): relative rotation, baseline direction error, ratio of our baseline to the reference baseline (pooled percentages in the Results). |
| `kinematics_rmsd_per_trial_dof.csv` | joint-angle RMSD between the Pose2Sim chain run with the reference calibration and with HumanCalib, per trial and degree of freedom (left and right pooled), for both engines (column `engine`); frame = own (each chain in its own frame, primary) or shared_with_reference (sensitivity) (Table 3, Fig. 4a, Supplementary Table S4). |
| `kinematics_vs_mocap.csv` | BioCV, I-MOVE-23 and OpenCap: RMSD of each chain's joint angles against the dataset's motion-capture kinematics, per trial, engine and OpenSim coordinate (one per side), after time alignment (`mocap_time_offset_s`). |
| `gait_spatiotemporal.csv` | stride length, walking speed and cadence from the chain run with the reference calibration, with HumanCalib and from motion capture, per trial and engine. |
| `comfi_angles_vs_mocap.csv` | COMFI joint-angle RMSD against the dataset's motion-capture kinematics, reference calibration vs HumanCalib (Fig. 4b). |
| `comfi_3d_vs_mocap.csv` | COMFI 3D error of triangulated keypoints against motion capture, reference calibration vs HumanCalib. |
| `comfi_3d_controls.csv` | same, with 2D detectors not used for the calibration, per-trial alignment and calibration from the other walk (Supplementary Table S5). |
| `walking_coverage.csv` | duration, extent, area and length of the walk, and how much of it each camera sees, per trial. |
| `scale_in_walking_volume.csv` | HumanCalib-M scale error measured on point pairs inside the walking volume, against the scale of the camera centres. |
| `development_trials.csv` | the 77 named trials opened while developing the method: used to develop the method (per engine), only to set the scale estimator, or only for diagnosis. Every other trial is development-free. |

## Sensitivity analyses

| File | Content |
|---|---|
| `walking_duration_sweep.csv` | calibration error for windows of 0.5 s to the full trial (Supplementary Table S3): the 10 trials of the first submission and the 20 out-of-sample trials. Short trials repeat no window: a trial shorter than the window is calibrated once, on its full length. Compute times of the out-of-sample trials were measured while another computation ran and are indicative only. |
| `criterion_perturbation.csv` | one camera rotated by 1-30 deg; acceptance decision without (readjusted = no) and with (yes) a new bundle adjustment (Fig. 5b, Supplementary Table S2). With re-adjustment, one camera per participant is perturbed (45 participants of the first submission, 16 out-of-sample participants). |
| `sensitivity_rig_conditions.csv` | HumanCalib-M calibration redone from the article's detections, with no new pose estimation, under degraded conditions. `camera_count`: random subsets of 2 to 8 cameras, 3 draws each (BioCV WALK_01, 9 trials; I-MOVE-23, 11 trials). `synchronisation`: one camera shifted by 1-16 frames at 200 Hz (BioCV). `intrinsics`: focal length scaled by 0.95-1.05 or principal point shifted by 10 or 30 px for all cameras (BioCV). Scored against the reference on the same cameras. With 2 cameras, the single pair is scored directly; `worst_pair_deg` is then the larger of its rotation and baseline-direction errors, and scale is undefined. The 7-DoF rig shape is left out with 3 cameras or fewer: it places each camera from a fit on the others, and with 2 remaining cameras the rotation about their baseline is free. |
| `scale_rule_grid.csv` | scale error of the head-to-floor rule for 36 settings (head and floor percentiles, number of frames), the constant refitted each time on the 18 original BioCV trials; evaluated on the 59 out-of-sample trials of the first submission and on 79 trials (59 + 20 new). |
| `rig_size_change_during_adjustment.csv` | change of the mean distance between cameras from the linear stage to the end of bundle adjustment, per HumanCalib-M calibration. |
| `stature_sensitivity.csv` | scale error of the 97 HumanCalib-M calibrations when the stature given is off by -3 to +3 cm, or measured with shoes (+2.5 cm). |

## Simulated pathological gait (OpenCap trunk sway)

The 9 OpenCap participants also walked while swaying their trunk laterally (walkingTS, 3 trials
each). These 27 trials were processed with HumanCalib v0.5.2, unchanged, and are compared with the 18
natural walks of the same participants (`gait` = trunk_sway or natural).

| File | Content |
|---|---|
| `trunk_sway_amplitude.csv` | lateral trunk lean (pelvis to C7, from motion capture) and walking speed, per trial. |
| `trunk_sway_calibrations.csv` | one line per calibration and engine: geometric metrics, scale, vertical, reprojection, acceptance. |
| `trunk_sway_kinematics.csv` | joint-angle RMSD between the chain run with the reference calibration and with HumanCalib (own frame), per trial, engine and degree of freedom. |
| `trunk_sway_kinematics_vs_mocap.csv` | RMSD of each chain against motion capture, per trial, engine and coordinate. |
| `trunk_sway_gait_spatiotemporal.csv` | stride length, speed and cadence, per trial and engine. |

These files contain derived metrics only: no video, no 2D or 3D keypoints, no motion-capture
markers and no element of the datasets' reference calibrations. The datasets themselves are
distributed by their authors under their own terms; their references are listed in the
[main README](../../README.md#datasets-of-the-evaluation).

## Licence

The data in this folder are released under the
[Creative Commons Attribution 4.0 International licence (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/).
The code of the repository remains under the MIT licence. Please cite the archived release
(concept DOI [10.5281/zenodo.23143081](https://doi.org/10.5281/zenodo.23143081)) and the article.
