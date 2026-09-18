# 03 — Résultats obtenus (état au 17/09/2026)

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
| IMOVE-23 | 2 (s2, s3) | **0,42 / 0,65** | 54 / 83 | 130 / 167 | 1,5 / 2,3 % | 0 |
| OpenCap (resync par essai, sensibilité) | 9 sujets | **2,06** [1,67–2,14] | 118 | 143 | 2,5 % | 0 |
| **OpenCap (article : synchro Mesh2Sim, fenêtre ≥ 3 caméras entières)** | 18 (9 sujets × 2) | **1,84** [1,57–1,91] ; pire paire 2,65 | 102 | 107 | 1,1 % | 0 |
| LBMC (tapis) | 2 | **1,47 / 3,08** | 60 / 97 | 103 / 187 | 3,0 / 5,1 % | 0 |
| COMFI (test, 1 participant) | 2 (circulaire 1000 img / rectiligne 282 img) | **2,06 / 1,19** | 32 / 26 | 61 / 68 | 1,4 / 1,8 % | 0 |

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

## 3. Deux moteurs, BioCV, 16 essais appariés

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
