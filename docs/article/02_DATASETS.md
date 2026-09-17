# 02 — Jeux de données et calibrations de référence

Cinq situations, choisies pour couvrir les cas d'usage : labo moyen, grand volume,
smartphones proches, tapis roulant, webcams. Toutes les données sont sous
`D:\FLO\DATASET MARKERLESS\` ; chaque lecteur est dans `src/humancalib/evaluation/`.

| Jeu | Situation | Caméras | Référence (gold) | Participants × essais utilisés | Lecteur |
|---|---|---|---|---|---|
| **BioCV** | labo de biomécanique | 9 × 1920×1080, 200 Hz, synchro matérielle | mocap-alignée, par participant | 9 × 2 marches (WALK_01/02) | `biocv.py` |
| **IMOVE-23** | grand couloir, 10 caméras | 10 Miqus 1080p, 100 Hz (2 en portrait) | Qualisys XML par sujet | 11 sujets × 1 aller-retour | `imove.py` |
| **OpenCap** | 5 iPhones en arc serré | 5 × 720×1280 portrait, 60 Hz, **pas de synchro matérielle** | damier, intrinsèques génériques du modèle d'iPhone | 9 sujets × 1 marche naturelle | `opencap.py` |
| **LBMC** | tapis roulant | 9 Miqus portrait 1088×1920, 60 Hz | Qualisys wand (résidu 0,19 mm), **un seul rig** | 2 participants × marche | `lbmc.py` |
| **COMFI** (LAAS-CNRS, Toulouse) | marche circulaire, 4 webcams 1280×720 à 40 Hz | **À FAIRE** : dossier caméras et marqueurs en cours de réception | 18 participants | à écrire |

La démo Pose2Sim (4 Qualisys, 100 images, sujet sur une poutre) a été calculée mais
**écartée** : pas de marche, stature inconnue (03 §9).

## Références cinématiques (pour le niveau 2, angles)

Déjà calculées pour l'article Mesh2Sim, dans `_EXPORT_ARTICLE/gold/<dataset>/`
(voir son `LISEZMOI.md`) :

| Jeu | Fichier de référence | Fréquence | Fenêtres |
|---|---|---|---|
| BioCV | `<P>/<WALK>/ik_gold_modele_bath.mot` (modèle du jeu) et `ik_gold_modele_mesh2sim.mot` ; `markers.c3d` | 200 Hz | `IK_WINDOWS.csv`, `RELIABLE_WINDOWS.csv` (marqueurs complets, ~50 % de l'essai) |
| OpenCap | `<sujet>/<essai>/ik_mocap.mot`, `marqueurs_mocap.trc` | mocap | fenêtre courte du clip synchronisé |
| IMOVE-23 | `<sujet>/ik_session_marche.mot` (Rajagopal, session entière), `marqueurs_cinematique_directe.trc` | 100 Hz | tous les passages |

**13 degrés de liberté évalués** (mêmes que Mesh2Sim, à réutiliser tels quels) :
`hip_flexion`, `hip_adduction`, `hip_rotation`, `knee_angle`, `ankle_angle` (droite et
gauche), `pelvis_tilt`, `pelvis_list`, `pelvis_rotation`.

## Ce qu'il a fallu découvrir sur chaque jeu (à mentionner dans « Data » ou en annexe)

**BioCV.** Le bloc 3×3 de la calibration est s·R (s ≈ 0,998) : orthonormaliser. Marqueurs
c3d dans le même repère (vérité anthropométrique). Stature dans `participantData.csv`.
Une caméra (08) voit parfois un passant.

**IMOVE-23.** `<transform>` est monde→caméra, t en mm, Z vers le haut. Distorsion
`radialDistortion1..3`, `tangentalDistortion1..2` = OpenCV k1 k2 p1 p2 k3. Caméras 22 et 23
montées sur le côté : on utilise les vidéos `Rotated_` et on tourne K, la distorsion et R ;
le sens de rotation est choisi par la géométrie (image vers le bas du monde), pas par
l'attribut `viewrotation`, qui indique l'inverse. Fenêtre = un aller-retour du tableau
`Timing_IMOVE23.xlsx` (passes 1–2, toutes caméras, écart compris), décimée à 50 Hz. Le
numéro de prise varie (`_001`/`_002`). Aucun décalage de synchronisation détecté.

**OpenCap.** `imageSize` stocké à l'envers (se fier au point principal). k3 = 0,2134
partout. Les caméras ne sont pas synchronisées matériellement : `_RAW_WINDOWS.json`
donne l'image de départ de chaque caméra ; on recoupe les vidéos brutes autour de cet
instant, sur `sync_frames` de chaque côté (~2× le clip officiel `syncdWithMocap`, qui
n'est décodable qu'à ~85 %). **Décision** : aucun décalage supplémentaire n'est appliqué
dans les résultats de l'article (voir 05) ; les résultats « resynchronisés » du 17/09
servent d'analyse de sensibilité. La `mocapToVideoTransform` de Session1 est dégénérée
(sans effet sur la comparaison de calibrations).

**LBMC.** `Calib.toml` a les bons K, R, t pour les vidéos redressées, mais ses
coefficients de distorsion sont **divisés par 64** (facteur des intrinsèques Qualisys
en 1/64 pixel, appliqué à tort aux coefficients sans dimension) et les tangentiels ne sont
pas tournés. Le lecteur reprend les coefficients de `Calib.qca.txt` et les tourne selon
le point principal. Vérifié sur les images : la correction réduit l'erreur en bord
d'image de 11–13 % ; la version ÷64 équivaut à ne pas corriger. Le convertisseur
Qualisys de Pose2Sim (`calibration.py` l. 149–152) a le même défaut : à signaler.
Deux participants (157 cm F, 174 cm M), marqueurs c3d 120 Hz avec noms ISB.

**COMFI.** Vidéos 1280×720 à 40 Hz, horodatages logiciels par caméra (départs décalés
de ~19 ms, intervalles 24 ms médian, jusqu'à 72 ms) : il faudra recaler les images sur
les horodatages. Fiches participants `metadata/*.yaml` (taille, poids, sexe). Reste à
vérifier : nature de la calibration fournie, repère commun avec la mocap, rig unique ou
non pour les 18 participants.

## Préparation (commandes)

```
python -m humancalib.evaluation.batch  --root <BioCV> --work_root <w> --participants P03 ... --trials WALK_01 WALK_02 --engines metrabs rtmpose --person_selection motion
python -m humancalib.evaluation.imove  prepare --root <IMOVE-23> --subject 2 --out <w>/imove_subject2 --step 2
python -m humancalib.evaluation.opencap prepare --root <OpenCap> --subject subject2 --trial walking1 --out <w>/s2_w1   # sans --shifts
python -m humancalib.evaluation.lbmc   prepare --root <LBMC> --participant 2 --task gait --out <w>/lbmc_p2
humancalib run <w>/_videos <w>/input/Calib_scene.toml <w>/metrabs_v4 cuda --pose_engine metrabs --person_selection motion
python -m humancalib.evaluation.compare --work <w> --engine metrabs --run metrabs_v4 --scale_method segments --vertical_method walk --out_name metrabs_v4_seg
python -m humancalib.evaluation.plot_rig --work <w> --run metrabs_v4 --eval metrabs_v4_seg --gif
```

Durées mesurées (GPU RTX, une machine) : BioCV MeTRAbs ~10 min, OpenCap ~12 min,
LBMC ~18 min, IMOVE ~60 min (10 caméras, 1400 images) ; RTMPose du même ordre.
