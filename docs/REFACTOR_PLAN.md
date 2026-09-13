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
| T1.5 | `env/calib.yaml` — py3.10, TF 2.12, MeTRAbs + cœur calibration, **toutes versions épinglées** depuis la résolution actuelle vérifiée | §2.3 | en cours (agent) |
| T1.6 | `env/rtmpose.yaml` — py3.8, torch 1.13, rtmlib, épinglé ; résoudre le double OpenCV | §2.3 | en cours (agent) |
| T1.7 | Supprimer les 7 dépendances mortes (`pandas`, `networkx`, `tabulate`, `termcolor`, `portalocker`, `ninja`, `numba`) | §2.3 | **fait** — équivalence prouvée sur les 4 caméras de démo (mêmes valeurs, dtype, forme) |
| T1.8 | Résoudre `bit.ly/metrabs_l` vers son URL permanente et l'inscrire en dur | §2.9 | en cours (agent) |
| T1.9 | Supprimer la dépendance `cameralib` (remplacer par `tf.constant(K)[tf.newaxis]`) — élimine la seule dépendance `git+https` | §2.3 | **fait** — équivalence prouvée sur les 4 caméras de démo (mêmes valeurs, dtype, forme) |
| T1.10 | Épingler le commit VideoPose3D dans `setup_models.sh` ; supprimer `.gitmodules` (submodule fantôme) | §2.9 | **fait** — commit `1afb1ca0` épinglé, SHA256 des poids vérifié, `.gitmodules` supprimé, mention CC BY-NC ajoutée |

**Correctif connexe (hors liste) :** `postprocessing/evaluate_calibration.py:37-41` n'avait pas le repli `tomllib`-d'abord présent dans les deux autres lecteurs TOML ; il affichait une erreur à l'import et dégradait silencieusement (`tomllib = None`). Aligné sur le motif commun.

**Critère d'acceptation :** création des deux envs depuis zéro, puis exécution complète de la démo
MeTRAbs dans `env/calib.yaml` **sans torch installé**, avec un MRE final conforme à la référence.

---

### Phase 2 — Docker · ~1 j
*Dépend de : Phase 1*

| ID | Tâche |
|----|-------|
| T2.1 | `Dockerfile` : base `nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04`, micromamba, `env/calib.yaml`. apt : `ffmpeg libgl1 libglib2.0-0 git wget ca-certificates` |
| T2.2 | `Dockerfile.rtmpose` séparé (py3.8/torch), avec **mention explicite CC BY-NC 4.0** dans l'image et sa documentation |
| T2.3 | Entrypoint à **interpréteur absolu** (neutralise le piège `python3` → conda base) ; `MPLBACKEND=Agg`, `PYTHONUNBUFFERED=1`, `TFHUB_CACHE_DIR=/models/tfhub`, `OMP_NUM_THREADS` |
| T2.4 | Neutraliser le correctif WSL `LD_LIBRARY_PATH=/usr/lib/wsl/lib` (`calibrate.sh:43-44`) en conteneur |
| T2.5 | Rendre surchargeable l'appel `conda run -n metrabs_opensim` (`calibrate.sh:188`) via variable d'environnement |
| T2.6 | Échappatoire sur `core/gpu.py:43` : ne plus forcer `CUDA_VISIBLE_DEVICES=0` sans condition (écrase l'affectation du runtime ou de Slurm) |
| T2.7 | `compose.yaml` : volumes pour `input/`, `output/`, et le cache modèles ; argument de build `BAKE_MODELS` (image ~9 Go avec modèles vs ~5 Go sans, 1,2 Go au premier lancement) |
| T2.8 | `.dockerignore` (exclure `input/` 2,4 Go, `output/` 1,9 Go, `model/`, `third_party/`) |

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
| T3.5 | Unifier la triangulation : 7 implémentations → un seul `core.geometry.triangulate_dlt` | §2.6 |
| T3.6 | Unifier `parse_toml` : 4 variantes → une, **sans `eval()`** | §2.6, B4 |
| T3.7 | Source unique pour les constantes de squelette (supprimer les doublons de `visualize_results.py:46-91`) | §2.6 |
| T3.8 | Supprimer les 73 imports inutilisés et les 3 `import *` | §2.6 |
| T3.9 | Supprimer `singularity/` (obsolète, remplacé par la Phase 2) | §2.9 |

**Critère d'acceptation :** `pyflakes` propre ; la démo produit un MRE identique à ±1e-9 avant/après.

---

### Phase 4 — Config par session · ~1 j
*Dépend de : Phase 3*

| ID | Tâche | Référence |
|----|-------|-----------|
| T4.1 | Remplacer le `config.yaml` global par un objet de session écrit **une fois** dans `<output_dir>/session.yaml` | §2.5 |
| T4.2 | Dériver résolution et fps **des vidéos réelles** (`rtmlib_inference.py:144-145` les lit déjà et les jette) au lieu du 1920×1080/30 codé en dur | B6 |
| T4.3 | Déplacer les sidecars `.dropped.json` de `input/` vers `output/` → permet de monter `input/` en lecture seule | §2.8 |
| T4.4 | Supprimer la dérivation de `AID`/`PID`/`GID` par regex sur le nom de dossier | §2.7 |

**Critère d'acceptation :** deux sessions concurrentes sur des jeux de données différents n'interfèrent
plus ; `input/` montable en lecture seule ; `git status` reste propre après exécution.

---

### Phase 5 — Tests + CI · ~1,5 j
*Dépend de : Phase 4*

| ID | Tâche |
|----|-------|
| T5.1 | Figer les JSON de poses de la démo comme fixtures → toute la chaîne numérique testable **sans GPU ni téléchargement de modèle** |
| T5.2 | Test golden-run : linéaire → BA → évaluation sur `demo/`, MRE dans une tolérance |
| T5.3 | `procrustes_align` (`calib_linear.py:134`) — recouvrement de `(R,t,s)` connus à 1e-9, cas de réflexion inclus (`:155-156`) |
| T5.4 | **Jacobienne analytique vs différences finies** (`ba_jacobian.py:151`) — c'est le code le plus récent et le plus risqué, activé **par défaut** (`argument.py:74`) |
| T5.5 | Cohérence de triangulation (force la déduplication T3.5) |
| T5.6 | `get_bone_config(87)` — invariant des 27 os sans articulation virtuelle (documenté comme porteur dans les notes projet) |
| T5.7 | Aller-retour `load_poses`/`save_json` et export TOML (couvre la régression B1) |
| T5.8 | GitHub Actions, CPU seul |

**Critère d'acceptation :** `pytest` vert sur une machine sans GPU ; la CI passe sur un runner public.

---

### Phase 6 — Package installable · ~1,5 j
*Dépend de : Phase 5 (les tests protègent le déplacement des fichiers)*

| ID | Tâche |
|----|-------|
| T6.1 | `src/humancalib/` + `pyproject.toml` + `__init__.py` dans tous les sous-packages |
| T6.2 | Supprimer les 12 manipulations de `sys.path` |
| T6.3 | Corriger l'import frère nu `scale_scene.py:41` (double chargement de module) |
| T6.4 | Fusionner `tools/` et `utils/` ; `create_cameras_from_toml.py` est une **étape du pipeline**, pas un outil |
| T6.5 | `pip install -e .` dans les deux envs → supprime la duplication de `METRABS_BML87_INDICES` |
| T6.6 | Mettre à jour `README.md:556-561`, qui *documente* le hack `sys.path` comme intentionnel |

**Critère d'acceptation :** `pip install .` dans un env vierge, puis exécution de la démo depuis un
répertoire de travail arbitraire.

---

### Phase 7 — CLI Python unique · ~2-3 j
*Dépend de : Phase 6*

| ID | Tâche |
|----|-------|
| T7.1 | `humancalib.cli` à sous-commandes ; chaque étape a déjà un `main(argv)` appelable |
| T7.2 | Porter les 2 heredocs Python de `calibrate.sh` (lignes 259-290, 298-314) dans des modules versionnés et testables |
| T7.3 | Donner un vrai argparse à `run_ba.py` (13 positionnels → options nommées) |
| T7.4 | Remplacer les 3 protocoles de scraping de stdout par des valeurs de retour |
| T7.5 | Remplacer les appels `subprocess` internes par des appels en processus — **sauf** la reprise BA après OOM (`run_ba.py:49-86`), qui a besoin d'un processus neuf |
| T7.6 | Conserver un shim `calibrate.sh` de ~15 lignes pour que les commandes du `HOWTO.md` continuent de fonctionner |
| T7.7 | Garder en shell **uniquement** la bascule d'environnement `conda run` — seule vraie frontière de processus |

**Critère d'acceptation :** les commandes documentées dans `HOWTO.md` fonctionnent à l'identique ; le
golden-run de la Phase 5 reste vert.

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

## 6. Suivi

| Phase | État | Date |
|-------|------|------|
| 0 — Assainissement publication | **terminée** | 2026-09-13 |
| 1 — Bugs + envs épinglés | en cours | 2026-09-13 |
| 2 — Docker | à faire | |
| 3 — Nettoyage | à faire | |
| 4 — Config par session | à faire | |
| 5 — Tests + CI | à faire | |
| 6 — Package | à faire | |
| 7 — CLI Python | à faire | |
| 8 — logging + docs | à faire | |
