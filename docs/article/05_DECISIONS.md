# 05 — Décisions et corrections (journal court)

Chaque entrée : décision, raison, conséquence. Le détail daté est dans
`docs/EVALUATION_PROTOCOL.md` §13.

## Décisions méthodologiques

- **Version évaluée = v4** (sélection par le mouvement, échelle par segments, verticale
  sur la marche). Figée avant les runs définitifs ; aucune version n'est retouchée après
  avoir vu les résultats d'un jeu.
- **Échelle : jambes pour MeTRAbs, jambes + tronc pour RTMPose, aucune constante
  corrective** (17/09, Florian). Une correction unique de ~−2,3 % aurait ramené l'erreur
  à ~0,7 % (validée en leave-one-dataset-out) mais Florian ne veut pas « dire la
  constante » ; la règle retenue se justifie par la définition des points (hanche
  Halpe26 antérieure) et par la littérature, pas par un ajustement.
- **Table anthropométrique : Drillis & Contini 0,491, citée avec de Leva 1996** (0,492,
  centres articulaires, vérifié). ANSUR II donnerait 0,477–0,486 ; à présenter en
  sensibilité, pas en méthode.
- **Résultats principaux = distribution par essai, un essai par ligne, échecs compris.**
  Pas de « meilleur essai » (demande de Florian du 17/09 refusée avec justification :
  un relecteur le reprocherait ; le meilleur essai peut illustrer une figure, dit comme tel).
- **Deux essais par participant** quand le jeu le permet (bootstrap BioCV).
- **OpenCap : on n'utilise que les fenêtres fournies par le jeu (`_RAW_WINDOWS.json`),
  sans nos décalages estimés** (17/09). Phrase de l'article : « essais synchronisés
  fournis par le jeu, prolongés de quelques images avant et après ». Nos décalages
  étaient estimés avec la gold : les publier reviendrait à évaluer avec la référence.
  Les runs « resync » restent une analyse de sensibilité. Conséquence : relancer les
  9 sujets (~2 h) ; résultats attendus un peu moins bons que 2,06°.
- **OpenCap, révision du 17/09 après-midi : synchronisation vérifiée à la main** (Florian, image
  par image sur un événement de la marche), validée par reprojection ; fenêtre asymétrique
  [−30, +120] pour exclure l'opérateur présent avant l'entrée du sujet. Remplace « fenêtres du jeu
  seules » ; phrase de l'article : « synchronisation des caméras vérifiée image par image ».
- **La resynchronisation n'est pas décrite comme méthode** : « un dataset propre est
  censé être bien synchronisé » (Florian, 16/09).
- **Démo Pose2Sim écartée** des statistiques (sujet sur une poutre, stature inconnue).
- **Tapis (LBMC)** : rapporté tel quel, avec le message « se déplacer dans la scène même
  pour une acquisition sur tapis » (MRE bon au centre, rotations mal contraintes).
- **OpenCap : 2 marches naturelles par sujet (walking1 et walking2 ; subject11 walking2 et walking3, pas de walking1), 18 essais, synchro relevée à la
  main par Florian sur chacun** (17/09) ; fenêtre = plage de visibilité mesurée par essai (repérage
  sur planches, `~/humancalib_eval/OpenCap/_visibility/`), la règle fixe [−30, +120] ne tenant pas
  (s8 : [−78, +72]). Premiers résultats : s2 w1 2,14 → 1,55°, s8 w1 2,11 → 1,96° ; 7 ddl 88 → 46 mm et
  205 → 78 mm ; MRE 4,4 → 2,2 et 5,0 → 1,7 px.
- **Marge d'équivalence : en attente** (04 §6).

## Erreurs faites et corrigées (à ne pas refaire)

- **« La gold OpenCap est imprécise »** (16/09) : c'était la caméra 2 désynchronisée.
- **« Notre calibration explique mieux les images que la gold OpenCap »** (17/09 matin) :
  vrai seulement sur les points qui ont servi à calibrer ; faux hors échantillon. Ne
  jamais comparer deux calibrations sur ces points.
- **« Les échecs RTMPose viennent d'une caméra mal vue »** : faux pour P17 (visibilité
  38–96 %). Cause non établie.
- **Estimation de décalages** : figer l'échantillon d'images avant le balayage (sinon
  faux minima aux bords), filtrer sur la visibilité, rejeter les minima au bord et les
  planchers proches du bruit.
- **Stats d'échelle** : exclure les calibrations ratées (rot ≥ 5°) avant tout calcul,
  sinon RTMPose donne +98 % de biais.
- **Marqueurs LBMC** : noms ISB (RIAS, LIAS, RIPS, LIPS, RFCC…), pas les noms devinés.
- **Gros lots lancés sans demander** (16/09) : reproche de Florian ; lancer les lots la
  nuit ou le week-end, après validation.

## Pièges de données découverts (résumé, détail dans 02)

BioCV s·R ; OpenCap `imageSize` inversé, k3, pas de synchro matérielle, transform
dégénérée ; IMOVE conventions XML, caméras tournées à l'envers de `viewrotation`, prise
`_001/_002` ; LBMC distorsions ÷64 dans le TOML (bug hérité du convertisseur Pose2Sim) ;
COMFI horodatages logiciels.
