# 08 — Niveau 2 : effet de la calibration sur les angles articulaires (méthode)

Question : **la calibration obtenue par la marche change-t-elle la cinématique articulaire par
rapport à la calibration de référence ?** Le niveau 1 mesure la géométrie des caméras ; ici on mesure
ce qui intéresse le biomécanicien, les angles.

## 1. Principe : ne faire varier que la calibration

Pour chaque essai, la chaîne **Pose2Sim** (version 0.10.43, la vraie, pas une réimplémentation) est
exécutée **deux fois**, sur les **mêmes détections 2D**, en ne changeant que le fichier de
calibration :

1. `poseEstimation` — RTMPose Halpe26, une seule fois par essai, sur GPU. Les détections sont
   ensuite **partagées** par les deux variantes (lien, pas copie) : c'est ce qui garantit que la
   seule différence est la calibration.
2. `triangulation` → `filtering` → `markerAugmentation` (LSTM Stanford) → `kinematics`
   (scaling + IK OpenSim), avec la configuration Pose2Sim par défaut, pour chaque variante :
   - **gold** : la calibration de référence du jeu ;
   - **hc** : la nôtre, échelle et verticale comprises.

Les paramètres non géométriques sont identiques : stature du participant, fréquence, filtrage,
modèle OpenSim, réglages de triangulation.

## 2. Repère commun, sans utiliser la référence

Deux constats, mesurés sur un essai OpenCap avant de lancer la série :

- **Pose2Sim n'applique aucune rotation avant l'IK** et attend la verticale sur l'axe Y (convention
  OpenSim). HumanCalib sort en Z vertical : sans conversion, l'IK est aberrante (bassin faux de 84°).
- **L'augmentation de marqueurs LSTM n'est pas invariante par rotation** : elle normalise par la
  hanche et la stature, sans recaler l'orientation. Une rotation de 30° autour de la verticale
  déplace les angles articulaires de 0,20° en médiane, jusqu'à 3,6° au subtalaire et 7° en
  prono-supination. **C'est un résultat publiable en soi**, et une mise en garde pour les
  utilisateurs de Pose2Sim dont la calibration n'a pas une orientation canonique.

Conséquence méthodologique : les points 3D filtrés de **chaque** variante sont amenés dans un
**repère canonique déduit de ses propres données**, avant l'augmentation de marqueurs :

- verticale = direction moyenne cou − chevilles du sujet ;
- axe X = direction de marche (axe principal de la trajectoire du bassin, orientée par le
  déplacement net) ;
- origine = bassin à la première image, sol (2ᵉ centile de la hauteur des chevilles) à zéro.

Ce recalage est calculé séparément pour la gold et pour nous, **sans jamais utiliser la référence**.
Il ne masque pas nos erreurs : notre erreur de verticale reste visible, puisque notre verticale est
estimée sur nos propres points.

## 3. Ce qui est comparé

- **Angles articulaires** (hanche 3, genou, cheville, subtalaire, lombaires, membres supérieurs) :
  RMSD entre les deux variantes, par essai et par degré de liberté, plus le biais moyen.
- **Position et orientation globales du bassin** : comparables grâce au repère canonique.
- **Contre l'optoélectronique** (BioCV, IMOVE, OpenCap, qui ont une IK mocap de référence) : chaque
  variante est comparée à l'IK mocap, ce qui situe l'effet de la calibration par rapport à l'écart
  markerless–mocap.

## 4. Plan statistique (figé avant les résultats)

- **Unité** : l'essai. **Mesure** : RMSD par degré de liberté sur tout l'essai.
- **Degrés de liberté principaux (9)** : bassin (3), hanche (3), genou, cheville, subtalaire,
  moyennés gauche-droite.
- **Marge d'équivalence : 2°** (seuil clinique usuel en analyse de la marche, McGinley et al.).
- **Critère** : équivalence déclarée si la borne haute de l'intervalle de confiance à 95 % du RMSD
  moyen entre essais reste sous 2°, pour chacun des 9 degrés de liberté ; TOST sur le biais en
  complément ; correction de Bonferroni sur les 9 degrés de liberté.
- **Taille d'échantillon** : d'après le premier essai (RMSD 0,1 à 1,8°), 2 à 17 essais suffisent
  selon l'hypothèse retenue sur la variabilité. Les 77 essais disponibles permettent de conclure
  **jeu par jeu** (BioCV 18, OpenCap 18, COMFI 28, IMOVE 11) ; LBMC (2) reste descriptif.

## 5. Résultat préliminaire (1 essai, OpenCap subject10 walking1)

| Mesure | Valeur |
|---|---|
| Angles articulaires, gold contre nous | médiane 0,12°, moyenne 0,38°, pire 1,83° (genou) ; **56/56 ddl sous 2°** |
| Hanche / genou / cheville | 0,56–0,72° / 1,34–1,83° / 1,06–1,30° |
| Bassin (orientation / position) | 0,44–0,53° / 2–14 mm |
| Face à la mocap | gold 4,90°, nous 5,03° (médiane sur 15 ddl), écart entre variantes 0,54° |

Lecture : l'effet de la calibration est environ **dix fois plus petit** que l'écart entre le
markerless et l'optoélectronique, qui vient du modèle, du jeu de marqueurs et de la détection.
À confirmer sur la série complète ; le recalage temporel avec la mocap doit être repris avec les
décalages connus (Mesh2Sim) plutôt que par corrélation.

## 6. Où sont les fichiers

- Scripts : `~/humancalib_eval/level2_prepare.py` (montage des essais), `level2_run.py` (chaîne
  Pose2Sim et repère canonique), `level2_batch.sh` (lot), `level2_compare.py` (écarts d'angles).
- Sorties : `D:\FLO\Calibration dataset\level2\<jeu>_<essai>\{gold,hc}\trial\kinematics\*.mot`.
