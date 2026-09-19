# 06 — Références vérifiées

« Vérifié » = le document a été ouvert et la valeur lue ; « à vérifier » = citation connue
mais non rouverte pour ce travail. Compléter avant soumission.

## Tables anthropométriques (échelle depuis la stature)

| Source | Ce qu'on en tire | Statut |
|---|---|---|
| Drillis R., Contini R. (1966) *Body segment parameters*, rapport NYU 1166-03 ; reproduit dans Winter D.A., *Biomechanics and Motor Control of Human Movement*, 4e éd., fig. 4.1 | hauteurs hanche 0,530 H, genou 0,285 H, cheville 0,039 H, épaule 0,818 H → cuisse 0,245, tibia 0,246, tronc 0,288, vertex 0,182 | vérifié dans Winter (figure) ; échantillon et repères d'origine **non documentés** |
| de Leva P. (1996) Adjustments to Zatsiorsky-Seluyanov's segment inertia parameters, *J Biomech* 29(9):1223-1230, doi:10.1016/0021-9290(95)00178-6, table 4 | longueurs entre **centres articulaires** : hommes cuisse 422,2 / tibia 434,0 mm pour 1741 mm → 0,2425 + 0,2493 = **0,492** ; femmes 0,462 ; 100 H / 15 F | vérifié (table) |
| Contini R. (1972) Body segment parameters, part II, *Artificial Limbs* 16(1):1-19 | mêmes hauteurs hanche/genou (0,530 / 0,285) pour les hommes US ; 0,468–0,476 selon population | vérifié (figures) |
| ANSUR II (2012), données publiques | repères osseux : jambes/H 0,471 (H) / 0,480 (F), SD 0,016 ; recalé aux centres articulaires ≈ 0,477 / 0,486 ; variabilité individuelle ≈ 3 % (jambes), ≈ 5 % (tronc) | vérifié (calcul sur les CSV) |
| Harrington M.E. et al. (2007) Prediction of the hip joint centre in adults, children, and patients with cerebral palsy based on magnetic resonance imaging, *J Biomech* 40:595-602 | régression du centre de hanche utilisée pour la vérité marqueurs LBMC | à vérifier |

Aucun travail antérieur trouvé qui met une scène à l'échelle depuis la stature avec une
table nommée (Guan 2016, Fei 2021 supposent une taille moyenne ; arXiv 2604.17567
utilise un bâton de longueur connue).

## Seuils et statistiques

| Source | Usage |
|---|---|
| McGinley J.L. et al. (2009) The reliability of three-dimensional kinematic gait measurements: a systematic review, *Gait Posture* 29:360-369 | < 2° acceptable, 2–5° raisonnable, > 5° préoccupant → marge d'équivalence |
| Bland J.M., Altman D.G. (2007) Agreement between methods of measurement with multiple observations per individual, *J Biopharm Stat* 17:571-582 | Bland-Altman avec plusieurs essais par participant |
| Schuirmann D.J. (1987) TOST, *J Pharmacokinet Biopharm* 15:657-680 | test d'équivalence apparié |
| Umeyama S. (1991) *IEEE TPAMI* 13(4):376-380 | superposition similitude (7 ddl) |
| Zhang Z., Scaramuzza D. (2018) A tutorial on quantitative trajectory evaluation, *IROS* | alignement 4 ddl (lacet + translation) |
| Challis J.H., Kerwin D.G. (1992) Accuracy assessment and control point configuration when using the DLT, *J Biomech* 25:1053-1058 | conditionnement / couverture spatiale |

## Calibration par la pose humaine (état de l'art)

Lee et al. 2022 *RA-L* (10.1109/LRA.2022.3192629) ; Takahashi et al. CVPRW 2018 ;
Pätzold, Bultmann, Behnke GCPR 2022 (arXiv 2209.07393) ; Lee, Nishino, Nobuhara 2025
(arXiv 2502.12546) ; Xu et al. CVPR 2021 (arXiv 2104.08568) ; CasCalib (arXiv 2405.06845) ;
HSfM CVPR 2025 (arXiv 2412.17806) ; Kineo (arXiv 2510.24464) ; Yang et al. 2026
(arXiv 2604.17567). Liste reprise de `docs/EVALUATION_PROTOCOL.md` §12, à relire.

## Outils et jeux de données

- Pose2Sim : Pagnon D. et al., *Sensors* 2021 (10.3390/s21196530) et 2022 (10.3390/s22072712).
- OpenCap : Uhlrich S.D. et al., *PLoS Comput Biol* 2023 (10.1371/journal.pcbi.1011462).
- BioCV : Needham L. et al., *J Biomech* 2022 (10.1016/j.jbiomech.2022.111338) ; à confirmer
  comme référence du jeu.
- LBMC : Muller A., Robert T. (2025) Benchmarking dataset for markerless motion capture
  analysis, doi:10.57745/LQI2MJ, licence Etalab 2.0 + charte d'utilisation (signée).
- IMOVE-23 : référence de publication **à retrouver**.
- COMFI (LAAS-CNRS, Toulouse) : référence **à retrouver** à réception du jeu.
- MeTRAbs : Sárándi I. et al., *IEEE T-BIOM* 2021 ; RTMPose : Jiang T. et al. 2023
  (arXiv 2303.07399) ; VideoPose3D : Pavllo D. et al., CVPR 2019. À vérifier.
