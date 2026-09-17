# 04 — Plan des expériences, métriques et statistiques

Établi le 17/09/2026 avant les runs définitifs. Les métriques **principales** sont figées
ici ; tout le reste est secondaire ou ablation. Deux points restent à trancher par
Florian (§6).

## 1. Questions de l'article

1. Quelle précision géométrique atteint la calibration par la marche, contre une
   calibration de référence, dans cinq situations d'acquisition ?
2. Cette précision suffit-elle pour la cinématique articulaire : les angles obtenus avec
   notre calibration sont-ils équivalents à ceux obtenus avec la calibration de référence ?
3. La méthode est-elle fiable et répétable ; comment l'utilisateur sait-il, sans
   référence, que sa calibration est bonne ?

## 2. Métriques

### Principales (5)
1. **Rotation relative** médiane par essai, avec pire paire (indépendante du repère).
2. **Position 4 ddl en mm** (notre échelle et notre verticale : ce que l'utilisateur obtient).
3. **Erreur 3D volumétrique par marqueurs** : marqueurs mocap projetés avec la gold,
   triangulés avec notre calibration, écart 3D en mm sur le volume (aucun bruit de pose).
   Jeux : BioCV, LBMC, COMFI, IMOVE (trc de cinématique directe). **Nouveau, à coder.**
4. **RMSD d'angles articulaires** entre Pose2Sim-gold et Pose2Sim-nous, mêmes 2D, 13 ddl,
   avec test d'**équivalence** (TOST) et IC 90 %.
5. **Taux d'échec** avec IC (Clopper-Pearson) et sa **détection par le MRE** et la pire
   caméra.

### Secondaires
- Direction de translation, forme 7 ddl, erreur d'échelle, erreur de verticale.
- RMSE d'angles contre la mocap des deux bras (l'effet de la calibration face à l'erreur
  du markerless lui-même) ; Bland-Altman sur les amplitudes.
- Écart 3D des points triangulés (mêmes 2D, gold contre nous), mm par articulation.
- Dispersion cuisse+tibia sur la séquence (critère non optimisé).
- Répétabilité : inter-essai même participant (BioCV, OpenCap), split en deux
  allers-retours (IMOVE, poses réutilisées, coût = BA seulement), inter-participant
  même rig (LBMC n = 2, COMFI si rig unique) ; gain de la moyenne de deux calibrations.
- Généralisation hors essai : calibration sur A, MRE et segments sur B.
- Corrélation MRE final ↔ rotation contre gold sur tous les essais (~60 points) ;
  validation croisée par caméra (recalibrer sans elle, mesurer sa reprojection).

### Ablations (en grande partie faites)
BA / sans BA ; v1 → v4 ; nombre d'images ; 200 vs 50 Hz ; 5 vs 9 caméras ; moteurs ;
jambes vs jambes+tronc ; **durée de marche nécessaire** (tronquer à 2, 5, 10, 20 s ;
poses déjà calculées) ; **couverture spatiale** (tapis / couloir / cercle) chiffrée.

### Praticité
Temps de calcul, secondes de vidéo utilisées, matériel nul ; incertitude de la gold
elle-même (résidu wand).

## 3. Design du niveau 2 (angles)

- Pose2Sim 0.10.40 (env `fast_sam_3d_body`), 2D RTMPose de Pose2Sim, **mêmes 2D** pour
  les deux bras ; triangulation avec (a) gold, (b) HumanCalib v4 ; IK OpenSim ; 13 ddl
  définis dans 02 ; références `_EXPORT_ARTICLE/gold/`.
- Critère principal : RMSD (b) − (a) par ddl, résumé par la moyenne des ddl sagittaux
  (hanche, genou, cheville) puis chaque ddl.
- Hypothèse d'équivalence, marge δ fixée avant (§6). Statistique : TOST apparié par essai
  (α = 0,05), IC 90 % de la différence ; participant comme groupe quand il a 2 essais
  (BioCV : moyenne par participant ou modèle mixte).
- Jeux : **IMOVE** principal (angles fournis, synchro matérielle, 11 sujets indépendants,
  grand espace) ; **BioCV** (angles fournis `ik_gold_modele_bath.mot`, fenêtre
  `RELIABLE_WINDOWS.csv`, 18 essais / 9 participants) ; **OpenCap** secondaire (angles
  fournis, recalage temporel mocap/vidéo nécessaire, bruit de synchro) ; COMFI selon
  le contenu reçu.

### Taille d'échantillon (TOST, α = 0,05, puissance 0,8) : n ≈ 6,2 σ_d² / δ²

| σ_d (écart-type des différences appariées) | δ = 1° | δ = 2° |
|---|---|---|
| 0,5° | 5 (plancher pratique) | 5 |
| 1° | 7 | 5 |
| 1,5° | 14 | 5 |
| 2° | 25 | 7 |
| 3° | 56 | 14 |

σ_d est inconnu : **pilote sur 3 essais IMOVE**, puis n fixé avant de continuer. Avec
δ = 2° et σ_d ≤ 2,6°, les 11 essais IMOVE suffisent ; BioCV (18) et OpenCap (9)
s'ajoutent comme réplications dans d'autres rigs.

## 4. Runs à lancer (GPU, une machine)

| Bloc | Contenu | Durée |
|---|---|---|
| OpenCap article | 9 sujets, fenêtres du jeu, **sans décalages** ; option 3 marches/sujet pour la répétabilité | 2 h (1 marche) ou 6 h (3) |
| IMOVE MeTRAbs | 9 sujets restants | 9 h |
| IMOVE RTMPose | 11 sujets | ~3 h |
| IMOVE split-half | 11 × 2 calibrations sur poses existantes | ~2 h de BA |
| BioCV | RTMPose P18_W02 | 15 min |
| Niveau 2 pilote | 3 essais IMOVE, deux bras | ~1,5 h |
| Niveau 2 complet | IMOVE 11 + BioCV 18 + OpenCap 9 | ~15 h |
| Volumétrique marqueurs | BioCV 18, LBMC 2, IMOVE, COMFI | CPU, à coder |
| COMFI | à définir à réception | — |

Deux à trois nuits, hors COMFI. Ordre proposé : OpenCap article → pilote niveau 2 →
IMOVE MeTRAbs → niveau 2 complet → IMOVE RTMPose → ablations CPU.

## 5. Figures prévues
1. Nuage par essai de la rotation relative, un panneau par jeu, échecs marqués.
2. Rigs 3D gold/nous pour un essai représentatif par jeu (existent : figures redressées,
   `Figures/`).
3. Carte volumétrique de l'erreur 3D (marqueurs) sur BioCV et LBMC.
4. Angles : Bland-Altman et séries temporelles gold/nous/mocap pour un essai ; forest
   plot des différences par ddl avec la marge d'équivalence.
5. MRE contre rotation gold : le critère d'acceptation sans référence.
6. Durée de marche et couverture spatiale contre erreur.

## 6. À trancher (Florian)
- Marge d'équivalence : **2°** (McGinley 2009, recommandé en principal) ou 1° ; ou 2° en
  principal et 1° en complémentaire.
- OpenCap : 1 marche par sujet ou 3 (répétabilité) ?
- Lancer le pilote niveau 2 dès que possible ?
