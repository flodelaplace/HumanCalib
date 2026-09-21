# 03 — Résultats obtenus (état au 20/09/2026, 07h — tous les runs prévus sont faits)

Conventions : « rot » = rotation relative médiane entre paires de caméras, en degrés
(1° ≈ 1,75 cm/m ≈ 16 px à f = 913) ; « 7 ddl » = erreur de position des centres de
caméras après superposition similitude (forme du rig), chaque caméra exclue de la
superposition ; « 4 ddl » = après lacet + translation seulement (notre échelle et notre
verticale : erreur bout-en-bout) ; « échelle » = facteur Umeyama (1 = juste). Tous les
essais sont rapportés, échecs compris. Fichiers détaillés : `~/humancalib_eval/NUIT_16-17.md`,
`article_*.txt`.

## 1. Vue d'ensemble MeTRAbs (HumanCalib-M)

| Jeu | Essais | rot médiane [IQR] | 7 ddl (mm) | 4 ddl (mm) | |échelle − 1| | Échecs |
|---|---|---|---|---|---|---|
| BioCV | 18 | **0,62** [0,48–0,81] ; 14/18 < 1°, 17/18 < 2° | 55 | 101 | 1,2 % | 0 |
| IMOVE-23 | 11 sujets | **0,42** [0,36–0,58] ; pire paire 1,05 | 48 | 167 | 2,3 % | 0 |
| OpenCap (resync par essai, sensibilité) | 9 sujets | **2,06** [1,67–2,14] | 118 | 143 | 2,5 % | 0 |
| **OpenCap (article : synchro Mesh2Sim, fenêtre ≥ 3 caméras entières)** | 18 (9 sujets × 2) | **1,84** [1,57–1,91] ; pire paire 2,65 | 102 | 107 | 1,1 % | 0 |
| LBMC (tapis) | 2 | **1,47 / 3,08** | 60 / 97 | 103 / 187 | 3,0 / 5,1 % | 0 |
| COMFI (14 participants × rectiligne + circulaire ; référence ArUco, voir §13) | 28 | **1,25** [0,94–1,63] ; rectiligne 1,00, circulaire 1,59 | 35 (26 / 63) | 118 | 1,9 % | 0 |

Verticale : BioCV 0,32° médiane ; IMOVE 0,89 / 0,31° ; LBMC 0,66 / 1,44°.

BioCV par essai (rot WALK_01 / WALK_02) : P03 0,54/1,39 ; P04 0,57/0,69 ; P06 1,25/1,46 ;
P09 0,71/0,56 ; P10 0,36/0,34 ; P13 0,46/0,22 ; P16 0,60/0,70 ; P17 0,44/**2,61** ;
P18 0,84/0,64 (tableau complet dans `article_biocv_metrabs.txt`).

OpenCap par sujet (resync) : s2 2,14 · s3 1,19 · s4 2,14 · s5 2,15 · s7 1,67 · s8 2,11 ·
s9 1,69 · s10 2,06 · s11 1,56 (walking2). Avec les clips officiels seuls (70–84 images) :
s11 1,40°, s9 3,06°, s2 w3 1,95° — suffisants quand l'essai est bien synchronisé.

## 2. Répétabilité et nombre d'essais (BioCV MeTRAbs)

- WALK_01 vs WALK_02 du même participant : **0,40°** médiane, inférieur à l'erreur contre
  la gold → une part systématique (ex. P16 : 0,08° entre marches, 0,6–0,7° contre gold).
- **Moyenne de deux calibrations** : 0,61° médiane ; meilleure que la moyenne des deux
  seules chez 7/9, meilleure que la meilleure des deux chez 2/9 (P06 1,25/1,46 → 0,35 ;
  P17 0,44/2,61 → 1,35).
- Variance entre essais d'un même participant (0,31) > entre participants (0,17),
  ICC ≈ 0,04 : l'erreur dépend de l'essai, pas de la personne.
- Bootstrap de l'IC 95 % de la médiane : 9 × 1 essai → largeur 0,81° ; 9 × 2 → **0,38°** ;
  7 × 2 (0,59°) bat 9 × 1. → **deux essais par participant**.

## 3. Deux moteurs, BioCV, 18 essais appariés (P18_W02 RTMPose ajouté le 18/09)

Mise à jour 18 essais (`~/humancalib_eval/article/table2_engines.md`) : RTMPose **5 échecs complets**
(+ P18_W02 7,9°) **+ 2 partiels** (une caméra > 10° : P18_W01 122°, P06_W01 23°, médianes 0,49 et 1,22°) ;
MeTRAbs 0/18. Sur les 11 essais réussis par les deux : MeTRAbs 0,57° [0,50–0,69], RTMPose 0,45°
[0,40–0,57] ; 7 ddl 39 / 37 mm ; |échelle − 1| 1,8 / 2,1 %. Tableau historique à 16 essais ci-dessous.

| | MeTRAbs | RTMPose + VideoPose3D |
|---|---|---|
| Échecs (> 5°) | **0/16** | **4/16** (P06_W02 28°, P10_W01 170°, P17_W01 118°, P17_W02 113°) + 1 partiel (P18_W01 : une caméra à 122°, médiane 0,49°) |
| rot médiane sans les échecs (n = 12) | 0,58 [0,52–0,70] | 0,46 [0,42–0,57] ; Wilcoxon apparié p = 0,18 |
| 7 ddl | 48 mm | 38 mm |
| |échelle − 1| | 1,4 % (jambes) | 5,2 % jambes → **2,1 %** jambes+tronc |
| 4 ddl | ~55 mm | ~263 mm jambes → **~102 mm** jambes+tronc |
| MRE final | 2,4–5,2 px | 5,5–17,7 px (réussis), 55–1306 px (échecs) |

Lecture : à précision égale quand il réussit, RTMPose échoue une fois sur quatre et
son échec complet se voit au MRE. La cause des échecs P17 n'est **pas** la visibilité
(38–96 % des images vues) ; les angles de 113–170° évoquent une ambiguïté d'orientation
du 3D de VideoPose3D dans l'étape linéaire (33–134° avant BA). **Non élucidée.**

LBMC : RTMPose 3,27 / 3,17° contre MeTRAbs 1,47 / 3,08° ; même plafond des deux côtés.

## 4. OpenCap : ce qui limite

- Sujet 2, cinq essais : seuls w1 2,14 · w2 1,61 · w3 1,85 · TS1 3,07 · TS2 2,93 ;
  **cumulés** w1+w2+w3 (720 images) 2,17°, TS1+TS2 3,11°, les cinq (1200) 2,42°.
  Le triple de données donne la moyenne des essais : erreur systématique. Le balancement
  du tronc (TS) dégrade.
- Décalages de synchronisation estimés par essai (avec la gold, donc analyse de
  sensibilité seulement) : gros sur le sujet 2 (Cam2 : −105 images en w1, −88 en TS1),
  petits (6–12 images sur 1–3 caméras) chez 6 sujets sur 9.
- Sans nos décalages (fenêtres du jeu seules) sur les essais déjà testés : s2 w2 1,79°
  (au lieu de 1,61), s3 w1 2,13° (au lieu de 1,19).
- **Synchronisation vérifiée à la main par Florian** (s2 walking1 : Cam1 −6, Cam2 −107, Cam3 +4
  images) : confirmée par reprojection avec la gold à l'image près (minima 3,2 / 11 / 6,0 px) ;
  l'estimateur automatique ratait les petits décalages. Un opérateur est en champ avant l'entrée
  du sujet → fenêtre **[−30, +120]** images autour de l'instant officiel (150 images). Résultat :
  **1,55° (pire paire 2,23°), 46 mm en 7 ddl, 60 mm en 4 ddl, MRE 2,2 px**, contre 2,14° / 88 mm /
  4,4 px avec Cam2 seule corrigée et 240 images. Bien synchronisé et bien fenêtré, OpenCap
  atteint le MRE de BioCV et ~1,5°. Règle retenue pour l'article : synchro vérifiée image par
  image sur chaque essai retenu, fenêtre [−30, +120].

- **Résultats article (18/09)** : synchro vidéo↔mocap par caméra de Mesh2Sim (`_MOCAP_SYNC.json`,
  validée par plateformes de force ±1,5 image), fenêtre = images où ≥ 3 caméras voient le participant
  entier (`_PARTICIPANT_PRESENCE.json`, YOLO + marqueurs mocap, validé à 4 images près contre un
  relevé visuel). Par sujet (w1/w2) : s2 1,73/1,85 · s3 1,55/1,60 · s4 1,87/1,90 · s5 1,95/2,11 ·
  s7 1,91/1,82 · s8 2,13/2,10 · s9 1,87/1,76 · s10 1,44/1,51 · s11 0,89/0,81. MRE 2,4 px.
  **Répétabilité entre les deux marches : 0,03–0,16°** pour ~1,8° d'écart à la gold → erreur
  systématique par session. Meilleur essai s11 w3 : 0,81°, 4 caméras à 0,5–0,8°, Cam2 (frontale) 2,5°.
- **Synchro Mesh2Sim contre manuelle (s2, s8 w1, plan croisé 2×2)** : la fenêtre ne change presque
  rien (±0,05°) ; la synchro manuelle gagne ~0,1° et 0,4–0,7 px, par Cam2 (Mesh2Sim +3/+4 images,
  caméra frontale où le calage temporel est peu sensible). Synchro manuelle des 16 autres essais en
  cours (Florian).

## 5. La gold est-elle en cause ? Test de cohérence hors échantillon

Mêmes points 2D MeTRAbs, triangulés puis reprojetés avec notre calibration et avec la
gold. **En échantillon** (points de l'essai qui a servi à calibrer) : la gold est meilleure
ou égale sur BioCV 18/18 (1,9–2,5 px contre 2,1–4,7), IMOVE 2/2, LBMC 2/2, mais pire sur
OpenCap 12/12. **Hors échantillon** (calibration sur l'essai A, points de l'essai B du
même rig) : la gold gagne aussi sur OpenCap (MRE 2,8–6,3 px contre 5,5–11,2, 10/12 ;
dispersion de la longueur cuisse+tibia 1,4–1,7 % contre 1,7–2,8 %, 12/12). → notre
calibration absorbe un défaut propre à chaque essai OpenCap (synchro résiduelle) ; la
gold n'est pas démontrée fausse ; ne jamais départager deux calibrations sur les points
qui ont servi à calibrer.

## 6. Échelle métrique depuis la stature

Erreur d'échelle bout-en-bout (triangulation avec notre calibration, échelle vraie par
Umeyama), biais / écart-type, calibrations ratées exclues :

| Groupe | n | Jambes | Jambes + tronc |
|---|---|---|---|
| BioCV MeTRAbs | 18 | **+1,0 / 1,5 %** | −2,9 / 0,4 % |
| OpenCap MeTRAbs | 12 | **+1,7 / 1,5 %** | −2,4 / 1,1 % |
| IMOVE MeTRAbs | 2 | +2,0 / 0,5 % | −1,1 / 1,3 % |
| LBMC MeTRAbs | 2 | +3,0 / +5,1 % | — |
| BioCV RTMPose | 12 | +4,9 / 1,9 % | **−1,8 / 0,8 %** |
| LBMC RTMPose | 2 | +10,8 / — | **+0,6 / +1,0 %** |

Points hauts du squelette MeTRAbs testés (marqueurs acromion `shom`, cou, épaules,
bandeau de tête) : le tronc jusqu'à l'acromion tombe sur la table (28,0–28,3 % contre
28,8 %) mais n'améliore pas l'échelle (+1,3 à +3,6 %), car jambes et tronc sont tous deux
1–2 % plus courts que la table dans le même sens. Pas de sommet du crâne dans BML-MoVi.

Décomposition avec les marqueurs LBMC (HJC Harrington 2007) : vraies jambes 47,0 %
(p1) et 47,8 % (p2) de la stature → la table 0,491 surestime de +4,6 / +2,8 % ; MeTRAbs
mesure la somme juste (+2,7 / +0,4 %) mais place le genou trop bas (cuisse +4–6 cm,
tibia −4 cm) ; le reste (+1,2 / +2,7 %) vient de la calibration sur tapis.

## 7. Ablations et sensibilité déjà mesurées

- Plus d'images / BA plus poussé : sans effet (grille BA, 24 images suffisent).
- 200 Hz vs 50 Hz MeTRAbs : identique.
- 5 caméras en arc : arc A 0,51°, arc B 1,39° (l'arrangement par rapport au trajet
  compte, pas le nombre).
- Sélection de personne par le mouvement (v4) contre v2 : corrige la caméra frontale
  vidée par RTMPose ; les régressions v4 venaient d'une perte de couverture, corrigée par
  la porte adaptative.
- Clips officiels OpenCap (70–84 images) contre fenêtre de 240 : identique si l'essai
  est synchronisé, dégradé sinon.

## 8. Ce que la gold de LBMC nous a appris sur les distorsions

Voir 02. Correction validée sur les images (−11 à −13 % d'erreur en bord).

## 9. Démo Pose2Sim (écartée)

4 caméras, 100 images : rot 2,08° (max 2,45), 7 ddl 108 mm, forme 0,88 %, MRE 4,0 px,
verticale 13,7° (sujet en déséquilibre sur une poutre : hors hypothèse), échelle non
évaluable. Utilisable seulement comme illustration.

## 10. COMFI, premier participant (1012)

Appariement vidéo ↔ calibration vérifié par permutations (identité 6,8 px, meilleure
alternative 17 px). Répétabilité entre nos calibrations circulaire et rectiligne (sans
gold) : **1,04°** médiane, 1,84° max. Test hors échantillon (calibration sur un essai,
points de l'autre) : MRE **nous 2,2–2,9 px contre gold 6,8–8,4 px** — l'inverse d'OpenCap ;
dispersion de longueur de jambe mitigée (nous 1,8 / 2,3 %, gold 1,1 / 2,6 %). La gold
COMFI (recalage ArUco indépendant par caméra, webcams 720p) n'est donc probablement pas
cohérente avec les images à mieux que ~1–2° ; nos 1,2–2,1° mélangent notre bruit (~1°)
et le sien. Le `cam_to_cam` fourni a rmse = 0 : dérivé du `cam_to_world`, pas un contrôle
indépendant. Positions (26–32 mm), forme (0,3 %), échelle et verticale restent évaluables.
**À FAIRE** : 14 participants × 2 marches (~2,5 h) ; contrôle de la gold avec les
marqueurs mocap si disponibles.

## 11. Niveau 2 (angles articulaires Pose2Sim) — **À FAIRE**, rien de lancé.

## 12. Durée de marche nécessaire (18/09, `~/humancalib_eval/duration_results_best.csv`)

Mêmes détections, fenêtre de D secondes où le plus de caméras voient le sujet, étape linéaire + BA
du pipeline (mêmes réglages). Durée minimale pour atteindre l'erreur de l'essai entier + 0,2° :
BioCV 1–2 s (4 essais : 2 s → 0,25–0,89°) ; IMOVE 4–8 s (grand couloir : il faut couvrir le volume ;
16 s donnent même mieux que l'aller-retour entier, 0,31 / 0,43°) ; COMFI circulaire 2–4 s, plafond
~1,3–2° indépendant de la durée (référence ArUco) ; LBMC (tapis) 0,5–1 s, plateau immédiat : marcher
plus longtemps au même endroit n'apporte rien. Temps de calcul linéaire + BA : 5–60 s.
**Recommandation** : 2 s de marche vue par toutes les caméras suffisent dans un labo de taille
moyenne ; dans un grand volume, 10 à 15 s qui parcourent tout l'espace. C'est la couverture
spatiale, pas la durée, qui compte au-delà de quelques secondes.

## 13. COMFI complet (18/09) : notre calibration bat la référence face à la mocap

14 participants × 2 marches = 28 calibrations, 0 échec. Mêmes détections MeTRAbs triangulées avec la
gold ArUco puis avec HumanCalib, comparées aux centres articulaires mocap (`joint_center_positions.csv`,
genou = milieu des épicondyles, etc.) : PA-MPJPE par image médiane **gold 56,3 mm, HumanCalib 53,9 mm ;
HumanCalib meilleur dans 28/28 essais, Wilcoxon apparié p < 10⁻⁴** (`~/humancalib_eval/comfi_mocap_eval.json`).
Sur ce jeu, l'écart « contre la gold » (rotation 0,6–2,4°) mesure donc surtout l'erreur de la référence.
Pour l'article : COMFI est évalué contre la mocap, pas contre sa calibration de référence.

## 14. Erreur de reconstruction induite par la calibration (PA-MPJPE marqueurs, 18–19/09)

Marqueurs mocap bruts projetés dans chaque caméra avec la gold, retriangulés avec notre calibration,
puis similitude ajustée sur les points eux-mêmes (PA-MPJPE, convention vision). Isole l'effet de la
calibration sur la reconstruction dans le volume où la personne marche (`~/humancalib_eval/marker_mpjpe.json`).

| Jeu | Essais | PA-MPJPE moyenne, médiane des essais (mm) | Étendue | p95 médian (mm) | 4 ddl (mm) |
|---|---|---|---|---|---|
| BioCV | 18 | **8,9** | 3,0–38,3 (P17_W02, 2,61°) | 21,4 | 35 |
| IMOVE | 2 | **7,5** | 6,5–8,4 | 14,4 | 66 |
| OpenCap | 18 | **4,6** | 2,8–7,1 | 7,9 | 38 |
| LBMC | 2 | **3,4** | 2,1–4,7 | 6,7 | 55 |
| COMFI | 28 | 38,9 (écart à une gold moins précise que nous, §13) | 27,0–66,3 | 86,1 | 80 |

Lecture : 1,8° d'orientation relative sur OpenCap ne donnent que 4,6 mm d'erreur de forme là où la
personne marche (erreurs d'orientation compensées par les positions autour du volume de travail).
COMFI : l'écart est grand parce que la référence ArUco est elle-même moins cohérente avec la mocap
(§13) ; ne pas le présenter comme une erreur de HumanCalib.

## 15. Critère d'acceptation sans référence (130 calibrations, 20/09)

MRE de chaque caméra converti en angle (MRE / focale, mrad). Règle figée le 18/09 : accepter si la
pire caméra ≤ 15 mrad et ≤ 3,5 × la médiane des caméras. Sur 88 calibrations (tous jeux, deux
moteurs, `~/humancalib_eval/mre_vs_error_trials.csv`, `article/table3_acceptance.md` ; ceci exclut les 13
essais où RTMPose ne produit aucune calibration, cas où il n'y a rien à juger) :

| | Calibrations | Acceptées | Rejetées |
|---|---|---|---|
| Correctes (toutes caméras < 10°) | 123 | 123 | 0 |
| Échecs complets ou partiels | 7 (tous RTMPose BioCV) | 0 | 7 |

Pire caméra : correctes ≤ 10,3 mrad, échecs ≥ 41,8 mrad (écart ×4 ; le seuil seul suffit, la règle
du rapport n'est pas nécessaire sur ces données). En revanche, parmi les calibrations réussies, le MRE
ne prédit pas la précision fine. Valeurs recalculées depuis `niveau1/donnees/essais.csv`
(n = 123 calibrations correctes) : Spearman ρ = +0,38 entre MRE médian et rotation, +0,28 avec le
MRE de la pire caméra. Cette corrélation globale est tirée par les différences entre jeux ; à jeu et
moteur fixés : BioCV MeTRAbs +0,79, COMFI MeTRAbs +0,64, COMFI RTMPose +0,71, IMOVE +0,63, mais
OpenCap MeTRAbs +0,10 et BioCV RTMPose −0,16. → Le MRE détecte les échecs ; il ne classe les
réussites que dans certains labos. (Une version antérieure annonçait ρ = +0,35 sur n = 125 : elle
comptait deux échecs partiels parmi les réussites.)

## 16. D'où vient le biais d'échelle (IMOVE contre mocap, 20/09)

L'échelle est surestimée sur tous les jeux : BioCV +0,6 %, OpenCap +0,5 %, COMFI +1,8 %, IMOVE
+1,5 à +4,6 %, LBMC +4,0 % (médianes par jeu, `~/humancalib_eval/article/table_trials.csv`).
Décomposition sur IMOVE, où la mocap donne les centres articulaires HJC, KJC, AJC
(`~/humancalib_eval/imove_scale_analysis.txt`) :

| Sujet | Stature déclarée | Jambe mocap | Ratio réel jambe/stature | Jambe MeTRAbs | MeTRAbs − mocap | Erreur d'échelle |
|---|---|---|---|---|---|---|
| 2 | 1,90 m | 0,888 m | 0,467 | 0,919 m | +3,5 % | +1,5 % |
| 3 | 1,72 m | 0,815 m | 0,474 | 0,826 m | +1,3 % | +2,3 % |
| 4 | 1,81 m | 0,832 m | 0,460 | 0,868 m | +4,4 % | +2,4 % |
| 5 | 1,65 m | 0,744 m | 0,451 | 0,787 m | +5,9 % | +2,9 % |
| 6 | 1,85 m | 0,818 m | 0,442 | 0,869 m | +6,2 % | +4,6 % |
| 7 | 1,68 m | 0,754 m | 0,449 | 0,791 m | +5,0 % | +4,3 % |

Deux biais de sens opposés :
1. **La table (0,491 × stature) ne décrit pas ces participants** : leur ratio mesuré est 0,442–0,474
   (moyenne 0,457). À jambe parfaitement mesurée, l'échelle serait fausse de +3,6 à +11,1 %. Une part
   vient peut-être des statures déclarées : la hauteur mesurée en marche (marqueur APEX − talon) est
   2 à 6 % plus basse que la stature du tableau démographique (sujet 2 : 1,826 contre 1,900 m).
2. **MeTRAbs mesure des jambes 1,3 à 6,2 % plus longues** que la chaîne HJC–KJC–AJC : ses points
   articulaires ne coïncident pas avec les centres articulaires du modèle biomécanique.

Les deux se compensent partiellement, d'où les +1,5 à +4,6 % observés. **À écrire tel quel** : le
plancher d'échelle n'est pas une erreur de calibration mais la somme de la variabilité individuelle
des proportions et de la définition des points du détecteur. Deux suites possibles (à trancher) :
étalonner le ratio jambe/stature propre au détecteur sur un seul jeu de développement, puis
l'appliquer sans retouche aux autres (tester hors échantillon) ; ou recommander une mesure
supplémentaire (longueur de jambe ou hauteur de hanche), qui rend l'échelle quasi exacte.

## 17. Les deux moteurs sur quatre jeux (20/09) — la fiabilité, pas la précision, les sépare

RTMPose + VideoPose3D a été relancé sur OpenCap (18) et COMFI (28) avec exactement le protocole de
MeTRAbs (mêmes vidéos découpées, mêmes intrinsèques, même sélection de personne, échelle jambes+tronc).
`~/humancalib_eval/article/table2b_engines_by_dataset.md` :

| Jeu | Essais | MeTRAbs : échecs | RTMPose : sans sortie + complets + partiels | Rotation MeTRAbs | Rotation RTMPose |
|---|---|---|---|---|---|
| BioCV | 18 | 0 | 0 + 5 + 2 | 0,57 [0,50–0,69] | 0,45 [0,40–0,57] |
| OpenCap | 18 | 0 | 0 + 0 + 0 | 1,84 [1,57–1,91] | 1,97 [1,72–2,27] |
| LBMC | 2 | 0 | 0 + 0 + 0 | 2,28 | 3,22 |
| COMFI | 28 | 0 | 13 + 0 + 0 | 1,48 [1,26–1,85] | 1,74 [1,59–2,09] |

- **MeTRAbs : 0 échec sur 66 essais appariés. RTMPose : 20 sur 66 inutilisables (30 %)**, en trois modes :
  aucune sortie (13, COMFI), calibration complètement fausse (5, BioCV), une seule caméra fausse (2, BioCV).
- **Les échecs COMFI sont expliqués** : 13 des 14 marches **rectilignes** échouent (essais courts, 282
  images, 4 caméras : après filtre de visibilité il ne reste que ~6 images vues par ≥ 2 caméras),
  contre **0 des 14 circulaires**. MeTRAbs réussit ces mêmes essais (0,68° de médiane sur les rectilignes).
  Les échecs BioCV, eux, restent inexpliqués.
- **Quand il réussit, RTMPose vaut MeTRAbs** : meilleur sur BioCV, un peu moins bon sur OpenCap
  (1,97 contre 1,84°, Wilcoxon apparié p = 0,25), COMFI (1,74 contre 1,48°) et LBMC.
- **Les biais d'échelle sont de signes opposés** : sur OpenCap, MeTRAbs +0,5 % et RTMPose −1,4 % ;
  sur COMFI circulaire, −1,5 % pour RTMPose. Les deux détecteurs encadrent la valeur vraie, ce qui
  confirme §16 : le biais vient de la définition des points articulaires, pas de la calibration.

## 18. Niveau 2 : effet de la calibration sur les angles articulaires (21/09, 77 essais)

Chaîne **Pose2Sim 0.10.43** exécutée deux fois par essai sur les **mêmes détections 2D**, en ne
changeant que la calibration (référence du jeu, puis la nôtre) ; protocole complet dans
`08_NIVEAU2_METHODE.md`. Données : `niveau2/donnees/*.csv` du dossier de rédaction.

| Jeu | Essais | Écart médian entre les deux chaînes | Pire ddl | ddl équivalents à 2° |
|---|---|---|---|---|
| BioCV | 18 | **0,61°** | 1,12° | **9/9** |
| OpenCap | 18 | **0,52°** | 0,85° | **9/9** |
| IMOVE | 11 | **0,93°** | 1,67° | 7/9 |
| LBMC | 2 | 0,48° | 0,91° | (2 essais : test non interprétable) |
| COMFI | 28 | 4,24° | 10,02° | 0/9 — voir la réserve ci-dessous |

Équivalence déclarée si la borne haute de l'IC 95 % du RMSD moyen reste sous 2° (McGinley), avec
correction de Bonferroni sur les 9 ddl. Sur IMOVE, les deux ddl qui échouent sont les **rotations
axiales** (bassin 1,61°, hanche 1,40° de moyenne) : la moyenne passe, la borne haute non.

**Face à l'optoélectronique** (IK mocap des jeux qui en fournissent une ; décalage temporel estimé
une fois par essai et appliqué aux deux variantes) :

| Jeu | Essais | Référence contre mocap | Nous contre mocap | Écart |
|---|---|---|---|---|
| BioCV | 18 | 6,16° | 6,18° | **+0,02°** |
| IMOVE | 11 | 11,41° | 11,48° | **+0,07°** |
| OpenCap | 18 | 4,43° | 4,43° | **0,00°** |

**C'est le message du niveau 2** : l'écart markerless–mocap est de 4 à 11° selon le jeu, et changer
de calibration ne le déplace que de quelques centièmes de degré. L'effet de la calibration est donc
d'un ordre de grandeur inférieur aux autres sources d'erreur de la chaîne (modèle, jeu de marqueurs,
détection de pose).

**COMFI, face à sa propre mocap (21/09).** Le jeu fournit ses angles articulaires
(`mocap/aligned/<id>/<tâche>/joint_angles.csv`), ce qui permet de trancher : notre calibration
donne-t-elle des angles plus proches de la mocap que la sienne ? Son modèle n'étant pas celui de
Pose2Sim, le signe et le décalage constant de chaque ddl sont fixés **une fois sur la chaîne de
référence** puis appliqués aux deux, de sorte que seule la comparaison entre chaînes s'interprète.

| | Écart médian à la mocap |
|---|---|
| Calibration ArUco du jeu | 8,19° |
| **Notre calibration** | **7,21°** |

**Meilleur dans 24 essais sur 27** (Wilcoxon apparié p < 0,0001), et sur **les 12 ddl sans
exception** : hanche 0,4–1,5°, genou 0,6–0,7°, cheville 1,1–1,5°, subtalaire 0,4–1,6° de gain.
C'est la confirmation angulaire du résultat 3D de §13 (28/28 en PA-MPJPE) : sur COMFI, l'écart entre
les deux chaînes vient de la référence, pas de nous. Données : `comfi_angles_vs_mocap.csv`.

**Réserves.** COMFI se lit à part : sa référence ArUco est moins juste que notre calibration face à
la mocap (§13), donc l'écart de 4,24° y mesure le désaccord entre deux calibrations dont la moins
bonne sert d'étalon, pas notre erreur ; les reconstructions 3D y diffèrent de 15 cm. LBMC n'a que
deux essais. Deux défauts ont été trouvés et corrigés pendant ces runs : la fenêtre de validité de
la référence BioCV (hors fenêtre, l'écart apparent montait à 15°) et l'ambiguïté de sens de l'axe de
marche sur les allers-retours d'IMOVE (un sujet sortait à 180°, corrigé en fixant le sens sur
l'orientation du corps).

## 19. RTMPose sur IMOVE, et comparaison des moteurs sur les cinq jeux (21/09)

RTMPose + VideoPose3D relancé sur les 11 sujets IMOVE, pour que la comparaison des moteurs couvre
aussi le rig à 10 caméras. Même protocole que MeTRAbs (mêmes vidéos, intrinsèques, sélection de
personne ; échelle jambes + tronc).

| Sujet | RTMPose | MeTRAbs | Verdict |
|---|---|---|---|
| 5, 12 | **0,25° et 0,38°** | 0,37° et 0,31° | réussis |
| 2, 3, 4, 9, 11 | 8 à 139° | 0,28 à 1,21° | échecs complets |
| 6, 7, 13 | 1,6 à 2,5° (médiane), une paire à 69–179° | 0,35 à 0,52° | échecs partiels |
| 10 | — | 0,38° | sans sortie (pas assez de points de pied pour l'échelle) |

**RTMPose : 9 échecs sur 11 ; MeTRAbs : 0.** Quand RTMPose réussit, il vaut MeTRAbs, voire mieux
(sujet 5). L'hypothèse d'une gêne due aux caméras tournées ne tient pas ici : la préparation redresse
les vidéos des caméras 22 et 23, qui sont même les deux meilleures pour RTMPose. L'échec vient d'un
déficit de détection général (72–90 % d'images exploitables contre 90–100 % pour MeTRAbs) et d'un
effondrement sur une caméra (Cam26 : 17 % contre 91 %), sans cause géométrique apparente
(distance et résolution comparables à des caméras qui fonctionnent).

**Comparaison des moteurs, cinq jeux, 77 essais appariés** (`niveau1/02_SYNTHESE.md` §2) :

| Jeu | Essais | MeTRAbs : échecs | RTMPose : sans sortie + complets + partiels |
|---|---|---|---|
| BioCV | 18 | 0 | 0 + 5 + 2 |
| IMOVE | 11 | 0 | 1 + 5 + 3 |
| OpenCap | 18 | 0 | 0 + 0 + 0 |
| LBMC | 2 | 0 | 0 + 0 + 0 |
| COMFI | 28 | 0 | 13 + 0 + 0 |

**MeTRAbs : 0 échec sur 77. RTMPose : 29 essais inutilisables sur 77 (38 %)**, concentrés sur trois
jeux, aucun sur OpenCap ni LBMC. Sur les essais réussis par les deux, la précision est équivalente.

**Critère d'acceptation, 140 calibrations** : 125 correctes acceptées, **15 échecs rejetés**, aucune
fausse alarme. Pire caméra : correctes ≤ 10,3 mrad, échecs ≥ 32,1 mrad. Les 8 échecs IMOVE,
complets comme partiels, sont tous détectés.

## 20. Échelle mesurée de haut en bas : récapitulatif des biais et nouvelle méthode (21/09)

Erreur d'échelle bout-en-bout = facteur Umeyama 7 ddl face à la référence − 1. Médiane [écart-type]
par jeu ; calibrations ratées exclues (rotation médiane ≥ 5° ou pire paire ≥ 10° : 15 RTMPose).
Rapport tête/stature fixé sur **BioCV seul** : BioCV est donc dans l'échantillon et ne compte pas
comme validation.

**MeTRAbs, 77 calibrations recalculées réellement** (`eval/metrabs_v4_stature`, rotations
identiques à v4 sur les 77) :

| Jeu | n | Jambes × 0,491 (v4) | Tête → sol (nouveau) | ≤ 1 % : jambes → tête | 4 ddl (mm) : jambes → tête |
|---|---|---|---|---|---|
| BioCV (dév.) | 18 | +0,60 [1,56] | +0,01 [0,95] | 39 → 67 % | 101 → 67 |
| OpenCap | 18 | +1,02 [1,53] | +0,58 [1,21] | 50 → 61 % | 84 → 82 |
| IMOVE | 11 | +2,27 [1,22] | +1,57 [1,07] | 9 → 36 % | 167 → 136 |
| LBMC | 2 | +4,03 [1,45] | +2,01 [1,29] | 0 → 0 % | 145 → 98 |
| COMFI | 28 | +1,85 [1,66] | +0,10 [1,49] | 18 → 50 % | 118 → 90 |

**Hors BioCV (59 calibrations)** : erreur absolue médiane **1,89 → 1,04 %** (Wilcoxon apparié
p = 9·10⁻⁵) ; ≤ 1 % : 25 → 49 % ; ≤ 2 % : 53 → 78 % ; pire cas 5,1 → 3,8 %. Sur les 77 : 1,77 →
0,92 % ; position 4 ddl médiane 117 → 82 mm. L'évaluation hors ligne (rapport appliqué aux
calibrations existantes, `scale_study.py`) prédisait les mêmes chiffres à 0,05 point près.

**RTMPose (évaluation hors ligne, 47 calibrations réussies)** : jambes + tronc −2,07 [0,67] sur
BioCV, −0,93 / +1,28 / +0,80 / −1,53 % sur OpenCap / IMOVE / LBMC / COMFI (|erreur| médiane hors
BioCV 1,18 %) ; sommet du crâne Halpe26 → sol (rapport 0,983 fixé sur BioCV) : 1,28 %, plus
dispersé (écart-type jusqu'à 2 %). **RTMPose garde jambes + tronc.**

Ce qui reste :
- **Cible de 1 % atteinte en biais sur BioCV, OpenCap et COMFI, pas sur IMOVE (+1,6 %) ni LBMC
  (+2,0 %, 2 essais).** Écart-type entre essais 1,0 à 1,5 % sur tous les jeux : c'est le bruit de
  mesure d'un essai.
- Le rapport bandeau/stature mesuré par MeTRAbs varie selon le jeu (0,907 LBMC, 0,911 IMOVE,
  0,920 OpenCap, 0,925 COMFI, 0,926 BioCV). **Ce n'est pas la chaussure** : BioCV, OpenCap et
  IMOVE sont chaussés, COMFI et LBMC pieds nus (vérifié sur les vidéos).
- **Ce n'est pas la posture de marche** : sur IMOVE, le marqueur APEX (vertex) de la cinématique
  mocap culmine à 0,99 × stature en marche (0,97–1,005, 9 sujets).
- Deux causes restent possibles, sans moyen de trancher sur nos données : la stature déclarée
  (sur IMOVE, APEX − talon mesuré était déjà 2 à 6 % sous la stature du tableau démographique, §16)
  et la façon dont MeTRAbs place le bandeau selon le point de vue (caméras hautes et inclinées
  d'IMOVE et LBMC).
- La référence d'échelle COMFI est la calibration ArUco du jeu, moins juste que la nôtre (§13) :
  ses chiffres d'échelle sont indicatifs.

Fichiers : `~/humancalib_eval/scale_study.py`, `scale_study.csv` (toutes les mesures, deux
moteurs), `scale_stature_vs_segments.csv` (77 calibrations recalculées), `stature_batch.sh`.
