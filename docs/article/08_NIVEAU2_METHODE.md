# 08 — Niveau 2 : effet de la calibration sur les angles articulaires (méthode)

Question : **remplacer la calibration fournie par le jeu de données par la nôtre change-t-il la
cinématique articulaire obtenue par une chaîne markerless ?** Le niveau 1 mesure la géométrie des
caméras ; le niveau 2 mesure ce qui intéresse le biomécanicien, les angles.

## 0. Ce que cette étude n'est pas

Elle **n'évalue pas** la chaîne markerless contre l'optoélectronique. Une telle évaluation exigerait
d'harmoniser les modèles biomécaniques, de retirer le biais inter-modèles et de définir des repères
anatomiques communs, ce qui n'est pas fait ici. On se place **à l'intérieur d'une chaîne markerless
multi-caméras open-source largement utilisée (Pose2Sim)** et on n'y fait varier qu'une chose : la
calibration. Les écarts à la mocap rapportés plus bas ne servent que d'échelle de comparaison ; ils
mélangent modèle, jeu de marqueurs et détection de pose, et ne sont pas une performance de Pose2Sim.

## 1. Principe : ne faire varier que la calibration

Pour chaque essai, la chaîne **Pose2Sim 0.10.43** (installation officielle, OpenSim 4.5.2) est
exécutée **deux fois**, sur les **mêmes détections 2D**, en ne changeant que le fichier de
calibration :

1. `poseEstimation` — RTMPose (modèle Halpe26, mode « balanced »), une seule fois par essai, sur
   GPU. Les détections sont **partagées** par les deux variantes (lien symbolique, pas copie) : c'est
   ce qui garantit que la seule différence entre les deux sorties est la calibration. Un contrôle
   vérifie, caméra par caméra, que le nombre de détections égale le nombre d'images à traiter ; un
   dossier incomplet est recalculé.
2. `triangulation` → `filtering` (Butterworth passe-bas, réglage par défaut, 6 Hz) →
   `markerAugmentation` (LSTM Stanford) → `kinematics` (mise à l'échelle et IK OpenSim), avec la
   configuration Pose2Sim par défaut, pour chaque variante :
   - **gold** : la calibration de référence du jeu ;
   - **hc** : la nôtre, échelle et verticale comprises. Échelle MeTRAbs tête → sol
     (`01_METHODE` §2, variante `hcst` dans les fichiers). Un contrôle a montré que l'échelle
     n'est pas neutre dans Pose2Sim : 3 à 4 % d'échelle déplacent les angles de 0,5 à 0,7°
     (`03_RESULTATS` §20) ; le niveau 2 a donc été recalculé avec l'échelle finale.

Tous les paramètres non géométriques sont identiques entre les deux variantes : stature du
participant, fréquence, filtrage, modèle OpenSim, réglages de triangulation.

## 2. Données analysées

- **Essais** : 77, soit BioCV 18, COMFI 28, IMOVE 11, LBMC 2, OpenCap 18 — les mêmes que le niveau 1.
- **Fenêtre de validité de la référence (BioCV)**. La cinématique de référence de BioCV n'est valable
  que sur une fenêtre de l'essai, relevée par Mesh2Sim (`_EXPORT_ARTICLE/00_index/essais.csv`,
  colonnes `lanceur_start` et `lanceur_end`, identiques sur les 9 caméras). L'analyse est restreinte
  à cette fenêtre via le paramètre `frame_range` de Pose2Sim. Hors fenêtre — sujet immobile au bord
  du volume — l'écart apparent entre les deux chaînes montait à 15° ; il tombe à quelques dixièmes de
  degré dans la fenêtre. Pour IMOVE et OpenCap, les vidéos sont déjà découpées sur la marche lors de
  la préparation ; pour COMFI et LBMC, l'essai entier est utilisé.
- **Synchronisation d'OpenCap**. Les vidéos d'OpenCap sont celles du niveau 1, découpées avec la
  synchronisation **vérifiée image par image** sur les 18 essais (voir `03_RESULTATS.md` §4 et le
  relevé `opencap_synchro_manuelle.json`), et la calibration « nous » est celle obtenue avec cette
  synchronisation.
- **Cadence**. Les trajectoires filtrées sont ramenées à environ 60 Hz avant l'augmentation de
  marqueurs et l'IK, par sous-échantillonnage (une image sur k, k = arrondi(fréquence / 60)),
  **à l'identique pour les deux variantes**. Seul BioCV (200 Hz → 66,7 Hz) est concerné ; les autres
  jeux sont déjà à 40, 50 ou 60 Hz. Aucune information n'est perdue : les trajectoires ont été
  filtrées à 6 Hz juste avant, bien sous la fréquence de Nyquist de 30 Hz. L'IK OpenSim, qui traite
  les images une à une sur CPU, devient trois fois plus rapide.

## 3. Repère commun : recalage 4 ddl sur la gold, repère canonique unique

Deux constats, mesurés avant de lancer la série :

- **Pose2Sim n'applique aucune rotation avant l'IK** et attend la verticale sur l'axe Y (convention
  OpenSim). HumanCalib sort en Z vertical : sans conversion, l'IK est aberrante (bassin faux de 84°
  sur l'essai de test).
- **L'augmentation de marqueurs LSTM n'est pas invariante par rotation** : elle normalise par la
  position de la hanche et la stature, sans recaler l'orientation. Une rotation de 30° autour de la
  verticale déplace les angles articulaires de 0,20° en médiane, jusqu'à 3,6° au subtalaire et 7°
  en prono-supination (mesuré sur un essai OpenCap). C'est une mise en garde pour tout utilisateur
  de Pose2Sim dont la calibration n'a pas une orientation canonique.

Conséquence : les deux variantes sont amenées dans **un seul et même repère**, en deux temps,
avant l'augmentation de marqueurs.

1. **Recalage 4 ddl de notre repère monde sur celui de la gold.** L'orientation autour de la
   verticale (lacet) et l'origine d'un repère monde sont arbitraires : ce ne sont pas des erreurs
   de calibration. Nos points 3D filtrés subissent donc la rotation autour de la verticale et la
   translation qui superposent au mieux nos centres de caméras à ceux de la gold
   (`recalage_hcst.json`). **La verticale et l'échelle ne sont pas corrigées** : nos erreurs sur ces
   deux points restent entières dans la comparaison. C'est la convention « 4 ddl » du niveau 1.
   Recaler sur 6 ddl redresserait notre verticale et masquerait une erreur réelle. Pose2Sim écrit
   ses `.trc` avec les axes permutés (le Z vertical de la calibration devient le Y vertical
   d'OpenSim) ; le recalage est exprimé dans ces coordonnées.
2. **Un repère canonique unique, calculé sur la variante gold** puis appliqué tel quel aux deux
   variantes :
   - verticale = direction moyenne chevilles → cou ;
   - axe X = déplacement horizontal du bassin sur la première seconde (sujet quasi immobile, tapis
     LBMC : normale à la ligne des épaules, moyennée sur l'essai) ;
   - origine = bassin à la première image, ramené au sol (2ᵉ centile de la hauteur des chevilles).

Avec un repère commun, les deux chaînes voient la même scène au même endroit, et la différence
d'angles ne vient plus que des calibrations. Le repère lui-même n'a plus besoin d'être stable
d'une variante à l'autre, puisqu'il n'est calculé qu'une fois. L'utilisation de la gold se limite
à ce recalage rigide de jauge, comme au niveau 1 : aucune version, aucun réglage n'est choisi en
comparant à la référence.

**Pourquoi pas un repère canonique par variante** (première version de l'étude) : chaque variante
devait retrouver la même direction de marche à partir de ses propres points, ce qui s'est révélé
fragile (§6, incidents 6 à 8). Surtout, chaque variante y estimait sa verticale sur ses propres points
(chevilles → cou), ce qui **effaçait notre erreur de verticale** au lieu de la laisser visible :
les écarts entre chaînes obtenus ainsi étaient légèrement optimistes (BioCV 0,42° contre 0,58°
avec le recalage 4 ddl).

## 4. Ce qui est comparé

- **Entre les deux chaînes** : pour chaque essai et chaque degré de liberté, RMSD sur tout l'essai
  (ou sa fenêtre), biais moyen, écart médian absolu et 95ᵉ centile. Degrés de liberté principaux
  (9) : bassin (inclinaison, obliquité, rotation), hanche (flexion, abduction, rotation), genou,
  cheville, subtalaire ; les côtés gauche et droit sont regroupés.
- **Face à l'optoélectronique**, sur les jeux qui fournissent une IK mocap : BioCV
  (`ik_gold_modele_mesh2sim.mot`), IMOVE (`ik_session_marche.mot`), OpenCap (`ik_mocap.mot`). Le
  décalage temporel avec la mocap est estimé **une fois par essai**, par corrélation sur la flexion
  de genou de la variante « gold », puis appliqué **à l'identique aux deux variantes** : c'est un
  paramètre de nuisance commun, il ne peut favoriser aucune des deux. On rapporte, par jeu, l'écart
  médian de chaque chaîne à la mocap et leur différence.
- **COMFI face à ses propres angles**. COMFI ne fournit pas d'IK OpenSim mais ses angles
  articulaires (`mocap/aligned/<id>/<tâche>/joint_angles.csv`, radians, alignés image par image sur
  les vidéos), issus d'un autre modèle. Pour 12 degrés de liberté (hanche, genou, cheville dans les
  plans disponibles), le signe et le décalage constant de chaque degré de liberté sont fixés **une
  seule fois sur la chaîne « gold »**, puis la même transformation est appliquée aux deux chaînes ;
  un décalage temporel de ±8 images est autorisé, estimé sur la chaîne « gold ». Seules les
  différences entre chaînes s'interprètent, pas les valeurs absolues. Le jeu ne fournit pas
  d'angles pour l'essai rectiligne du participant 2307 : cette comparaison porte donc sur 27 essais.

## 5. Plan statistique

- **Unité d'analyse** : l'essai. Pour chaque essai, RMSD par degré de liberté ; la valeur par essai
  est la médiane de ces RMSD ; le chiffre rapporté par jeu est la médiane des valeurs par essai. Les
  tests appariés portent sur ces mêmes valeurs par essai. Les autres agrégations (médiane de toutes
  les lignes, moyennes) donnent des valeurs voisines et ne changent aucune conclusion ; elles sont
  données en complément.
- **Équivalence** : déclarée si la borne haute de l'intervalle de confiance à 95 % du RMSD moyen
  entre essais reste sous la marge, pour chacun des 9 degrés de liberté principaux, avec correction
  de Bonferroni sur les 9 degrés de liberté ; TOST sur le biais en complément.
- **Marges** : **2°** en analyse principale (seuil clinique usuel en analyse de la marche, McGinley
  et al. 2009) ; **1°** en analyse de sensibilité.
- **Exclusions déclarées** : COMFI est exclu du test d'équivalence, sa référence ArUco étant moins
  juste que notre calibration face à la mocap (niveau 1 et comparaison ci-dessus) ; LBMC, avec
  2 essais, n'est pas interprétable statistiquement et reste descriptif.
- **Comparaisons appariées** entre chaînes : test de Wilcoxon signé sur les valeurs par essai.

## 6. Incidents et corrections, dans l'ordre où ils sont apparus

Signalés pour qu'aucun chiffre intermédiaire ne soit repris par erreur :

1. Repère monde en Z vertical non converti → repère canonique (§3).
2. Estimation de pose tombée sur CPU (`onnxruntime` CPU masquant la version GPU, et Pose2Sim testant
   `torch.cuda`) → `onnxruntime-gpu` seul et périphérique forcé en CUDA dans la configuration.
3. Détections partielles laissées par des runs interrompus, réutilisées sans contrôle → contrôle de
   complétude caméra par caméra (§1).
4. Fenêtre de validité de BioCV absente → `frame_range` depuis l'index de Mesh2Sim (§2).
5. Sens de l'axe de marche ambigu lors des allers-retours d'IMOVE → sens fixé sur l'orientation du
   corps (§3) ; seul le sujet 13 était touché et a été recalculé.
6. Repère canonique par variante, axe X = axe principal de la trajectoire : **instable en marche
   circulaire** (COMFI). Un cercle n'a pas d'axe principal, et 9 essais circulaires sur 14 sont
   sortis retournés de 180° entre les deux variantes.
7. Axe X = normale aux épaules sur dix images : défini partout mais bruité, avec un biais de
   rotation du bassin allant jusqu'à 8° (IMOVE). Axe X = premier mètre parcouru : faux sur un
   trajet courbe, parce que les deux variantes, d'échelles différentes, n'atteignent pas le mètre
   à la même image (12° sur COMFI).
8. → **Repère unique calculé sur la gold, notre variante recalée en 4 ddl** (§3). Validé sur les
   7 essais les plus touchés : biais de rotation du bassin sous 0,6° sur 6 d'entre eux, essais
   rectilignes revenus au niveau initial, essai circulaire COMFI 1118 de 8,2 à 2,3°.
9. **IK OpenSim en parallèle** : chaque IK occupait ~12 cœurs ; à 2 en parallèle, une IK passe de
   90 à 1 280 s. Les IK tournent un essai à la fois, bridées à un fil de calcul, ce qui les rend
   aussi plus rapides seules (64 s au lieu de 114 s sur IMOVE s11).

## 7. Où sont les fichiers

- Scripts (`~/humancalib_eval/`) : `level2_prepare.py` (montage des essais au format projet
  Pose2Sim), `level2_run.py` (chaîne Pose2Sim, contrôle des détections, repère canonique,
  sous-échantillonnage), `level2_batch.sh` et `watchdog_level2.sh` (lot et surveillance),
  `level2_analyse.py` (écarts et équivalence, marge réglable par `LEVEL2_MARGE`),
  `level2_vs_mocap.py` (comparaison à l'IK mocap), `comfi_angles_vs_mocap.py` (COMFI),
  `export_niveau2.py` (dossier de rédaction).
- Sorties brutes : `D:\FLO\Calibration dataset\level2\<jeu>_<essai>\{gold,hc}\trial\`.
- Chiffres pour la rédaction : `Article_pour_ClaudeScience\niveau2\donnees\`.
- Résultats : `03_RESULTATS.md` §18 (niveau 2) et §19 (moteurs et critère).
