# Refactor & Reproducibility Plan

Objectif : rendre le dépôt installable, reproductible et extensible par un autre laboratoire,
sans changer les résultats scientifiques du pipeline.

- **Auteur du plan :** audit du 2026-09-13 (3 audits parallèles + vérifications directes)
- **État initial :** 6 593 LOC vivantes, 3 120 LOC mortes, 0 test, 0 CI, 0 métadonnée de packaging
- **Document vivant :** cocher les tâches au fur et à mesure, ne pas réécrire l'historique des décisions

---

## 1. Décisions arrêtées

| # | Question | Décision | Conséquence |
|---|----------|----------|-------------|
| D1 | Sort du chemin RTMPose + VideoPose3D | **Garder en option séparée** | Image Docker principale = MeTRAbs seul (~4-5 Go) ; seconde image optionnelle pour RTMPose (~8 Go), documentée comme non maintenue et portant la mention CC BY-NC |
| D2 | Périmètre du chantier | **Socle + packaging complet** | Phases 0 à 8, ~9 jours |
| D3 | Traitement des données personnelles déjà publiées | **Correction en avant** | Pas de `filter-repo`, pas de force-push. À réévaluer avant soumission d'article ou dépôt Zenodo |

---

## 2. Base de preuves

Tout ce qui suit a été **vérifié directement** (exécution, `ffprobe`, `git ls-files`, tests d'import),
pas seulement lu. Les références `fichier:ligne` sont valides à la date de l'audit.

### 2.1 Bugs de correction (indépendants du packaging)

| ID | Sévérité | Localisation | Description |
|----|----------|--------------|-------------|
| B1 | **Haute** | `postprocessing/evaluate_calibration.py:125-128` | `export_to_toml` est un réécrivain ligne à ligne. Si un nom de section TOML ne correspond à aucun nom de vidéo, `current_cam_index = -1` et les lignes `rotation`/`translation` **d'origine sont recopiées telles quelles**, puis `Successfully exported` est affiché. Le livrable principal (`Calib_scene_calibrated.toml`) peut contenir silencieusement les extrinsèques non calibrées d'une caméra. |
| B2 | Moyenne | `calibration/ba.py:618` | `np.alltrue` — supprimé dans NumPy 2.0. Ironie : `core/poses_io.py:96` porte un commentaire expliquant qu'on l'a évité *à cet endroit*. |
| B3 | Moyenne | `argument.py:4` | `from distutils.util import strtobool` — `distutils` supprimé dans Python 3.12. Importé par `ba.py:18`, `calib_linear.py:15`, `inference.py:12`. |
| B4 | Moyenne | `tools/create_cameras_from_toml.py:64`, `pose/metrabs_inference.py:126` | `eval(val)` sur le contenu d'un fichier TOML. Un fichier de calibration partagé entre labos devient un vecteur d'exécution de code arbitraire. |
| B5 | ~~Basse~~ **Clos — sans effet** | `demo/Calib_scene.toml` | Déclare `size = [1088.0, 1920.0]` pour les 4 caméras, mais `cam01`/`cam02` mesurent **1080×1920**. **Investigation T0.6 close : le champ `size` n'est lu par aucun code du pipeline** — sa seule occurrence dans `tools/create_cameras_from_toml.py:21` est une ligne de docstring ; les dimensions réelles viennent du décodeur (`metrabs_inference.py:205`). Métadonnée inerte, **aucun effet numérique. Ne pas corriger** (voir §2.10). |
| B6 | **Moyenne (latent)** | `scripts/calibrate.sh:310` | Écrit en dur `width: 1920, height: 1080, frame_rate: 30` alors que la démo est en 1088×1920 @ 60 fps. Ces valeurs atteignent le BA (`ba.py:641` `img_size`) et pilotent le test de bord `--ba_obs_weight declip` (`ba.py:402-405`) ainsi que `save_mask` (`core/geometry.py:171-173`, qui met à NaN tout point avec `y > height`). Sur des vidéos **portrait** 1088×1920, un `height` de 1080 écarterait ~45 % de l'image — une erreur de **840 px**. Vérifié : les deux chemins sont **désactivés par défaut** (`--ba_obs_weight` = `"none"` et `--save_obs_mask` = `False`, `argument.py:64,42`), donc latent et non actif. |

### 2.2 Le verrou d'installation

`core/__init__.py:34` réexporte `select_gpu` depuis `core/gpu.py`, qui importe `torch` (ligne 6) et
`nvgpu` (ligne 5) au niveau module. **Tout** consommateur de `core` traîne donc PyTorch.

Usage réel vérifié par `grep` : `torch` n'apparaît que dans `pose/inference.py:17` (VideoPose3D) et
`core/gpu.py:6` ; `nvgpu` uniquement dans `core/gpu.py:5`.

**Vérification effectuée :** avec `torch` et `nvgpu` remplacés par des stubs, ces modules s'importent
tous sans erreur sous **Python 3.10** (env `metrabs_opensim`) :
`core`, `core.geometry`, `calibration.calib_linear`, `calibration.ba`, `calibration.ba_jacobian`,
`postprocessing.evaluate_calibration`, `postprocessing.scale_scene`,
`postprocessing.visualize_results`, `argument`.

Aucune syntaxe 3.10+ (`match`, `X | Y`, walrus) et aucune syntaxe 3.8-only dans les 33 fichiers.
Le code lui-même n'impose aucune version ; seul l'environnement le fait.

**Conclusion :** l'env `human_calib` (py3.8, torch 1.13, **7,1 Go**) n'existe que pour le chemin
RTMPose/VideoPose3D. L'isoler permet une image principale sans torch.

### 2.3 Environnements

| Env | Python | Taille disque | Rôle |
|-----|--------|---------------|------|
| `human_calib` | 3.8 | 7,1 Go | Calibration + RTMPose + VideoPose3D |
| `metrabs_opensim` | 3.10.20 | 7,1 Go | MeTRAbs seul (TF 2.12.0, cudatoolkit 11.8, cudnn 8.9.2.26) |

- **15 dépendances sur 22 ne sont pas épinglées** dans `conda_linux.yaml`.
- **Conflit avéré** dans `human_calib` : `opencv-contrib-python 4.7.0.72` (épinglé) **et**
  `opencv-python 4.13.0.92` (tiré par `rtmlib` non épinglé) cohabitent. Deux distributions `cv2`.
- `pycalib-simple` non épinglé a résolu vers `2025.12.5.1` (wheel `py3-none-any`, donc py3.10 OK).
- `onnxruntime-gpu 1.15.0` exige CUDA 11.8 alors que l'env fournit `pytorch-cuda=11.7` : fonctionne
  aujourd'hui grâce au pilote WSL permissif, basculera silencieusement sur CPU dans un conteneur propre.
- `metrabs_opensim` n'est **pas défini dans ce dépôt** — le README renvoie à
  `flodelaplace/Metrabs_to_Opensim`. Le contenu réel tient en 18 lignes d'`environment.yml`.
- Seul emprunt de code à cet écosystème : `cameralib` (`pose/metrabs_inference.py:51`, utilisé une
  fois lignes 422-425). **Absent de PyPI**, installé depuis
  `git+https://github.com/isarandi/cameralib.git@6a9ae983b072f2afb1e1c6229bcc5102719233ac`.
  `model.detect_poses_batched` ne reçoit que `camera.intrinsic_matrix` (ligne 254) : remplaçable par
  `tf.constant(K)[tf.newaxis]`.
  > **Note :** contrairement à ce qu'un premier examen suggérait, la distorsion **n'est pas ignorée**.
  > Elle est traitée par une voie séparée — `undistort_points()` ligne 167, appliquée lignes 463-474
  > après inférence. Ce point est donc du packaging, **pas** un défaut de précision.

### 2.4 Assainissement avant publication

Le dépôt est **déjà public** : `https://github.com/flodelaplace/HumanCalib`.

| ID | Localisation | Contenu |
|----|--------------|---------|
| P1 | `scripts/fix_person_association.py:25` | `/mnt/c/Users/fdela/Documents/These Flo/Stage M2/pose2sim_project` — nom d'utilisateur, intitulé de thèse, contexte de stage. Introduit en `cf5132f`. |
| P2 | `scripts/covisibility_report.py:22,24` | `calib_elodie_unitapa_v3`, `calib_elodie_unitapa` — **prénom de participante** + code de protocole |
| P3 | `scripts/detect_outlier_frames.py:15,18` | `calib_remi_unitapa` — **prénom de participant** |
| P4 | `demo/cam02.mp4` | **Piste audio AAC** + `creation_time = 2024-01-28T01:26:33Z`. Enregistrement sonore d'un sujet humain dans un dépôt public. Également en VP9 quand les trois autres sont en H.264. |
| P5 | `legacy/archive/prepare_h36m.sh:59`, `prepare_panoptic.sh:70` | `/home/slee/pub/...` — répertoire personnel de l'auteur amont (disparaît avec la Phase 3) |

Aucun secret, jeton ou identifiant d'accès détecté sur les 80 fichiers suivis.

**Fichiers suivis à retirer de l'index :**
- 9 fichiers `.idea/` (suivis malgré `.gitignore:58` — une règle d'ignore ne s'applique pas au suivi déjà établi)
- `conda` — fichier de **0 octet**, commit accidentel, aucune règle d'ignore ne le couvre
- `config/config.yaml` — état mutable réécrit à chaque exécution (voir §2.5)

**À conserver** : `input/.gitkeep`, `input/README.md`, `output/.gitkeep` — explicitement autorisés par
`.gitignore:98-103`, ils préservent la structure de dossiers.

**Historique :** sain. `.git` = 11 Mo, 335 objets, 40 commits, 9,39 Mio. Les 4 vidéos de démo
(4,2 Mio au total) n'apparaissent qu'une fois chacune. ~2,4 Mo de blobs d'images mortes, non
significatif. Un simple `git gc` suffit — aucune chirurgie nécessaire.

**Licence :** `LICENSE` = MIT `Copyright (c) 2022 Sang-Eun Lee` (amont, kyotovision-public).
Les contributions du fork (Jacobienne analytique, intégration MeTRAbs, refonte `core/`) n'y figurent pas.
**VideoPose3D est CC BY-NC 4.0** (`third_party/VideoPose3D/LICENSE`) et ses poids dérivent de H36M
(usage recherche uniquement) : le dépôt est MIT mais l'un de ses deux moteurs de pose est
non-commercial, ce qui n'est indiqué nulle part.

### 2.5 `config/config.yaml` — état global mutable

Écrit par un heredoc Python dans le bash (`scripts/calibrate.sh:298-314`), lu par
`calibration/ba.py:592`, `pose/inference.py:294`, `postprocessing/visualize_results.py:478`.

- Suivi par git **et** réécrit à chaque exécution → arbre de travail sali systématiquement
  (le diff actuel montre `camera_ids` passé de 8 à 12 caméras).
- Aucune liaison session → config : lancer un script hors de `calibrate.sh` lit ce qu'a laissé la
  session précédente.
- Lectures relatives au CWD (`"./config/config.yaml"`) dans `inference.py:294` et `calibrate.sh:309`,
  mais ancrées sur `_REPO_ROOT` dans `ba.py:592` — le dépôt est incohérent avec lui-même.
- Blocs de datasets morts `GAFA`, `H36M`, `Panoptic`, `SynADL`, `RETRAIN` (lignes 1-62, 171-244),
  consommés uniquement par `legacy/archive/`.

### 2.6 Dette structurelle

- **Triangulation implémentée 7 fois** : `core/geometry.py:36` (morte), `core/geometry.py:76`,
  `core/geometry.py:15` (imbriquée, masque la première), `evaluate_calibration.py:50`,
  `visualize_results.py:139` (**doublon verbatim** de la précédente),
  `scale_scene.py:72`, `fix_person_association.py:72`.
- **`parse_toml` en 4 variantes** : `create_cameras_from_toml.py:42-67` et
  `metrabs_inference.py:96-129` (corps de 26 lignes **identique octet pour octet**),
  `fix_person_association.py:54-69` (regex + `ast.literal_eval`), `evaluate_calibration.py:37-41` (`tomli`).
- `METRABS_BML87_INDICES` dupliqué (`core/skeletons.py:189` et `metrabs_inference.py:58`) — cause
  légitime : le second tourne dans un autre env conda et ne peut pas importer `core`. **C'est
  exactement l'argument pour un package installable** (Phase 6).
- **12 manipulations de `sys.path`** ; `postprocessing/scale_scene.py:41` fait
  `from evaluate_calibration import export_to_toml` (import frère nu) → le module est chargé **deux
  fois sous deux noms différents** dans la même exécution.
- `calibration/`, `pose/`, `postprocessing/`, `scripts/`, `tools/`, `utils/` **n'ont pas d'`__init__.py`**
  mais sont importés comme des packages : ne fonctionne qu'en packages-espaces-de-noms PEP 420.
- 9 fonctions mortes confirmées, 15 arguments CLI morts sur 40, 73 relevés `pyflakes`,
  3 `import *` qui neutralisent toute analyse statique.
- `legacy/archive/` : 27 fichiers, 3 120 LOC, **zéro référence vivante**, et **déjà cassés**
  (`import util` — le module n'existe plus depuis la refonte Phase 2).

### 2.7 Orchestration

`scripts/calibrate.sh` : 495 lignes, 3 couches (bash → runner Python → worker Python), 4 pour les
étapes linéaire/BA en comptant les sous-processus. 40 arguments dans `argument.py` + 87 dans les
11 parseurs par script + 19 sur `calibrate.sh`.

- `scripts/run_ba.py` n'a **aucun argparse** : 13 emplacements positionnels décodés par index
  (lignes 42-46), dont `false true` en dur à l'appel (`calibrate.sh:381`).
- **3 protocoles de scraping de stdout** servent d'API entre processus :
  `calibrate.sh:396` (grep `Global MRE` + `awk` + `bc`), `run_calib_linear.py:127-135` (le même
  nombre, extrait une seconde fois indépendamment), `calibrate.sh:372` (grep `NEW_DROPS=`).
- Logique applicative en bash : validation du cache de poses (151-197), dérivation de `AID/PID/GID`
  par regex sur le **nom du dossier de sortie** (101-110), 2 heredocs Python (259-290, 298-314),
  sélection du meilleur modèle (388-404).
- `AID`/`PID`/`GID`, `SUBSET="noise_1_0"`, `DATASET="MyDataset"` : vestiges du dataset amont, figés en
  constantes mais propagés dans **15 fichiers** et dans tous les chemins de sortie.
- **Piège d'interpréteur :** `calibrate.sh` appelle `python3` nu une dizaine de fois. Sur la machine
  de développement, `python3` → `/home/fdela/miniconda3/bin/python3` = **Python 3.13.12** (conda
  *base*). Les `.pyc` `cpython-313` à la racine prouvent que le pipeline a déjà tourné sur le mauvais
  interpréteur.

### 2.8 Déterminisme

- Aucun RNG dans le code vivant (`--ransac_seed` et 3 autres arguments RANSAC sont morts).
- Le cœur de calibration est déterministe (SVD, Procrustes, `least_squares` TRF depuis `theta0`).
- `numba` est importé (`ba.py:14`) mais **aucun `@jit` n'est appliqué** — dépendance morte.
- Non-déterminisme réel : inférence GPU (TF 2.12 sans `enable_op_determinism`), nombre de threads BLAS
  non contraint, et surtout **deux mécanismes à état** — le cache de poses et les sidecars
  `.dropped.json` écrits dans le dossier d'entrée — qui font qu'une seconde exécution n'est jamais
  identique à la première par construction.

### 2.9 Actifs téléchargés

| Actif | Taille | Source | Risque |
|-------|--------|--------|--------|
| MeTRAbs `metrabs_l` | 1,1 Go | `https://bit.ly/metrabs_l` (`metrabs_inference.py:398`) | **Raccourcisseur d'URL tiers dans le chemin critique** : non versionné, redirigeable silencieusement, bloqué par de nombreux proxys institutionnels |
| RTMPose ONNX + YOLOX | ~160 Mo (mode `balanced`) | URLs internes à `rtmlib` | `rtmlib` non épinglé ⇒ le modèle téléchargé peut changer sans préavis |
| VideoPose3D (poids) | 65 Mo | `dl.fbaipublicfiles.com` | Stable ; aucune somme de contrôle |
| VideoPose3D (source) | 20 Mo | GitHub HEAD, **non épinglé** | `.gitmodules` déclare un submodule **fantôme** : `git ls-files -s` ne contient aucun gitlink, `git submodule update` est un no-op. Seul le `git clone` de secours de `setup_models.sh` fonctionne réellement. |

Les deux caches vivent dans `$HOME/.cache` → à monter ou intégrer à l'image, sinon 1,2 Go
retéléchargés à chaque `docker run`. `TFHUB_CACHE_DIR` est déjà surchargeable
(`metrabs_inference.py:31`, via `setdefault`) ; le cache `rtmlib` ne l'est pas.

`singularity/` (ignoré par git, présent sur disque) : `env.def` hérité du dépôt amont, ~4 ans
d'obsolescence (torch 1.8.1 / CUDA 11.1 / detectron2 — aucun utilisé par ce fork). À remplacer par le
Dockerfile ; seule sa liste de paquets apt est réutilisable.

### 2.10 Verdict T0.6 — l'écart 1080/1088 px est sans conséquence

Investigation close. Le champ `size` du TOML est **inerte** : aucun consommateur du pipeline ne le lit.
Vérifié sur `tools/create_cameras_from_toml.py` (lit `matrix`, `distortions`, `rotation`, `translation` ;
`size` n'apparaît qu'en docstring ligne 21), `pose/metrabs_inference.py:142,144`,
`postprocessing/evaluate_calibration.py:113` (recopie la ligne `size` verbatim), `calibration/ba.py`,
`postprocessing/scale_scene.py` et `scripts/calibrate.sh`. Les dimensions réellement utilisées viennent
du décodeur vidéo (`metrabs_inference.py:205`, `:469`). Seul `utils/convert_calib_rotation.py:86,88`
le lit — utilitaire autonome non appelé par `calibrate.sh`.

Deux hypothèses concurrentes ont été testées quantitativement :

- **Padding macrobloc de cam03/cam04 — réfuté.** Un padding x264 réplique le bord : les colonnes
  1080-1087 seraient quasi identiques à la colonne 1079. Mesuré : la divergence croît de façon
  monotone avec la distance (MAD 1,62 → 6,08 pour cam03 ; 2,67 → 10,52 pour cam04) et rejoint la
  ligne de base intérieure. Contenu optique réel jusqu'à la dernière colonne.
- **Rééchantillonnage 1080→1088 — réfuté.** Aucune signature périodique de resampling ; le pic FFT
  le plus élevé appartient à une vidéo *1080* de large.

Le point principal ne permet pas de départager : l'écart discriminant est de 4 px alors que la
dispersion inter-caméras de `cx` vaut σ ≈ 12 px (rapport signal/bruit ≈ 0,33).

**Conséquence :** ne modifier ni `demo/Calib_scene.toml` ni les vidéos. À traiter plutôt en Phase 3/8 :
supprimer la ligne de docstring trompeuse `tools/create_cameras_from_toml.py:21`, ou valider le champ
`size` contre la vidéo réelle. Le vrai défaut à corriger est B6 (T4.2).

---

## 3. Phases

Chaque tâche porte un identifiant stable (`T<phase>.<n>`) pour le suivi.

### Phase 0 — Assainissement publication · ~1 h

> Priorité : le dépôt est déjà public et contient des données de sujets humains.

| ID | Tâche | Référence | État |
|----|-------|-----------|------|
| T0.1 | Neutraliser les prénoms de participants dans les exemples d'usage → `./input/my_session` | P2, P3 | fait |
| T0.2 | Neutraliser le chemin personnel dans la docstring | P1 | fait |
| T0.3 | `git rm --cached` sur les 9 fichiers `.idea/` + le fichier `conda` de 0 octet | §2.4 | fait |
| T0.4 | `git rm --cached config/config.yaml` + ajout au `.gitignore` (sa suppression fonctionnelle est en Phase 4) | §2.5 | fait |
| T0.5 | Retirer la piste audio et les métadonnées de `demo/cam02.mp4`. **Réencodage H.264 abandonné** : la provenance des vidéos n'étant pas établie (§2.10), le retrait est fait en `-c:v copy`, flux vidéo vérifié bit-identique (`framemd5` inchangé). cam02 reste en VP9. | P4 | fait |
| T0.6 | **Investiguer** l'écart 1080 vs 1088 px avant toute correction du TOML de démo — déterminer si les intrinsèques ont été calibrées sur des images 1080 ou 1088 | B5 | **fait — verdict : ne rien corriger** |
| T0.7 | LICENSE : ajouter le copyright du fork sans retirer celui de l'amont | §2.4 | fait |
| T0.8 | `git gc` (335 objets non compactés, 0 pack) | §2.4 | fait — `.git` 11 Mo → 8,3 Mo, 335 objets épars → 321 empaquetés |

**Critère d'acceptation :** `grep -riE "elodie|remi|unitapa|fdela" $(git ls-files)` ne retourne rien ;
`ffprobe demo/cam02.mp4` ne montre aucun flux audio ; `git status` propre après une exécution de démo.

---

### Phase 1 — Bugs + environnements épinglés · ~1 j
*Dépend de : Phase 0*

| ID | Tâche | Référence | État |
|----|-------|-----------|------|
| T1.1 | Corriger `export_to_toml` : échouer bruyamment sur un nom de caméra non apparié, au lieu de recopier les extrinsèques d'origine | B1 | fait — testé (nominal + non-apparié) |
| T1.2 | `np.alltrue` → `np.array_equal` | B2 | fait |
| T1.3 | Remplacer `distutils.util.strtobool` par un parseur local | B3 | fait |
| T1.4 | Rendre `core/gpu` paresseux : retirer la réexportation de `core/__init__.py:34`, importer `select_gpu` à l'usage dans `pose/inference.py:282` | §2.2 | fait — vérifié : `core` importable sans torch ni nvgpu |
| T1.5 | `envs/calib.yaml` — py3.10, TF 2.12, MeTRAbs + cœur calibration, **toutes versions épinglées** depuis la résolution actuelle vérifiée | §2.3 | **fait** |
| T1.6 | `envs/rtmpose.yaml` — py3.8, torch 1.13, rtmlib, épinglé ; résoudre le double OpenCV | §2.3 | **fait** |
| T1.7 | Supprimer les 7 dépendances mortes (`pandas`, `networkx`, `tabulate`, `termcolor`, `portalocker`, `ninja`, `numba`) | §2.3 | **fait** — équivalence prouvée sur les 4 caméras de démo (mêmes valeurs, dtype, forme) |
| T1.8 | Résoudre `bit.ly/metrabs_l` vers son URL permanente et l'inscrire en dur | §2.9 | **fait** — URL RWTH résolue et vérifiée (301 → 200, 708 Mo) ; cache TF Hub préservé par lien symbolique sur le nouveau hash |
| T1.9 | Supprimer la dépendance `cameralib` (remplacer par `tf.constant(K)[tf.newaxis]`) — élimine la seule dépendance `git+https` | §2.3 | **fait** — équivalence prouvée sur les 4 caméras de démo (mêmes valeurs, dtype, forme) |
| T1.10 | Épingler le commit VideoPose3D dans `setup_models.sh` ; supprimer `.gitmodules` (submodule fantôme) | §2.9 | **fait** — commit `1afb1ca0` épinglé, SHA256 des poids vérifié, `.gitmodules` supprimé, mention CC BY-NC ajoutée |

**Correctif connexe (hors liste) :** `postprocessing/evaluate_calibration.py:37-41` n'avait pas le repli `tomllib`-d'abord présent dans les deux autres lecteurs TOML ; il affichait une erreur à l'import et dégradait silencieusement (`tomllib = None`). Aligné sur le motif commun.

**Critère d'acceptation :** création des deux envs depuis zéro, puis exécution complète de la démo
MeTRAbs dans `envs/calib.yaml` **sans torch installé**, avec un MRE final conforme à la référence.

---

### Phase 2 — Docker · ~1 j
*Dépend de : Phase 1*

| ID | Tâche |
|----|-------|
| T2.1 | **fait** — `Dockerfile`. **Écart assumé au plan initial : base `ubuntu:22.04`, pas `nvidia/cuda`.** Le CUDA userspace dont TensorFlow a besoin est déjà déclaré dans `envs/calib.yaml` (cudatoolkit 11.8 + cuDNN 8.9) ; une base CUDA en poserait une **seconde** copie, construite indépendamment, sur le chemin de l'éditeur de liens — ~1,8 Go de doublon dont le seul effet possible est de lier la mauvaise. Une seule déclaration = le conteneur exécute la même pile qu'une installation native, ce qui est précisément l'objectif. `NVIDIA_VISIBLE_DEVICES`/`NVIDIA_DRIVER_CAPABILITIES` déclarés explicitement, faute d'être hérités. apt réduit à `libgl1 libglib2.0-0 ca-certificates bzip2` : `ffmpeg` vient de l'env conda (deux builds sur le PATH sinon), `git`/`wget` ne servent qu'à l'image rtmpose |
| T2.2 | **fait** — `Dockerfile.rtmpose`, derrière un profil compose pour qu'aucun `docker compose build` ne le construise par accident. Mention CC BY-NC 4.0 en tête de fichier, dans le `LABEL ...licenses="MIT AND CC-BY-NC-4.0"` et dans `compose.yaml`. `rtmlib` installé en post-étape `--no-deps` (voir `envs/rtmpose.yaml`) ; VideoPose3D et ses poids cuits dans l'image via `setup_models.sh` |
| T2.3 | **fait** — `docker/entrypoint.sh`. Toutes les étapes passent par `${HUMANCALIB_PYTHON}`, chemin absolu de l'interpréteur de l'env. `MPLBACKEND=Agg`, `MPLCONFIGDIR`, `HOME=/tmp` (le conteneur tourne sous l'uid de l'hôte, sans entrée passwd), `PYTHONUNBUFFERED=1`, `PYTHONDONTWRITEBYTECODE=1`, `TFHUB_CACHE_DIR=/models/tfhub`, `OMP_NUM_THREADS=4`. Préflight : GPU absent, `/output` non inscriptible, cache modèles non monté |
| T2.4 | **fait** — le correctif WSL est désormais conditionné à l'existence de `/usr/lib/wsl/lib`. Inconditionnel, il masquait les stubs du driver injectés par le runtime NVIDIA |
| T2.5 | **fait** — `HUMANCALIB_PYTHON` et `HUMANCALIB_METRABS_PYTHON` surchargent respectivement `python3` et `conda run -n metrabs_opensim`. Dans l'image les deux moitiés partagent un env : conda n'est jamais invoqué |
| T2.6 | **fait** — `core/gpu.py` respecte un `CUDA_VISIBLE_DEVICES` déjà positionné. L'indice qu'il écrivait compte sur la liste **complète** des périphériques : il pouvait donc désigner une carte non allouée au job (`--gpus device=1`, `--gres=gpu` de Slurm, épinglage par tâche). Un argument explicite l'emporte encore, avec avertissement |
| T2.7 | **fait** — `compose.yaml` : `./input:/input:ro` (rendu possible par T4.3), `./output:/output`, volume nommé pour le cache modèles, `user: ${HOST_UID}:${HOST_GID}`, argument de build `BAKE_MODELS`. **Piège évité :** la forme *mapping* `CUDA_VISIBLE_DEVICES: ${CUDA_VISIBLE_DEVICES:-}` la définit à la chaîne vide à chaque exécution — c'est exactement la façon de dire à CUDA de n'exposer aucun GPU. Forme *liste* (nom nu) : transmise seulement si l'hôte la définit |
| T2.8 | **fait** — `.dockerignore`. `demo/` volontairement **conservé** (4,2 Mo) : `docker compose run calib demo` est le critère d'acceptation de l'image et a besoin des clips |

**Critère d'acceptation :** `docker compose run calib` exécute la démo de bout en bout sur une machine
propre, avec `--gpus all`, et produit le même MRE qu'en natif.

---

### Phase 3 — Nettoyage · ~1 j
*Dépend de : Phase 1. Parallélisable avec la Phase 2.*

| ID | Tâche | Référence |
|----|-------|-----------|
| T3.1 | `git tag archive/pre-metrabs-research` puis `git rm -r legacy/` ; pointer le tag depuis le README | §2.6 |
| T3.2 | Supprimer les 15 arguments morts d'`argument.py` (11 n'existent que pour `legacy/`) | §2.6 |
| T3.3 | Supprimer les 4 blocs de datasets morts du `config.yaml` | §2.5 |
| T3.4 | Supprimer les 9 fonctions mortes confirmées | §2.6 |
| T3.5 | Unifier la triangulation. **Partiellement fait : 7 → 5.** Les deux `triangulate_skeleton` (prouvés équivalents par diff) sont fusionnés, et le `triangulate` mort de `core/geometry.py` — qui partageait la signature de `pycalib.calib.triangulate` et le masquait via `from core import *` — est supprimé. **La consolidation restante est reportée après la Phase 5** : `scale_scene.get_3d_keypoint` et `fix_person_association.triangulate` ont des signatures et des pondérations différentes ; les fusionner sans test golden-run risquerait des résultats faux sans plantage. | §2.6 |
| T3.6 | Unifier `parse_toml` : 4 variantes → une, **sans `eval()`** | §2.6, B4 |
| T3.7 | Source unique pour les constantes de squelette (supprimer les doublons de `visualize_results.py:46-91`) | §2.6 |
| T3.8 | Supprimer les 73 imports inutilisés et les 3 `import *` | §2.6 |
| T3.9 | **sans objet** — vérifié : `singularity/` est *gitignoré* (`.gitignore:78`) et n'a jamais été suivi par git. Il n'a donc jamais été publié et il n'y a rien à retirer du dépôt ; les fichiers restent en local sur la machine de l'auteur. La recette était bien obsolète (torch 1.8.1/CUDA 11.1, detectron2 — inutilisé partout —, `numba`, et les **deux** distributions opencv, soit le bug corrigé en Phase 1). Ajouté au `.dockerignore` pour ne pas se retrouver dans l'image. | §2.9 |

**Critère d'acceptation :** `pyflakes` propre ; la démo produit un MRE identique à ±1e-9 avant/après.

---

### Phase 4 — Config par session · ~1 j
*Dépend de : Phase 3*

| ID | Tâche | Référence |
|----|-------|-----------|
| T4.1 | **fait** — `core/session.py` + `scripts/write_session.py` ; `config/config.yaml` supprimé, session écrite dans `<output_dir>/<subset>/session.yaml` | §2.5 |
| T4.2 | **fait** — `probe_videos()` lit les vidéos via OpenCV. Sur la démo : 1080×1920 @ 60 au lieu du 1920×1080 @ 30 codé en dur, et un avertissement signale l'hétérogénéité cam01/cam02 vs cam03/cam04 | B6 |
| T4.3 | **fait** — `core/sidecars.py` ; écriture dans `<output>/<subset>/dropped_frames/`, lecture rétro-compatible de l'ancien emplacement (fusion, avec avertissement) pour ne perdre aucune exclusion déjà constituée | §2.8 |
| T4.4 | **fait** — constantes fixes et documentées ; renommer un dossier de sortie ne change plus silencieusement les fichiers cherchés. Leur suppression complète touche 15 fichiers et la disposition des artefacts sur disque : reportée au packaging | §2.7 |

**Critère d'acceptation :** deux sessions concurrentes sur des jeux de données différents n'interfèrent
plus ; `input/` montable en lecture seule ; `git status` reste propre après exécution.

---

### Phase 5 — Tests + CI · ~1,5 j
*Dépend de : Phase 4*

| ID | Tâche |
|----|-------|
| T5.1 | **fait** — `tests/fixtures/demo_20f/`, 412 Ko. 20 images **contiguës** : `load_eldersim` intersecte les indices d'images avec ceux du squelette monde, décalés d'une unité (B7), donc une sélection éparse donnait une intersection **vide** et la fixture ne testait rien. C'est ainsi que B7 a été découvert. |
| T5.2 | Test golden-run : linéaire → BA → évaluation sur `demo/`, MRE dans une tolérance. **Tolérances mesurées le 2026-09-14** en rejouant la calibration du run natif du 2026-05-11 sur poses figées, dans le conteneur : l'étape **linéaire est reproduite au bit près** (rotation 0,000°, translation 1,4e-12 sur ~6073) — donc testable à 1e-9. Le **BA ne l'est pas** : 0,011° de rotation et 2e-4 en translation relative, parce que `least_squares` (TRF) suit un chemin d'itérations différent au moindre epsilon et s'arrête ailleurs dans le même bassin. Un test d'égalité stricte sur le BA serait instable ; viser ~0,05° et 1e-3 relatif |
| T5.3 | **fait** — recouvrement exact d'une similitude connue, identité, invariance d'échelle, et refus des réflexions (seul mode d'échec d'Umeyama produisant un résultat plausible plutôt qu'une erreur). |
| T5.4 | **fait — a trouvé un bug dès la première exécution.** `_varbone_jac` faisait `xw[invalid_mask] = np.nan` : avec `invalid_mask=None`, `xw[None]` ajoute un axe et l'affectation remplit **tout** le tableau de NaN, donc le bloc ne renvoyait aucune ligne — régularisateur d'os **silencieusement inerte**. Production épargnée (`ba.py:362` passe toujours un tableau), mais `objfun_varbone` accepte `None` et le protège : résidu et dérivée étaient en désaccord sur le contrat. Corrigé. Bloc de reprojection concordant à **3,9e-10**. |
| T5.5 | **fait** — `tests/test_triangulation.py`. Le dépôt contenait **deux estimateurs distincts**, pas cinq doublons : (a) DLT homogène par SVD, en trois copies (`triangulate_skeleton`, `get_3d_keypoint`, `fix_person_association.triangulate`) et (b) moindres carrés inhomogènes pondérés (`core.triangulate_point`), qui fixe la coordonnée homogène à 1 au lieu de prendre le plus petit vecteur singulier — donc **volontairement différent** sous bruit. Les trois copies de (a) ont été prouvées identiques à 1e-9, bruit compris, **avant** d'être fusionnées dans `core.geometry.triangulate_dlt` ; (b) n'est pas fusionné, et un test vérifie que les deux familles restent distinctes (écart borné à 5 mm pour 2 px de bruit) pour que personne ne les confonde plus tard. Clôt la déduplication reportée en T3.5 : 5 → 2. |
| T5.6 | **fait** — 27 os, prouvés être la topologie à 26 articulations réindexée, ne touchant que les 26 articulations réelles. |
| T5.7 | **fait** — aller-retour `load_poses` (indices non contigus compris) et export TOML : caméra absente refusée, caméra incomplète refusée, `[metadata]` toléré, rien écrit en cas d'échec. |
| T5.8 | **fait** — `.github/workflows/tests.yml`. `envs/ci.yaml` = `calib.yaml` sans les 2,8 Go de CUDA ni TensorFlow, qu'aucun test n'importe ; `test_env_consistency.py` échoue si les deux fichiers divergent sur un paquet commun, pour que la duplication ne pourrisse pas. Second job : `bash -n` sur tous les scripts shell. |

**Critère d'acceptation : tenu (2026-09-14).** 51 tests verts en 4,4 s dans le conteneur avec `CUDA_VISIBLE_DEVICES=""`, sans téléchargement de modèle ni réseau ; les quatre exécutions GitHub Actions déclenchées par ces commits sont vertes sur runner public.

---

### Phase 6 — Package installable · ~1,5 j
*Dépend de : Phase 5 (les tests protègent le déplacement des fichiers)*

| ID | Tâche |
|----|-------|
| T6.1 | **fait** — `src/humancalib/{core,calibration,pose,postprocessing,pipeline,tools}` + `pyproject.toml`. **Deux couches de dépendances, volontairement** : `pyproject.toml` déclare des *plages* compatibles (ce que `pip install` résout), `envs/*.yaml` épinglent les versions *exactes* validées ; `test_env_consistency.py` échoue si un épinglage sort de sa plage. Extras `metrabs` et `dev`. Wheel vérifié : ne contient que `humancalib/` |
| T6.2 | **fait** — 13 manipulations, pas 12, → **0** vers la racine du dépôt. Une seule subsiste, et elle est légitime : VideoPose3D n'est pas un paquet (ses modules s'importent en `common.*`), désormais relocalisable via `HUMANCALIB_VP3D_DIR`. `visualize_results.py` insérait aussi le chemin de VideoPose3D sans jamais l'importer : code mort, supprimé. Les sous-processus (`run_ba` → `ba`, `run_calib_linear` → `calib_linear`, `evaluate_calibration`) sont lancés en `python -m`, plus par chemin de fichier |
| T6.3 | **fait** — qualifié dès la Phase 2 (défaut n°3 du conteneur), désormais `humancalib.postprocessing.evaluate_calibration` |
| T6.4 | **fait** — `pipeline/` regroupe les étapes que lance `calibrate.sh` (dont `create_cameras_from_toml`), `tools/` les utilitaires autonomes (`covisibility_report`, `fix_person_association`, et les deux de `utils/`). Répertoires racine `tools/` et `utils/` supprimés |
| T6.5 | **fait** — la copie de `METRABS_BML87_INDICES` dans `metrabs_inference.py` (vestige d'un env séparé qui ne pouvait pas importer le code partagé) est remplacée par un import. `pip install --no-deps -e .` documenté pour `envs/calib.yaml`. **L'env `rtmpose` (py3.8) n'installe pas le paquet, délibérément** : la licence SPDX exige setuptools ≥ 77, donc Python ≥ 3.9 ; ce chemin figé tourne depuis les sources via `PYTHONPATH`, que `calibrate.sh` exporte |
| T6.6 | **fait** — arborescence réécrite (elle listait encore `config/config.yaml` et `legacy/archive/`, supprimés en Phases 3-4), note `sys.path` remplacée, 17 références de chemins mises à jour, section « Installing as a Python package » qui dit franchement ce que pip seul ne peut pas fournir (CUDA pour TF 2.12) |

**Critère d'acceptation :** `pip install .` dans un env vierge, puis exécution de la démo depuis un
répertoire de travail arbitraire.

*Vérifié (2026-09-14)* : installé dans l'image puis utilisé depuis `/` **sans `PYTHONPATH`** — `import humancalib` résout vers `site-packages`, `python -m humancalib.pipeline.write_session` et `python -m humancalib.pose.metrabs_inference` répondent ; 52 tests verts. Démo de bout en bout depuis l'image qui installe le paquet par pip : `DEMO_RC=0`, `Compute device: GPU`, MRE **4,057 px** (BA) / 8,214 px (linéaire), fichiers de sortie à l'uid de l'hôte, `output/demo` bien ignoré par git ; CI verte sur runner public, étapes d'installation et d'import hors dépôt comprises. **Critère tenu.**

*Sur l'écart de MRE* avec la validation Docker du matin (4,050 / 7,998) : il ne vient pas de l'empaquetage — le golden-run, sur poses figées, reste identique. Deux causes connues se cumulent ici sans pouvoir être séparées par ce seul run : le correctif B7, qui réintègre l'image 0 et change donc les images retenues par `frame_skip=10` (0, 10, … au lieu de 1, 11, …), et la ré-extraction des poses sur GPU, non déterministe. Le BA absorbe presque tout (+0,007 px) ; l'initialisation linéaire, plus sensible au choix des images, bouge de 0,2 px.

**Découvert en chemin, hors périmètre prévu :** `calibrate.sh` lançait l'étape MeTRAbs via `conda run -n metrabs_opensim` **sans condition** — l'environnement de la machine de l'auteur. Toute installation suivant le README (`envs/calib.yaml`, un seul env) échouait dès l'étape 1 sur `EnvironmentLocationNotFound` ; seul Docker y échappait, parce qu'il surchargeait la variable. L'env séparé n'est plus utilisé que s'il existe.

**Reporté en Phase 8 :** `conda_linux.yaml`, encore suivi à la racine, est supplanté par `envs/` et n'apparaît plus dans l'arborescence documentée.

---

### Phase 7 — CLI Python unique · ~2-3 j
*Dépend de : Phase 6*

| ID | Tâche |
|----|-------|
| T7.1 | **fait** — `humancalib run` (pipeline complet, **ligne de commande de `calibrate.sh` inchangée**, mots nus `cuda balanced` compris) et `humancalib <étape>` pour les 11 étapes ; commande `humancalib` installée par pip, et `python -m humancalib`. *La prémisse « chaque étape a déjà un `main(argv)` » était fausse* : seules 3 sur 11 en avaient un ; `calib_linear` n'avait qu'un bloc `__main__`. Toutes en ont désormais un |
| T7.2 | **fait** — `pipeline/poses_cache.py` (vérification du cache de poses) et `pipeline/frame_mapping.py` (squelette monde en numéros absolus), testés ; la règle du cache est volontairement conservée à l'identique (plage d'images seulement, pas les intrinsèques — limite documentée dans `HOWTO.md`) |
| T7.3 | **fait** — options nommées avec les valeurs du pipeline par défaut ; l'ancienne forme à 13 positionnels reste acceptée, dépréciée, pour ne casser aucun script existant ; boucle de reprise testée avec un exécuteur simulé |
| T7.4 | **fait** — `evaluate_calibration.main` renvoie le MRE, `detect_outlier_frames.main` le nombre d'images écartées. Le plus fragile était dans `run_calib_linear` : le MRE de chaque chunk était le 4ᵉ mot d'une ligne contenant « Global MRE » ; reformuler ce message aurait rendu tous les chunks inévaluables et fait échouer la calibration |
| T7.5 | **fait, avec deux exceptions de plus que prévu, assumées.** En processus : caméras, session, chunks linéaires et leur évaluation, détection d'aberrants, évaluation, mise à l'échelle ; une étape qui fait `sys.exit(≠0)` devient une `PipelineError` qui la nomme. En sous-processus : le BA (reprise OOM), **l'extraction de poses** (TensorFlow/PyTorch gardent la mémoire GPU jusqu'à la fin du processus, et MeTRAbs peut vivre dans un autre env conda) et **la visualisation** (rendu d'animation lourd, dont l'échec a toujours été toléré et ne doit pas emporter une calibration terminée) |
| T7.6 | **fait** — 533 lignes → 5 lignes de code : `cd` à la racine du dépôt (les chemins relatifs du `HOWTO.md` en dépendent) puis `exec python -m humancalib.cli run`. Un test échoue si le shim dépasse 10 lignes de code |
| T7.7 | **fait autrement** — même la bascule `conda run` est passée en Python (`resolve_metrabs_launcher`), où elle est testable ; le shell ne garde que `cd` et `PYTHONPATH` |

**Critère d'acceptation :** les commandes documentées dans `HOWTO.md` fonctionnent à l'identique ; le
golden-run de la Phase 5 reste vert.

*Vérifié* : les trois commandes du `HOWTO.md` sont analysées mot pour mot dans `tests/test_cli.py` ; 93 tests
verts, golden-run compris — les chunks linéaires en processus donnent les mêmes chiffres. *Exécution de bout en
bout de la commande MeTRAbs du `HOWTO.md` via le shim : en cours de vérification.*

**B8 — ordre et extensions des vidéos, découvert en portant `calibrate.sh`.** L'étape de poses numérotait les
caméras dans l'ordre lexicographique (`sorted()`), mais `calibrate.sh` nommait les caméras — donc choisissait
leurs intrinsèques dans le TOML — avec `sort -V`, l'ordre naturel. Identiques sur des noms à zéros (`cam01`) ou
de même longueur, mais pas sur `cam1…cam10` : `cam1 cam2 cam10` contre `cam1 cam10 cam2`. **À partir de la
dixième caméra, des poses étaient appariées aux intrinsèques d'une autre caméra**, sans erreur. De plus,
`calibrate.sh`, `evaluate_calibration` et `scale_scene` ne cherchaient que `*.mp4` pour nommer les caméras alors
que l'étape de poses lit aussi `.avi`, `.mov`, `.mkv` : ces formats, annoncés comme pris en charge par
`HOWTO.md`, arrêtaient le pipeline à l'étape 2. Sept listes de vidéos privées remplacées par
`core/videos.py`, dans l'ordre de l'étape de poses — pas l'ordre naturel, pour ne renuméroter aucune caméra déjà
extraite ; et par un ensemble, car sur un système de fichiers insensible à la casse (NTFS sous `/mnt/c`),
`*.mp4` et `*.MP4` comptaient chaque caméra deux fois. **Les sessions de l'auteur ne sont pas concernées**
(`CAMERA01…`, numéros de série de longueur égale).

**Résumé final trompeur.** Quand `--ref_frame` sortait de la plage, la mise à l'échelle était sautée mais le
tableau final annonçait tout de même « Final TOML file generated ». Le résumé ne liste plus que les fichiers
qui existent.

---

### Phase 8 — logging, langue, documentation · ~1 j
*Dépend de : Phase 7*

| ID | Tâche |
|----|-------|
| T8.1 | 221 `print()` → `logging` avec niveaux (aucun `import logging` dans le dépôt aujourd'hui) |
| T8.2 | Tout en anglais : chaînes, commentaires, et **labels des figures** (`ba.py:649-651` produit des axes en français dans les PNG livrés) |
| T8.3 | `except BaseException` → `except Exception` (`core/gpu.py:26`, intercepte `KeyboardInterrupt`) |
| T8.4 | Traiter les absorptions silencieuses d'exceptions recensées (`visualize_results.py:314`, `convert_calib_rotation.py:89`, `run_calib_linear.py:89`) |
| T8.5 | README réorganisé **Docker d'abord** ; section licences tierces explicite (CC BY-NC pour VideoPose3D, conditions recherche des poids MeTRAbs) ; lien vers ce document |
| T8.6 | `CITATION.cff`, `CONTRIBUTING.md` |

---

## 4. Séquencement et parallélisation

```
Phase 0 ──> Phase 1 ──┬──> Phase 2 (Docker)      ──┐
                      │                            ├──> Phase 5 ──> Phase 6 ──> Phase 7 ──> Phase 8
                      └──> Phase 3 ──> Phase 4   ──┘
```

- **Phases 2 et 3 sont parallélisables** une fois la Phase 1 terminée (l'une touche l'infrastructure,
  l'autre le code).
- La Phase 5 doit précéder la 6 : les tests protègent le déplacement massif de fichiers.
- Les phases 6 → 8 sont strictement séquentielles.

**Jalon intermédiaire livrable** — fin de Phase 2 : un relecteur peut cloner, construire l'image et
exécuter la démo. C'est le point de sortie minimal si le chantier doit s'arrêter en cours.

---

## 5. Registre des risques

| Risque | Probabilité | Mitigation |
|--------|-------------|------------|
| Un refactor modifie silencieusement les résultats numériques | Moyenne | Le golden-run (T5.2) devrait exister avant les Phases 6-7. Pour les Phases 1-4 qui le précèdent, comparer manuellement le MRE de la démo avant/après chaque phase. |
| Le double env ne tient pas en une seule image Docker | Faible | Vérifié : conda/pip embarquent leur propre couche CUDA utilisateur ; seul le pilote hôte est partagé, et ≥525 couvre 11.7 et 11.8. |
| `pycalib-simple` casse sur py3.10 | Faible | Vérifié : wheel `py3-none-any`, installation à blanc réussie dans l'env py3.10. À épingler malgré tout. |
| L'écart 1080/1088 px révèle des intrinsèques de démo erronées | Moyenne | T0.6 est une investigation, pas une correction. Ne pas modifier les vidéos avant d'avoir tranché. |
| Réécriture d'historique réclamée tardivement | Moyenne | D3 = correction en avant. À réévaluer **avant** soumission d'article ou dépôt Zenodo — c'est le dernier moment où le coût reste faible. |

---

## 5 ter. B7 — le squelette monde est écrasé par un placeholder décalé (2026-09-14)

Découvert en construisant la fixture du golden-run (T5.1), parce que
l'intersection des indices d'images y était **vide** — ce qui a obligé à
comprendre pourquoi elle ne l'est pas en production.

**Mécanisme.** L'étape 1 (MeTRAbs) écrit `skeleton_w_G001.json` : la 3D de la
caméra 1, indices d'images 0…N-1. L'étape 2
(`tools/create_cameras_from_toml.py:95-110`) **l'écrase** par un placeholder de
zéros, `np.zeros((n_frames, 25, 3))`, avec `frame_indices = range(1, n+1)`.
Vérifié identique sur le run natif du 2026-05-11 et sur celui du conteneur.

**Conséquence.** `core/poses_io.py:100` fait
`functools.reduce(np.intersect1d, [frames, *f2d_all])`. Avec `[1…N]` contre
`[0…N-1]`, l'intersection vaut `[1…N-1]` : **l'image 0 est écartée de chaque
calibration**, silencieusement. Un second effet, latent : sur des images non
contiguës l'intersection serait vide.

Le contenu du placeholder — les zéros — est **inoffensif** : `p3d_w` est
ignoré par `calib_linear.py:271,275`, et `ba.py:584` le charge dans `sp3d_w`,
le tranche ligne 600, puis ne s'en sert jamais. Seuls les indices comptent.

`scripts/run_calib_linear.py:172` s'en sert aussi pour
`map_video_frames_to_indices`, donc `--start_frame`/`--end_frame` exprimés en
numéros de trame vidéo sont décalés d'une unité.

**Impact numérique, mesuré** sur la fixture (20 images, donc 1 perdue sur 20) :
MRE 5,175 → 5,121 px, rotations caméras déplacées de 0,31° (linéaire) et 0,20°
(BA), translations de 2e-3 relatif. Sur 100 images la perte est de 1 % au lieu
de 5 %, donc l'effet attendu est plus proche de 0,05–0,1°.

**Statut : corrigé le 2026-09-14 (décision D4).** Le placeholder n'écrase plus
un squelette réel déjà écrit, et ses indices sont repris **des fichiers de
poses eux-mêmes** plutôt que d'une plage supposée — une plage supposée
réintroduirait le même décalage dès qu'une image est écartée. Les valeurs de
référence du golden-run ont été régénérées ; l'ampleur du déplacement est
désormais mesurée à chaque exécution du test au lieu d'être subie.

**D4 — chiffres publiés.** Corriger déplace les résultats déjà publiés
(~0,05–0,1° attendu sur 100 images). Retenu quand même : un article décrivant
un pipeline reproductible ne devrait pas embarquer un décalage connu, et le
golden-run rend l'écart mesurable plutôt qu'invisible.

---

## 5 bis. Validation du 2026-09-14 — ce que le conteneur a révélé

`docker compose run calib demo` s'exécute de bout en bout sur GPU, 7 étapes,
`DEMO_RC=0`, MRE **4,050 px** pour `linear_1_0_ba` contre 7,998 px pour `linear_1_0`.
Fichiers de sortie appartenant à l'utilisateur hôte, pas à root. Critères
d'acceptation des Phases 1 et 2 tenus.

Construire l'image depuis zéro a mis au jour **six défauts réels** qu'une
installation native vieille de plusieurs mois masquait. Trois n'auraient jamais
planté — ils auraient seulement mal fonctionné, ce qui est pire :

| # | Défaut | Symptôme pour un nouvel arrivant | Correctif |
|---|--------|----------------------------------|-----------|
| 1 | `pandas` non déclaré par `pycalib-simple` (`pycalib/__init__` → `.robust`) | `ModuleNotFoundError` sur `import pycalib` | ajouté au bloc **pip** (pas conda : sinon numpy conda écrase numpy pip) |
| 2 | `setuptools` ≥ 81 a supprimé `pkg_resources`, que `tensorflow-hub` importe inconditionnellement | chemin MeTRAbs inimportable | `setuptools=80.9.0`. Échéance connue : l'API est vouée à disparaître |
| 3 | `scale_scene.py` importait son voisin en nom nu | exécutable en script, non importable en module | qualifié `postprocessing.evaluate_calibration` |
| 4 | **`LD_LIBRARY_PATH` absent** : TF ne trouvait pas libcudart/libcudnn dans l'env conda | **pipeline entier sur CPU, ~20× plus lent, sans un message** | `ENV LD_LIBRARY_PATH` + le device annoncé à chaque run + l'entrypoint refuse de démarrer dans ce cas |
| 5 | **`bc` absent d'Ubuntu minimal** (`calibrate.sh`) | **la sélection de la meilleure calibration ne se faisait plus** — substitution vide, test jamais déclenché | remplacé par `awk`, présent dans la base |
| 6 | **Regex sur le nom du dossier de sortie**, dupliquée dans 3 scripts de post-traitement | avertissement alarmant à chaque exécution normale ; renommer un dossier changeait les fichiers lus | lecture du fichier de session (achève T4.4, close à tort dans `calibrate.sh` seulement) |

Mesures : GPU 9–12 s par caméra contre 3 min 55 s en CPU. Image ramenée de
12,2 à 10,4 Go en sortant 902 Mo de cache pip vers un montage BuildKit.

**Reproductibilité numérique** — voir T5.2 pour les tolérances mesurées.

---

## 6. Suivi

| Phase | État | Date |
|-------|------|------|
| 0 — Assainissement publication | **terminée** | 2026-09-13 |
| 1 — Bugs + envs épinglés | **terminée** | 2026-09-14 |
| 2 — Docker | **terminée** | 2026-09-14 |
| 3 — Nettoyage | **terminée** | 2026-09-13 |
| 4 — Config par session | **terminée** | 2026-09-13 |
| 5 — Tests + CI | **terminée** | 2026-09-14 |
| 6 — Package | **terminée** | 2026-09-14 |
| 7 — CLI Python | écrite, démo HOWTO en vérification | 2026-09-14 |
| 8 — logging + docs | à faire | |
