# Dossier article — HumanCalib évalué contre des calibrations de référence

Synthèse rédigée pour écrire l'article (ou pour qu'un assistant le rédige) sans relire
tout l'historique. Tout ce qui est écrit ici a été mesuré ; ce qui n'est pas encore fait
est marqué **À FAIRE**. Les chiffres bruts sont dans `~/humancalib_eval/` (machine de
Florian) et sur `D:\FLO\Calibration dataset\` ; les figures dans
`D:\FLO\Calibration dataset\Figures\` ; les références cinématiques (IK mocap) dans
`D:\FLO\DATASET MARKERLESS\_EXPORT_ARTICLE\gold\`.

| Fichier | Contenu |
|---|---|
| [01_METHODE.md](01_METHODE.md) | La méthode telle qu'elle est évaluée (version figée v4), ses briques, ses choix et pourquoi |
| [02_DATASETS.md](02_DATASETS.md) | Les cinq jeux de données, leurs références, leurs pièges, comment ils sont préparés |
| [03_RESULTATS.md](03_RESULTATS.md) | Tous les résultats obtenus à ce jour, avec les tableaux |
| [04_PLAN_EXPERIENCES.md](04_PLAN_EXPERIENCES.md) | Métriques retenues, plan des runs, taille d'échantillon, statistiques |
| [05_DECISIONS.md](05_DECISIONS.md) | Journal des décisions méthodologiques et des erreurs corrigées |
| [06_REFERENCES.md](06_REFERENCES.md) | Bibliographie vérifiée (tables anthropométriques, seuils cliniques, jeux de données) |
| [07_NOTES_REDACTION.md](07_NOTES_REDACTION.md) | Plan de l'article, messages clés, chiffres à reprendre, figures, ce qui manque |

Documents liés dans le dépôt :
- `docs/EVALUATION_PROTOCOL.md` : protocole complet et journal daté (source primaire, très détaillé).
- `src/humancalib/evaluation/` : lecteurs de chaque jeu (`biocv.py`, `opencap.py`, `imove.py`, `lbmc.py`),
  comparaison (`compare.py`, `metrics.py`), figures (`plot_rig.py`), lots (`batch.py`).

Règles que l'on s'est fixées pour l'article :
- rapporter la **distribution par essai**, échecs compris, jamais le meilleur essai seul ;
- aucune constante d'échelle ajustée sur les données d'évaluation ;
- les métriques principales sont figées avant les runs définitifs (voir 04) ;
- la resynchronisation d'OpenCap n'est pas une contribution ni une méthode décrite ; la
  synchronisation utilisée est documentée dans 05 (décisions successives du 17/09).
