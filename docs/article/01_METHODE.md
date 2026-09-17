# 01 — La méthode évaluée

HumanCalib estime les **extrinsèques** (rotation, position) de N caméras fixes à partir
d'une personne qui marche dans la scène, sans mire. Les intrinsèques sont supposées
connues (fournies par le fabricant, une calibration préalable ou le jeu de données).
Le résultat est une calibration au format Pose2Sim (TOML), métrique et orientée avec la
verticale vers le haut.

## 1. Chaîne de traitement (version figée « v4 »)

1. **Estimation de pose par caméra**, deux moteurs interchangeables :
   - **HumanCalib-M** : MeTRAbs (squelette `bml_movi_87`, 87 points dont centres
     articulaires ; 2D et 3D par image). Les 2D sont non distordus avec les intrinsèques.
   - **HumanCalib-R** : RTMPose (Halpe26, 2D) puis VideoPose3D (relèvement 3D, entraîné à
     50 Hz ; les vidéos sont décimées à ~50 Hz par sélection d'images, jamais par timestamp).
2. **Sélection de la personne** (`--person_selection motion`) : dans chaque caméra, on
   garde le candidat qui marche (vitesse 2D), avec une **porte adaptative** : une caméra
   où la personne vient de face (peu de mouvement 2D apparent) n'est pas vidée si son
   rythme de marche est cohérent avec les autres. Introduite parce que la porte fixe
   supprimait la caméra frontale avec RTMPose.
3. **Calibration linéaire par tronçons** (`calib_linear`) : orientations relatives à partir
   des os 3D vus dans toutes les caméras (Procrustes pour MeTRAbs), positions par les
   projections 2D ; tronçons de 1000 images, le meilleur est gardé.
4. **Rejet d'images aberrantes** par caméra, puis **ajustement de faisceaux** (BA) sur les
   2D, poids auto-équilibrés ; la référence est choisie automatiquement.
5. **Orientation** : la verticale est estimée sur toute la marche (axe du corps moyen,
   composante le long de la direction de marche retirée). Une seule image donnait 0,3 à 12°.
6. **Échelle métrique depuis la stature** du participant (voir §2).
7. Export TOML Pose2Sim ; figures et animation 3D.

Les noms de configurations (v1 à v4, échelle « seg ») sont définis dans
`docs/EVALUATION_PROTOCOL.md` §3 bis. **v4 = sélection par le mouvement + échelle par
segments + verticale sur la marche** ; c'est la seule version évaluée dans l'article.

## 2. Échelle métrique depuis la stature

Principe : les segments sont triangulés sur toutes les images vues par assez de caméras,
leurs longueurs médianes sont sommées et comparées à une fraction de la stature issue de
la littérature. Aucune constante n'est ajustée sur nos données.

| Moteur | Segments | Fraction de la stature | Pourquoi |
|---|---|---|---|
| MeTRAbs | cuisse + tibia (centres hanche, genou, cheville) | 0,245 + 0,246 = **0,491** (Drillis & Contini ; de Leva 1996 donne 0,492 pour des centres articulaires) | ses hanches sont des centres articulaires |
| RTMPose | cuisse + tibia + tronc (milieu des hanches → cou) | 0,491 + 0,288 = **0,779** | sa hanche Halpe26 est ~85 mm en avant du centre : cuisse trop longue, tronc trop court, les deux se compensent |

Résultats et raisons détaillées dans 03 §6 et 05. Le plancher de cette approche est la
variabilité individuelle des proportions (écart-type ~3 % du rapport jambes/taille dans
ANSUR II) : on ne peut pas attendre mieux que ~1,5 % sans mesure du sujet.

## 3. Ce que la méthode suppose

- Une personne **qui marche debout** et se déplace dans la scène. Une personne sur une
  poutre en déséquilibre (démo Pose2Sim) met la verticale en échec ; une personne
  immobile sur un tapis (LBMC) laisse les rotations mal contraintes (~3°).
- Des caméras **synchronisées** au niveau de l'image. Un décalage de 6 images à 60 Hz
  double le MRE et dégrade la rotation (OpenCap).
- Des intrinsèques correctes. Des intrinsèques génériques (OpenCap) plafonnent la
  précision quelle que soit la quantité de données.
- La stature du participant, pour l'échelle seulement ; sans elle, le résultat est
  correct à un facteur près.

## 4. Ce qui ne change pas le résultat (mesuré)

- **Plus d'images** : à partir de quelques centaines d'images utiles, la rotation ne bouge
  plus ; 24 images suffisent au BA pour retrouver le même optimum.
- **Un BA plus long ou plus tolérant** : identique.
- **200 Hz contre 50 Hz** pour MeTRAbs : identique ; RTMPose est évalué à ~50 Hz par
  construction (VideoPose3D).
- **Cumuler plusieurs essais** d'un même rig (OpenCap sujet 2 : 3 marches, 720 images)
  donne la moyenne des essais seuls, pas mieux.

## 5. Indicateurs disponibles sans référence

- **MRE final** (px) : signale les échecs complets (55 à 1306 px contre ≤ 18 px quand la
  calibration réussit). Il ne détecte pas un échec **partiel** d'une seule caméra
  (P18_WALK_01 RTMPose : une caméra à 122°, MRE 14,6 px) : rapporter aussi la pire caméra.
- **Dispersion des longueurs de segments** au fil des images et **MRE sur un autre essai**
  (validation croisée) : critères que l'optimisation ne minimise pas ; ils ont tranché
  le cas OpenCap (03 §5).
