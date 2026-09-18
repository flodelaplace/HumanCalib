# 07 — Notes de rédaction (pour reprise par Claude Science)

Brouillon de structure et messages clés, à partir des résultats de 03. Les chiffres marqués
**[à jour ?]** dépendent de runs en cours (nuit du 18 au 19/09) : les reprendre dans 03 ou dans
les tableaux de `~/humancalib_eval/article/` avant d'écrire. Langue de l'article : à décider
(anglais probable) ; ces notes sont en français.

## Titre (pistes)
- « Calibrating multi-camera motion capture from a walking person: accuracy against five
  reference calibrations »
- « HumanCalib: extrinsic calibration of markerless motion-capture rigs from human walking »

## Message central (une phrase)
Quelques secondes de marche d'une personne suffisent à calibrer un rig multi-caméras sans mire :
sur cinq jeux de données et ~80 calibrations, l'erreur de forme reconstruite dans le volume de
travail est de quelques millimètres, l'orientation relative des caméras de 0,4 à 2°, aucune
calibration n'échoue avec MeTRAbs, et un critère de reprojection sans référence détecte tous
les échecs.

## Plan proposé
1. **Introduction** — la calibration à la mire est la contrainte pratique du markerless
   multi-caméras (Pose2Sim, OpenCap) ; la calibration par la pose humaine existe (Takahashi 2018,
   Lee 2022, Pätzold 2022, CasCalib…) mais n'est pas évaluée contre des calibrations de référence
   en biomécanique, ni sur des configurations variées, ni avec une échelle métrique. Objectifs :
   Q1 précision contre référence, Q2 impact sur la reconstruction 3D (et angles, si niveau 2),
   Q3 fiabilité et critère sans référence.
2. **Méthode** — voir 01_METHODE.md (chaîne v4, deux moteurs, échelle depuis la stature).
3. **Données** — 02_DATASETS.md : BioCV, IMOVE-23, OpenCap, LBMC, COMFI ; tableau des rigs.
   Préparation : fenêtres, synchronisation (OpenCap : synchro vidéo-mocap par caméra de
   Mesh2Sim, validée par plateformes de force ; COMFI : horodatages ; autres : matérielle).
4. **Métriques** — 04 §2 : rotation relative par paire (principale, indépendante du repère),
   position 7 ddl et 4 ddl, échelle, verticale, **PA-MPJPE induite par la calibration** (marqueurs
   mocap projetés avec la gold, retriangulés avec notre calibration), taux d'échec, MRE.
5. **Résultats** — par question (voir ci-dessous).
6. **Discussion** — voir « Messages de discussion ».
7. **Limites et recommandations pratiques.**

## Résultats — points à écrire
- **Q1 précision (MeTRAbs)** : BioCV 0,62° [0,48–0,81] (18) ; IMOVE 0,42–0,65° (2, **[à jour ?]**
  11 sujets en cours) ; OpenCap 1,84° [1,57–1,91] (18) ; LBMC 1,47 / 3,08° (tapis) ; COMFI
  rectiligne 0,68–1,19°, circulaire 1,3–2,1° (**[à jour ?]** 14 participants en cours).
  Échelle 1–2 % (jambes ; RTMPose jambes+tronc), verticale < 1°.
- **Q2 reconstruction** : PA-MPJPE induite par la calibration (médianes) : BioCV 8,9 mm,
  IMOVE 7,5 mm, OpenCap 4,6 mm, LBMC 3,4 mm ; COMFI ~40 mm d'écart à la gold, mais **face à la mocap notre calibration bat la gold ArUco dans
  28/28 essais** (PA-MPJPE par image 53,9 contre 56,3 mm, Wilcoxon p < 10⁻⁴) : résultat fort à mettre en avant. **La rotation relative surestime l'impact pratique** : 1,8° d'orientation
  sur OpenCap donnent < 7 mm d'erreur de forme là où la personne marche (compensation des
  erreurs d'orientation autour du volume de travail).
- **Q3 fiabilité** : 0 échec MeTRAbs ; RTMPose 4/16 échecs complets + 1 partiel (BioCV).
  Répétabilité : OpenCap 0,03–0,16° entre deux marches d'un même rig (erreur systématique par
  session, pas du bruit) ; BioCV 0,40°. **Critère d'acceptation sans référence** : MRE de la pire
  caméra ≤ ~15 mrad (MRE / focale) et ≤ 3,5 × la médiane des caméras → détecte 100 % des échecs
  complets et partiels, sans fausse alarme (61 calibrations). Mais le MRE ne prédit pas la
  précision fine entre calibrations réussies (ρ = −0,07, sauf dans un même labo, BioCV ρ = 0,8).
- **Ablations** : plus d'images / BA plus long / cumul d'essais : sans effet ; 200 vs 50 Hz :
  sans effet ; synchronisation : décisive (OpenCap : 4–8 images de décalage doublent le MRE) ;
  géométrie : arc de 5 caméras A 0,51° vs B 1,39° ; tapis : rotations mal contraintes ;
  **durée de marche nécessaire [à jour ?]** (`duration_results_best.csv` ; BioCV P09 : 0,5 s
  2,36°, 1 s 1,05°, 2 s 0,89°, 4 s 0,71° = essai entier) ; marche rectiligne meilleure que
  circulaire sur COMFI (à expliquer : trajectoire circulaire plus loin des paires de caméras ?).

## Messages de discussion
1. **Ce qui limite n'est pas la quantité de données** mais ce qui est systématique : intrinsèques
   (génériques sur OpenCap), synchronisation, couverture spatiale du trajet, qualité même de la
   référence (OpenCap damier, COMFI ArUco). Plus d'images ou de participants sur le même trajet
   n'aident pas ; un trajet qui couvre le volume aide.
2. **Les métriques d'orientation des caméras sont trompeuses pour l'usage biomécanique** : ce qui
   compte est l'erreur de reconstruction dans le volume de travail (PA-MPJPE), millimétrique.
3. **Une calibration de référence n'est pas une vérité** : sur OpenCap et COMFI, la « gold » n'est
   pas plus cohérente avec les images que notre calibration ; tester hors échantillon ou contre la
   mocap (jamais sur les points qui ont servi à calibrer).
4. **Échelle depuis la stature** : 1–2 % d'erreur, plancher fixé par la variabilité individuelle
   des proportions (~3 %, ANSUR II) ; choix des segments selon la définition des points du
   détecteur (hanche RTMPose antérieure → ajouter le tronc).
5. **Choix du détecteur** : MeTRAbs (3D natif, centres articulaires) robuste ; RTMPose +
   VideoPose3D aussi précis quand il réussit mais ~25 % d'échecs (cause non élucidée,
   ambiguïté d'orientation du 3D relevé suspectée) → à utiliser avec le critère d'acceptation.

## Recommandations pratiques (encadré possible)
- Marcher en traversant tout le volume (aller-retour, diagonales), pas sur place ; sur tapis,
  marcher autour du tapis pour la calibration.
- Caméras synchronisées à l'image près ; intrinsèques calibrées par caméra si possible.
- 2 s de marche vue par toutes les caméras suffisent dans un labo moyen (BioCV) ; 10–15 s couvrant le volume dans un grand espace (IMOVE) ; au-delà, c'est la couverture spatiale qui compte (03 §12).
- Contrôler le MRE de la pire caméra (critère ci-dessus) ; refaire un essai sinon.
- Donner la stature ; attendre ~1–2 % d'erreur d'échelle.

## Figures à produire (voir `~/humancalib_eval/article/`)
1. Rigs 3D gold vs nous, un essai par jeu (existent dans `D:\FLO\Calibration dataset\Figures`).
2. Nuage par essai de la rotation relative, par jeu (échecs visibles).
3. PA-MPJPE par jeu (boîtes), et rotation vs PA-MPJPE.
4. MRE (pire caméra, mrad) vs erreur : le critère d'acceptation.
5. Durée de marche vs erreur.
6. Échelle : jambes vs jambes+tronc par moteur.

## Ce qui n'est pas fait (à signaler dans la rédaction ou à compléter)
- Niveau 2 (angles articulaires Pose2Sim gold vs nous) : non lancé ; marge d'équivalence à fixer
  (2° McGinley recommandé).
- IMOVE RTMPose ; répétabilité IMOVE (split) ; synchro manuelle OpenCap (gain attendu ~0,1°).
