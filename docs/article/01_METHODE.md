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
segments + verticale sur la marche** ; c'est la version des résultats de niveau 1 et 2.
L'échelle « stature » (§2, 21/09) ne change que le facteur d'échelle : rotations, forme et
verticale sont identiques à v4 (vérifié sur les 77 calibrations).

## 2. Échelle métrique depuis la stature

**MeTRAbs : le corps mesuré de haut en bas** (méthode retenue le 21/09, remplace les jambes).
Sur ~400 images réparties sur la marche, chacune triangulée par consensus de caméras :

- **haut** = milieu des quatre marqueurs virtuels du bandeau de tête du squelette MeTRAbs
  (`lfronthead`, `rfronthead`, `lbackhead`, `rbackhead`) ;
- **sol** = 2ᵉ centile, sur l'essai, du marqueur de semelle le plus bas de chaque image
  (talons, orteils, 1er, 4ᵉ et 5ᵉ métatarses) ;
- hauteur retenue = **95ᵉ centile** de (haut − sol) le long de la verticale estimée
  (instants de simple appui, jambe tendue) ;
- cette hauteur vaut **0,9255 × stature**. Ce rapport a été fixé **une seule fois, sur BioCV
  seul** (jeu de développement, 18 calibrations, écart-type 0,009), puis appliqué sans retouche
  aux quatre autres jeux. Il couvre l'écart bandeau → vertex et l'affaissement de la tête en
  marche.

Pourquoi : l'ancienne règle (cuisse + tibia = 0,491 × stature, Drillis & Contini) fait passer
toute la variabilité individuelle des proportions dans l'échelle (ratio jambe/stature réel de
0,442 à 0,474 sur IMOVE, écart-type ~2,5 % entre sujets). Mesurer toute la hauteur n'expose qu'à
la partie tête → vertex (~7 % de la stature). Hors BioCV (59 calibrations), l'erreur absolue
médiane passe de 1,9 à 1,0 % (03 §20).

**RTMPose : cuisse + tibia + tronc (milieu des hanches → cou) = 0,491 + 0,288 = 0,779 ×
stature**, rapport de la littérature, inchangé depuis v4. La hanche Halpe26 est ~85 mm en avant du
centre articulaire : la cuisse sort trop longue et le tronc trop court, les deux se compensent.

**Deux règles, une par moteur : pourquoi, et comment le choix a été fait.** Ce n'est pas un choix
au cas par cas, mais une seule procédure appliquée aux deux moteurs :
1. la mesure tête → sol a été testée **sur les deux moteurs, de façon identique** : même
   définition du sol et du centile, rapport tête/stature fixé sur BioCV seul, évaluation sur les
   quatre autres jeux ;
2. la règle en place n'est remplacée que si la nouvelle mesure fait mieux hors BioCV.
   - **MeTRAbs** : erreur absolue médiane 1,89 → 1,04 % (59 calibrations, Wilcoxon p = 9·10⁻⁵),
     donc la règle est remplacée.
   - **RTMPose** : 1,18 → 1,28 % (36 calibrations réussies, p = 0,81), avec une dispersion plus
     grande sur tous les jeux (écart-type jusqu'à 2,0 % contre 1,2 %), donc la règle est gardée.
3. La raison tient à la définition des points. MeTRAbs prédit un squelette 3D de surface complet
   (87 points, dont quatre marqueurs de bandeau et dix marqueurs de semelle), cohérent entre les
   vues. Halpe26 n'a qu'un point « tête », détecté en 2D sur le contour du crâne : il dépend de la
   coiffure et de l'angle de vue, et se triangule donc moins bien.

**L'asymétrie est à déclarer :**
- **MeTRAbs** : le rapport 0,9255 est **empirique**, fixé sur un seul jeu de développement.
- **RTMPose** : 0,779 vient d'une **table anthropométrique**, sans aucun ajustement.

Les chiffres de validation de la règle MeTRAbs sont donc ceux des quatre jeux hors BioCV.

Option `--scale_method` : `stature` (défaut ; MeTRAbs 87 points, repli sur les segments pour
les autres squelettes), `segments` (ancienne règle, gardée pour comparaison), `head`.

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
