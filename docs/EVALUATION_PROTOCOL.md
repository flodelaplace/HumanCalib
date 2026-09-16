# Protocole d'évaluation de HumanCalib

Document de travail pour l'article et la thèse. Il fixe **avant** de regarder les
résultats ce qui est mesuré, comment, et avec quels paramètres, pour qu'aucun
réglage ne soit ajusté a posteriori sur les données de validation.

Code : `src/humancalib/evaluation/` (lecteurs de calibrations gold, métriques,
pilotes par dataset), tests : `tests/test_eval_*.py`. Résultats :
`D:\FLO\Calibration dataset\<Dataset>\<essai>\` (hors dépôt).

---

## 1. Questions

| # | Question | Niveau |
|---|---|---|
| Q1 | Quelle est la justesse géométrique des extrinsèques estimés, face à une calibration de laboratoire ? | Géométrie |
| Q2 | Quel est l'effet de cette calibration sur la cinématique articulaire et les paramètres spatio-temporels obtenus avec Pose2Sim ? | Aval |
| Q3 | Quelle est la fidélité : dispersion entre plusieurs enregistrements du même dispositif ? | Fidélité |
| Q4 | Qu'apportent les deux moteurs (MeTRAbs + Procrustes vs RTMPose + VideoPose3D), et à quoi le résultat est-il sensible (image de référence pour l'échelle, type de mouvement) ? | Sensibilité |

La littérature de calibration à partir de l'humain (Takahashi 2018, Lee 2022,
CasCalib, Xu 2021, Pätzold 2022, HSfM, Kineo, Yang 2026) s'arrête aux erreurs de
pose de caméra ou au MPJPE, sur des jeux de vision (Human3.6M, Panoptic,
EgoHumans) ou synthétiques. Aucune n'évalue la cinématique biomécanique ni ne
compare à une calibration de laboratoire de biomécanique ; aucune ne sépare
erreur de forme et erreur d'échelle, ni ne mesure la verticale. Le seul
précédent sur l'effet d'une erreur de calibration sur les angles est Pose2Sim
Part 1 (Pagnon et al. 2021 : ~1 cm de perturbation → < 0,5°), en simulation.

## 2. Données

| Dataset | Caméras | Vidéo | Gold | Qualité du gold | Référence cinématique |
|---|---|---|---|---|---|
| **BioCV** | 9 | 1920×1080, 200 fps, synchro matérielle | Mire de cercles + BA, alignée mocap, par participant | Bonne | `.mot` gold (`_RESULTS/_GOLD_BIOCV`), c3d |
| **LBMC** | 9 Miqus | 1088×1920 (portrait), 60 fps | QTM baguette (σ 0,19 mm), TOML Pose2Sim | Très bonne | c3d (IK à faire) |
| **IMOVE-23** | 10 Miqus | 1920×1080, 100 fps, marche ~130 s | QTM XML, 13 sessions | Bonne | `ik.mot` |
| **OpenCap** | 5 iPhone | 720×1280 (portrait), 60 fps | Damier au mur, intrinsèques génériques | Faible | `.mot` mocap |

Exclus : **Toulouse** (aucune calibration ni intrinsèque), **Fukuchi** (pas de vidéo).

Pièges de conversion identifiés (chaque lecteur a un test) :

* **BioCV** : le bloc 3×3 de la matrice monde→caméra vaut s·R (s ≈ 0,998). La
  caméra est lue comme `[R | t/s]`, qui projette à l'identique. On utilise
  `calibrationUpdate/` (alignement mocap raffiné).
* **LBMC** : distorsions vraisemblablement divisées par 64 à la conversion
  depuis QTM — à trancher par reprojection des marqueurs avant usage.
* **IMOVE-23, OpenCap** : k3 ≠ 0 (fort sur IMOVE 22/23), non représentable dans
  un TOML Pose2Sim à 4 coefficients : le writer refuse plutôt que de tronquer.
* **Orientation** : vidéos portrait (LBMC, OpenCap) et vues tournées (IMOVE) —
  la taille d'image doit correspondre aux intrinsèques.

**Validation de chaque lecteur** avant tout résultat : reprojection de points
3D connus avec la calibration lue, comparée aux projections fournies par le
dataset. BioCV P03, caméra 08, points d'axes ±1 m de `markers2D` : écart
0,35–1,9 px (une erreur de convention donnerait des centaines de pixels).

## 3. Principe d'isolation

* **Entrée de HumanCalib** : les vidéos et les **intrinsèques gold**. Seuls les
  extrinsèques sont estimés, ce qui est la contribution évaluée.
* **Convention commune** (`evaluation/rig.py`) : `x_cam = R·X + t`, monde→caméra,
  mètres, centre `C = −Rᵀt`. Toute calibration est convertie à la lecture.
* **Aval** : même vidéo, mêmes détections 2D, mêmes images, même configuration
  Pose2Sim ; seul le fichier de calibration change. Toute différence est
  imputable à la calibration.

## 3 bis. Noms des configurations évaluées (pour l'article)

Les noms « v1 » à « v4 » sont des étapes de développement ; l'article ne compare que les
configurations ci-dessous. Chacune est un jeu d'options de `humancalib run`.

| Nom | Moteur de pose | Options | Pour qui |
|---|---|---|---|
| **HumanCalib-M** (référence) | MeTRAbs | `--person_selection motion --scale_method segments --vertical_method walk` | Le meilleur compromis précision / temps (~12 min pour 9 caméras et 1250 images) |
| **HumanCalib-R (full)** | RTMPose + VideoPose3D | idem, à la fréquence native de la vidéo | Sans TensorFlow ; le plus précis de ce chemin, mais le plus lent |
| **HumanCalib-R (fast)** | RTMPose + VideoPose3D | idem, vidéo ramenée à ~50 Hz | Option rapide, précision moindre |
| *Ablations* | — | `--person_selection largest`, `--scale_method head`, `--vertical_method frame` | Montrent ce qu'apporte chaque élément |

Les trois configurations principales partagent la même sélection de personne, la même
correction de distorsion, la même échelle et la même verticale : seul le moteur de pose et
la fréquence d'images changent.

## 4. Exécution de HumanCalib (paramètres figés)

* Valeurs par défaut du pipeline : `frame_skip 10`, `conf_threshold 0.5`,
  détection automatique des images aberrantes, caméra de référence automatique,
  jacobienne analytique. Aucun réglage par essai.
* Deux moteurs : `metrabs` et `rtmpose` (RTMPose + VideoPose3D).
* Échelle : stature fournie par le dataset. Image de référence : règle
  automatique n'utilisant que les détections de HumanCalib (jamais le gold) —
  l'image où le plus de caméras voient tête et talons avec confiance, départagée
  par la confiance moyenne. Sa sensibilité est mesurée (§8).
* **Un échec compte** : le taux de réussite est un résultat. Un essai qui
  échoue n'est pas relancé avec d'autres paramètres ; s'il l'est pour une
  raison technique (panne, disque), c'est consigné.

## 5. Niveau 1 — géométrie

Notations : `d(R) = arccos((tr R − 1)/2)` ; Rᵢ monde→caméra ; Cᵢ centre.
Verticale : HumanCalib `−y` (repère OpenCV, y vers le bas) ; BioCV, LBMC `+z`.

**Principal — invariant à la similitude, sans alignement.** Pour chaque paire (i, j) :

* erreur de rotation relative : `d( (R̂ᵢR̂ⱼᵀ)(RᵢRⱼᵀ)ᵀ )` ;
* erreur de direction de translation relative, dans le repère de la caméra i :
  `∠( R̂ᵢ(Ĉⱼ−Ĉᵢ), Rᵢ(Cⱼ−Cᵢ) )`.

Rapportés en médiane et maximum, AUC à 1/2/5/10° de max(rotation, direction),
et médiane par caméra. Les C(C−1)/2 paires ne sont pas indépendantes (6C−7
degrés de liberté) : **pas de test statistique sur les paires**.

**Secondaire — ce que HumanCalib estime à partir de la personne.**

* Échelle : médiane des rapports de base `‖Ĉⱼ−Ĉᵢ‖ / ‖Cⱼ−Cᵢ‖` (et facteur
  d'Umeyama). Écart à 1 en %.
* Verticale : angle entre la verticale estimée et la verticale gold, comparées
  via la rotation de jauge estimée **à partir des seules orientations**
  (moyenne chordale de RᵢᵀR̂ᵢ).
* Forme : écart des rapports de base à leur médiane (%) ; erreurs de position
  et d'orientation après similitude 7 ddl (Umeyama), en leave-one-out.
* **Erreur absolue de bout en bout** : position (mm) et orientation (°) par
  caméra après alignement **4 ddl** (lacet autour de la verticale + translation,
  échelle fixée à 1), en leave-one-out. L'erreur d'échelle et de verticale y
  restent, volontairement.

Pourquoi pas une similitude 7 ddl comme mesure principale : elle absorbe
l'échelle, qui est justement estimée par la méthode ; et, sur 4 à 10 centres,
elle répartit l'erreur d'une caméra sur les autres (d'où le leave-one-out).
Pourquoi pas la base en mm comme invariant : elle ne l'est pas sous similitude,
elle mélange forme et échelle.

**Supplémentaire.** MRE en pixels (critère de convergence du BA, pas mesure de
justesse — Lee 2025 et Pätzold 2022 montrent des classements inversés).

## 6. Niveau 1 bis — erreur 3D induite par la calibration

* Marqueurs mocap (repère gold) projetés avec la calibration gold → 2D sans
  bruit → triangulés avec la calibration estimée → erreur 3D en mm (moyenne,
  95ᵉ centile), après alignement 4 ddl puis 7 ddl ; erreur sur les distances
  inter-marqueurs (invariante au rigide).
* Longueur connue : BioCV `calib_00/*.grids` (mire de cercles, pas 78,5 mm),
  LBMC damier (60 mm), triangulés avec la calibration estimée.

## 7. Niveau 2 — aval (Pose2Sim)

Deux exécutions Pose2Sim identiques (détection 2D, association, triangulation,
filtrage, augmentation, mise à l'échelle et IK OpenSim) : calibration gold vs
calibration HumanCalib.

* **Mesure principale** : différence appariée HumanCalib − gold, par degré de
  liberté ; biais et RMSE ; plan sagittal séparé des plans frontal et
  transverse.
* Contexte : chacune face au `.mot` de référence (MAE brut et cMAE, le modèle
  Pose2Sim n'étant pas celui du gold).
* Spatio-temporel (marche) : longueur et largeur de pas, vitesse — sensibles à
  l'échelle, contrairement aux angles.
* Écart-type des longueurs de segments triangulés (avant IK) : indicateur
  secondaire seulement.

Les erreurs indépendantes s'ajoutent en variance, avec une covariance non
nulle a priori : on ne soustrait pas « erreur HumanCalib − erreur gold » ; on
rapporte la différence appariée directe.

## 8. Niveau 3 — fidélité et sensibilité

* **Fidélité** : plusieurs enregistrements d'un même dispositif non déplacé.
  BioCV : une calibration par participant pour tous ses essais ; IMOVE : sujets
  partageant une calibration ({4,5,6}, {7,9,10}, {11,12,13}, {15,16,17}). Biais
  = moyenne face au gold ; précision = dispersion entre calibrations.
  Relancer la même séquence ne mesure que le non-déterminisme GPU de la pose
  (MRE 4,03–4,06 px observée) : fait une fois, pour le chiffrer.
* **Moteurs** : MeTRAbs vs RTMPose + VideoPose3D sur les mêmes essais. Un
  résultat défavorable à RTMPose + VideoPose3D est un résultat (il motive la
  recommandation de MeTRAbs), à condition que ce chemin ait tourné dans son
  domaine d'usage : VideoPose3D est un modèle temporel entraîné à 50 Hz, donc
  une vidéo à 100–200 Hz lui est donnée ramenée à ~50 Hz. Cette condition
  d'entrée est fixée ici, avant résultats, et appliquée à tous les essais ; ce
  n'est pas un réglage par essai.
* **Image de référence** : échelle et verticale recalculées sur plusieurs images
  valides du même essai.
* **Type de mouvement** : marche, course, saut sur place (CMJ), tapis (LBMC).
* Optionnel si le temps le permet : sous-ensembles de caméras, durée.
* **Méthode v2 — sélection géométrique de la personne** (`--person_selection
  geometric`), conçue après avoir vu les échecs de P06 et P10 (expérimentateur
  au premier plan de la caméra 08). Règle fixée avant tout run v2 : après une
  première calibration, triangulation robuste du sujet par consensus de
  caméras (sous-ensemble de 3 caméras le plus cohérent, puis caméras à moins de
  max(50 px, 5 × son erreur)), re-sélection dans chaque caméra de la détection
  la plus proche de la reprojection, recalibration complète. Seuils = ceux de
  la détection d'images aberrantes, aucun réglage par essai. Les résultats v1,
  échecs compris, restent les résultats de la méthode v1. Parce que la règle
  a été motivée par P06/P10, elle est aussi validée sur des participants jamais
  examinés (P04, P17, P18), en v1 et en v2.

## 9. Statistiques

* **Unité : le sujet** (essais imbriqués). Jamais les images mises en commun
  (autocorrélation ; limites d'agrément artificiellement serrées).
* Description : médiane, intervalle interquartile, intervalles de confiance
  bootstrap par sujet.
* Bland-Altman avec mesures répétées (Bland & Altman 2007) sur les sorties
  cinématiques.
* Équivalence : borne fixée a priori et justifiée (erreur de mesure du système
  à marqueurs, changement minimal détectable, ordre de grandeur de Pose2Sim
  Part 1), pas les seuils de McGinley et al. 2009, qui portent sur la fiabilité
  inter-séances et non sur la validité. Avec peu de sujets, intervalles de
  confiance plutôt que tests.

## 10. Plan d'expérience

À confirmer après le premier essai (temps de calcul mesuré) :

| Dataset | Sujets | Essais | Moteurs | Calibrations |
|---|---|---|---|---|
| BioCV | 6 (sans errata) | 3 WALK + 2 RUN + 1 CMJ | 2 | 72 |
| IMOVE-23 | 6, dont deux groupes à calibration partagée | marche (fenêtres de passage) | 2 | ~24 |
| LBMC | 2 | gait, sit-stand, mmh | 2 | 12 |
| OpenCap | 5 | walking | 2 | 10 |

BioCV P08 (sauts d'images) et P04 (WALK_05 absent) sont évités en premier choix.

## 11. Arborescence des résultats

```
D:\FLO\Calibration dataset\<Dataset>\<Participant>_<Essai>\
  input\Calib_scene.toml     intrinsèques gold (entrée HumanCalib)
  gold\Calib_gold.toml       calibration gold complète (Pose2Sim)
  gold\meta.json             provenance, stature
  metrabs\  rtmpose\         sorties HumanCalib par moteur
  eval\                      métriques (JSON/CSV)
```

## 12. Références vérifiées

* Lee et al., Extrinsic Camera Calibration From a Moving Person, RA-L 2022, 10.1109/LRA.2022.3192629
* Takahashi et al., Human Pose as Calibration Pattern, CVPRW 2018
* Pätzold, Bultmann, Behnke, GCPR 2022, arXiv 2209.07393
* Lee, Nishino, Nobuhara 2025, arXiv 2502.12546
* Yang et al. 2026, arXiv 2604.17567 ; Kineo, arXiv 2510.24464 ; HSfM, CVPR 2025, arXiv 2412.17806 ; CasCalib, arXiv 2405.06845 ; Xu et al., CVPR 2021, arXiv 2104.08568
* Pagnon et al., Pose2Sim Part 1, Sensors 2021, 10.3390/s21196530 ; Part 2, Sensors 2022, 10.3390/s22072712
* Uhlrich et al., OpenCap, PLoS Comput Biol 2023, 10.1371/journal.pcbi.1011462
* Kanko et al., J Biomech 2021, 10.1016/j.jbiomech.2021.110665 et 10.1016/j.jbiomech.2021.110414
* Needham et al., J Biomech 2022, 10.1016/j.jbiomech.2022.111338
* McGinley et al., Gait Posture 2009, 10.1016/j.gaitpost.2008.09.003
* Bland & Altman, J Biopharm Stat 2007, 10.1080/10543400701329422
* Zhang & Scaramuzza, trajectory evaluation, IROS 2018 ; Umeyama, TPAMI 1991, 10.1109/34.88573
* Challis & Kerwin, J Biomech 1992, 10.1016/0021-9290(92)90040-8

## 13. Journal

| Date | Étape |
|---|---|
| 2026-09-14 | Protocole rédigé. Lecteur BioCV validé par reprojection. Premier essai BioCV P03_WALK_01 (MeTRAbs) lancé. |
| 2026-09-15 | Batch BioCV marche (P03 P06 P09 P10 P13 P16 × WALK_01/02 × 2 moteurs). Coupure de la machine vers 3 h 25 (Docker « unexpected EOF ») : relance technique, consignée. Bugs corrigés puis essais relancés avec les mêmes paramètres : décalage d'une image entre caméras (P09, P16 : crash de la détection d'images aberrantes) ; métrique d'angle lisant 0° sur les matrices non orthonormées de l'étape linéaire RTMPose ; conteneur RTMPose sur le code du dépôt. Décision : les échecs dus à une personne au premier plan (caméra 08 de P06, P10) **restent des échecs**. |
| 2026-09-15 | Méthode v2 (sélection géométrique de la personne) implémentée et testée sur données synthétiques ; runs v2 MeTRAbs programmés après le test à 50 Hz, sur les 12 marches puis P04, P17, P18. |
| 2026-09-15 | Premier run v2 réel (P10_WALK_01, essai de développement) : caméra 08 112° → 13°, autres 2–4° → 0,5–0,8°. Diagnostic par oracle gold : la re-sélection choisit comme l'oracle, mais (1) les images où le sujet n'est pas détecté gardent la seule autre personne, et le seuil relatif de l'étape « images aberrantes » ne les écarte pas quand la médiane de la caméra est haute ; (2) un seul tour, sur une première calibration fausse pour la caméra 08. **Règle v2 révisée sur les essais de développement P10 et P06 uniquement** : image sans personne si la meilleure détection dépasse max(50 px, 5 × médiane de la caméra) face au sujet de consensus ; jusqu'à deux tours de re-sélection. P04, P17, P18 restent non examinés pour la validation. |
| 2026-09-15 | v2 révisée validée sur P10_WALK_01 (développement) : 2,5 px, 0,36° médiane / 1,1° max, 31 mm, 0 % mauvaise personne. Échelle : étude hors ligne de trois estimateurs face au gold (calibrations existantes, sans GPU) — tête sur une image (actuel) 11,2 % d'erreur absolue moyenne ; segments de jambe × ratio Drillis–Contini (0,491 × stature, Winter 2009) 2,1 % ; longueurs MeTRAbs métriques, sans stature, 2,5 % ; bras exclus (articulations virtuelles ≠ repères anatomiques, +5 à +10 %). **Méthode v3 = v2 + échelle par segments de jambe**, ratio de la littérature non ajusté ; pas de combinaison des estimateurs (ce serait un ajustement sur les données). L'estimateur MeTRAbs est rapporté comme variante sans stature. |
| 2026-09-15 | Verticale, étude hors ligne (10 calibrations) : une image (actuel) ~3° ; axe du corps médian 3–8° (inclinaison du tronc) ; plan du sol sur les appuis instable (0,1–37°, bande d'appuis trop étroite) ; **axe du corps médian moins sa composante le long de la direction de marche (donnée par les appuis) : médiane ~0,65°**, retenu. BA robuste (soft_l1 / cauchy, f_scale = 5 fixé d'après le bruit des keypoints) : négatif — soft_l1 dégrade les essais propres (0,44° → 1,06°) et casse certains essais, cauchy reste à l'étape linéaire ; BA inchangé. **v3 = v2 + échelle par segments de jambe + verticale sur toute la marche.** |
| 2026-09-16 | **Batch v3 terminé : 18 marches BioCV (9 caméras).** 14/18 essais à 0,26–0,82° de rotation relative médiane et 2,5–3,4 px, échelle |1,6| % médiane, verticale 0,55° médiane, forme 60 mm. 4 échecs (P03_W2, P06_W1, P10_W2, P18_W1), tous dus à une personne en trop. Validation (P04, P17, P18, jamais examinés avant de figer la v3) : 5/6 essais réussis. RTMPose + VideoPose3D reste à 6–15° même avec l'échelle et la verticale v3, à 50 comme à 200 Hz. **v4** (sélection initiale par mouvement) testée sur 4 essais de développement : P06_W1 11,1° → 1,3°, P18_W1 11,4° → 0,8°, sans dégrader P10_W1 (0,36°) ni P04_W1 (0,40 → 0,57°). P18 devient un essai de développement (règle v4 conçue après son échec) ; validation restante jamais examinée : P19, P24, P26, P27. |
| 2026-09-16 | **v4 sur les 18 marches** : rotation relative médiane 0,62° (v3 : 0,68°), **pire essai 2,61° contre 11,36°**, MRE 2,94 px, échelle 1,2 %, verticale 0,32°, forme 55 mm. Les 4 échecs de la v3 sont réparés (P03_W02 5,78 → 1,39° ; P06_W01 11,12 → 1,25° ; P10_W02 9,26 → 0,34° ; P18_W01 11,36 → 0,84°). Deux essais se dégradent : P17_W02 (0,73 → 2,61°) et P06_W02 (0,82 → 1,46°), à instruire avant de faire de la v4 le défaut. Densité du BA : aucune amélioration en passant de 130 à 650 images (0,72 / 0,72 / 0,72° sur P16_W02), pour 6 à 25 fois plus de temps — le BA converge, la limite est le bruit des keypoints (2–3 px) et les intrinsèques. **RTMPose corrigé : 200 Hz nettement meilleur que 50 Hz** (P16_W02 : 0,31° contre 2,24° ; 6,2 px contre 21 px ; 26 mm contre 973 mm), au prix de 27 min contre 5,7 min. |
| 2026-09-16 | **Biais de méthode corrigés sur le chemin RTMPose + VideoPose3D**, tous en sa défaveur : 2D jamais corrigée de la distorsion (k1 = −0,15 sur BioCV) alors que MeTRAbs l'était ; terme de longueur d'os désactivé par un seuil absolu sur une scène en unités arbitraires ; étape linéaire renvoyant [s·R | t] et non une rotation (relevé métrique par PnP, l'orthonormalisation directe déplaçant toutes les projections : MRE linéaire 234 → 1704 px) ; sélection de la personne non appliquée. Après correction, P16_WALK_02 : MRE linéaire 234 → 33 px, BA 107 → 21 px, rotation relative 8,2° → 2,2°, forme 2938 → 973 mm (MeTRAbs v3 : 0,72° et 66 mm). Reste : le poids du terme d'os retombe à zéro car quelques triangulations aberrantes font exploser la variance ; une mesure robuste serait nécessaire. |
| 2026-09-15 | Test RTMPose + VideoPose3D à 50 Hz (§8) programmé après le batch : vidéos réduites en gardant une image sur k à l'identique sur toutes les caméras, sorties dans `rtmpose_50hz`. |
| 2026-09-16 | **BA « poussé » : la grille ratio d'images × tolérance ne donne rien** (P16_W02, P09_W01, P13_W02, mêmes poses et même étape linéaire). Tolérance : de 1e-7 à 1e-9 l'écart est ≤ 0,02° et ≤ 0,01 px ; 1e-10 gagne 0,02° et 0,06 px sur un seul essai pour 13 fois le temps (107 s contre 8 s) ; 1e-12 ne converge pas en 25 min. Images : passer de 1/10 à toutes les images **dégrade** deux essais sur trois (P13_W02 0,26 → 0,44° ; P09_W01 0,68 → 0,76°) pour 18 à 35 fois le temps ; le troisième est stable (P16_W02 0,72 → 0,74°). Combiner les deux (1/2 des images et 1e-8) ne fait pas mieux que le réglage courant. **Conclusion : le BA est convergé à 1/10 d'images et 1e-7 ; la limite est le bruit des keypoints (2–3 px) et les intrinsèques fixes, pas l'optimiseur.** Aucun mode « optimisation poussée » ne sera proposé dans l'article ; le résultat négatif y est rapporté. |
| 2026-09-16 | **Cinquième biais contre RTMPose, trouvé en relançant les essais : la sélection par mouvement vidait la caméra de face.** L'oscillation des jambes est mesurée dans l'image pour RTMPose (en 3D pour MeTRAbs) : la caméra vers laquelle le sujet marche la voit raccourcie et ne déclare « marche » que sur 8 à 31 % des images, contre 60 à 85 % pour ses voisines. Comme l'étape linéaire exige chaque os visible dans **toutes** les caméras à la fois (`core/filtering.py`, `joints2orientations`), cette seule caméra vidait l'intersection : P09_WALK_01 n'avait plus une seule orientation valide et la calibration échouait (exit 1) ; P16_WALK_02 ne survivait que sur un chunk. Diagnostic : la caméra 04 de P09 n'a que 7 % de keypoints au-dessus du seuil de confiance après sélection, contre 92 % avec la sélection « plus grande boîte » ; MeTRAbs, lui, garde 94 % sur la même caméra. **Correctif (`gate` adaptatif)** : une caméra suit la fenêtre des autres au lieu de son propre verdict si (1) elle déclare la marche moins de 0,7 fois le taux médian des caméras **et** (2) elle voit toujours quelqu'un bouger (quartile bas de la vitesse ≥ 0,4 × seuil). Les deux conditions sont nécessaires : le taux seul ne sépare pas la caméra de face (0,51–0,79 du médian) de celle qui n'a qu'un opérateur assis (0,63–0,77), le quartile de vitesse si (0,29–0,37 contre 0,03–0,12). Mesuré contre l'oracle gold sur 7 marches de développement : RTMPose gagne sur les deux axes (P09 63→75 % d'images gardées et 87,1→89,1 % de bonnes personnes ; P16 66→76 % et 87,9→89,4 % ; P13 67→74 % et 89,9→90,8 %), **MeTRAbs est strictement inchangé** — vérifié sur les 18 marches, 0 caméra concernée, donc aucun résultat MeTRAbs à refaire. Retirer la barrière partout, au lieu de l'adapter, coûterait 6 à 7 points à MeTRAbs (96,1→89,3 ; 98,1→92,0 ; 97,0→91,3). |
| 2026-09-16 | **Les deux régressions de la v4 instruites (P17_WALK_02, P06_WALK_02) : ce n'est pas la personne, c'est le volume couvert.** Diagnostic par oracle gold : la v4 choisit *mieux* la personne que la v3 sur ces deux essais — 98–100 % de bonnes détections dans chaque caméra, 0 % de mauvaise personne, même bruit de keypoints (~2 px), et *plus* d'images vues (P17 caméra 03 : 79 → 95 % ; P06 caméra 00 : 83 → 98 %). La dégradation est déjà présente à l'étape linéaire (P17 2,85 → 4,67° ; P06 1,09 → 3,07°), le BA n'en rattrape qu'une partie (0,73 → 2,61° ; 0,82 → 1,46°) : c'est un problème de **conditionnement**, pas d'optimisation. Cause mesurée sur la trajectoire du bassin triangulée avec la calibration gold : la sélection par mouvement ne garde que la fenêtre de marche et supprime les phases debout, les demi-tours et les pas latéraux, qui portaient la diversité spatiale. P06_WALK_02 : étendue transversale 2,67 m et deuxième axe de l'ACP 0,42 m en v3 (parcours 18,2 m), contre 0,21 m et 0,04 m en v4 (parcours 9,3 m) — le deuxième axe s'effondre d'un facteur dix. P17_WALK_02 : 0,46 → 0,10 m. Contrôle sur P18_WALK_01, où la v4 gagne : l'« étendue » de la v3 (27 m, parcours 92 m) n'est pas de la couverture mais les triangulations aberrantes de la mauvaise personne. **Piste à tester avant de faire de la v4 le défaut : se servir du mouvement pour identifier la personne (quelle détection) sans restreindre les images à la fenêtre de marche**, la re-sélection géométrique prenant ensuite le relais hors marche. |
| 2026-09-16 | **Échelle : le biais de +5 % de RTMPose vient de la convention des keypoints, pas de la géométrie.** Vérification sans calibration estimée : les jambes sont triangulées avec les caméras **gold** (l'échelle y est juste par construction) et comparées au rapport de Drillis–Contini (cuisse 0,245 H, jambe 0,246 H). RTMPose mesure 0,950 ± 0,020 du modèle (8 marches propres ; P06 et P10 exclues, leurs extractions `rtmpose` d'origine sont polluées par le passant de la caméra 08), MeTRAbs 0,988 ± 0,015 (18 marches). Comme le facteur d'échelle vaut 0,491 H / longueur mesurée, cela prédit +5,2 % pour RTMPose et +1,2 % pour MeTRAbs — **et c'est bien ce qu'on observe : sur les 18 marches MeTRAbs, le rapport d'échelle mesuré contre le gold est l'inverse du rapport de jambe, corrélation 0,969, écart médian 0,66 %, maximum 1,26 %.** Cause localisée en comparant les deux moteurs triangulés avec le gold sur les mêmes images : la hanche Halpe26 de RTMPose est **85 mm en avant** et 32 mm en dessous du centre articulaire de MeTRAbs (décalage latéral 6–12 mm seulement), convention COCO/Halpe qui annote la face avant du bassin et non la tête fémorale ; la cheville est 20 mm plus bas. D'où deux structures d'erreur opposées : MeTRAbs cuisse **+8 à +13 %** et jambe **−10 à −15 %**, qui *se compensent* ; RTMPose cuisse −4 à −7 % et jambe −1 à −7 %, qui *s'additionnent*. La bonne échelle de MeTRAbs est donc en partie fortuite. **Aucune correction appliquée** : une constante par moteur serait ajustée sur BioCV seul (un labo, neuf caméras) ; décision de l'utilisateur de ne rien corriger avant d'avoir IMOVE, OpenCap et LBMC. Plancher de la méthode, même avec une constante parfaite par moteur : 1,5 % d'écart-type (MeTRAbs), 2,1 % (RTMPose). Piste de vérification absolue non exploitée : BioCV fournit `markers.c3d` pour les 18 marches (aucun lecteur c3d installé dans l'environnement). |
| 2026-09-16 | **Vérification absolue de l'échelle avec les marqueurs BioCV (`markers.c3d`, ezc3d installé).** Les centres articulaires Visual3D fournis par le jeu de données servent de référence : vérifié que `LEFT_KNEE` est exactement le milieu des épicondyles et `LEFT_ANKLE` le milieu des malléoles (0,0 mm d'écart) ; la hanche vient de la régression Visual3D (les marqueurs du bassin sont à zéro dans 19–34 % des images de marche, occlusion — **images invalides masquées**, il reste 45–66 % d'images utilisables, largement assez pour une médiane). Décomposition du biais d'échelle en deux parts indépendantes : (1) **le modèle de Drillis–Contini lui-même surestime la jambe de 1,6 %** (écart-type 2,4 % sur 18 marches) — part commune aux deux moteurs, irréductible sans anthropométrie individuelle ; (2) la convention des keypoints : MeTRAbs cuisse **+5,1 %** et jambe **−4,2 %** face à l'anatomie réelle, qui se compensent en partie (+0,7 % net, écart-type 2,1 %) ; RTMPose cuisse **−9,7 %** et jambe +2,7 % (−3,9 % net, écart-type 1,4 %). Biais d'échelle prédit par ces mesures : **+0,9 % pour MeTRAbs, +5,8 % pour RTMPose**, contre +1,1 % et +5,0 % observés face au gold — mécanisme confirmé de bout en bout. À noter : RTMPose est **plus répétable** (1,4 %) que MeTRAbs (2,1 %) tout en étant plus biaisé ; c'est donc lui qui se prêterait le mieux à une constante par moteur, si elle était un jour justifiée sur d'autres jeux de données. Réserve : ces « vraies » longueurs restent celles d'un modèle marqueurs (le README de BioCV le dit lui-même), pas une vérité anatomique. |
