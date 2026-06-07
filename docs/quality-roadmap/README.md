# dblift — Quality Roadmap to 9/10

This folder tracks the work needed to lift every quality dimension of dblift
from its current score to **9/10 or higher**. It is a living document; each
action item should be moved to `Done` (struck through with the PR link) as it
lands.

## Baseline (current scores, mai 2026 — branche `develop`)

| Critère | Actuel | Cible |
|---|---|---|
| Lisibilité & structure | 7.5 | 9.0 |
| Maintenabilité | 8.5 | 9.0 |
| Évolutivité | 8.0 | 9.0 |
| Modularité | 7.5 | 9.0 |
| Simplicité | 7.5 | 9.0 |
| Fiabilité & robustesse | 7.5 | 9.0 |
| Documentation | 8.5 | 9.0 |
| Tests | 7.2 | 9.0 |

The baseline rationale (strengths and weaknesses cited with `file:line`
references) is the source review delivered alongside this roadmap. Each action
item below was derived directly from one or more weaknesses identified there.

## Navigation

- [`priorities.md`](./priorities.md) — **toutes les actions triées par priorité
  P0 → P3**, avec effort estimé, impact, et critères d'acceptation. C'est la
  vue à consulter en premier pour planifier les sprints.
- [`categories.md`](./categories.md) — **mêmes actions regroupées par critère
  de qualité**, avec la note de départ, la note cible, et la liste des actions
  qui contribuent à chaque amélioration.

## Comment utiliser ce dossier

1. Au démarrage de chaque cycle de stabilisation, prendre les actions P0
   restantes puis remonter vers P1.
2. Une action peut améliorer plusieurs critères — le tableau dans
   `categories.md` rend ces croisements explicites.
3. Quand une action atterrit, mettre `[x]` devant la case, ajouter le numéro de
   PR sur la même ligne, et basculer le `Status` de la fiche détaillée dans
   `priorities.md`.
4. Aucun bonus point pour des actions hors-roadmap qui dégradent un score
   ailleurs — toute proposition doit être ajoutée ici et arbitrée d'abord.

## Convention de scoring

Une catégorie atteint **9/10** quand :

- les forces actuelles sont préservées ;
- toutes les actions marquées `target: 9` pour cette catégorie dans
  `categories.md` sont `[x] Done` ;
- aucune régression mesurable (couverture, complexité, nombre de violations
  flake8, etc.) n'est introduite entre temps.

10/10 est intentionnellement hors-portée — la note 9 est le bon optimum
qualité/coût pour un projet en stabilisation. Au-delà, le rendement marginal
décroche.

## Contraintes structurelles à respecter

- **Budget GitHub Actions** — la suite complète (unit + intégration sur 6
  dialectes) ne peut pas tourner sur chaque PR. `CONTRIBUTING.md` § "CI Test
  Evidence Policy" fige la règle : `push develop/main` ou `workflow_dispatch`
  uniquement. Toute action proposée ici doit respecter cette contrainte —
  les gates PR-time doivent être *sélectifs* (testmon, lint, mypy) plutôt que
  full-suite.
- **Programme de stabilisation v1.3.x → v2.0** — features gelées (`feat`
  type Conventional Commit interdit sauf approbation explicite). Les actions
  P0/P1 ici sont alignées avec ce périmètre.

## Méthodologie de priorisation

Chaque action est classée par `Priorité × Effort × Impact` :

| Priorité | Définition |
|---|---|
| **P0** | Quick wins (1–3 jours-ingénieur) ou bloquants méta (gates CI manquants). À traiter immédiatement. |
| **P1** | Travail structurant (1–2 semaines), améliore plusieurs catégories. À planifier sur le prochain cycle. |
| **P2** | Polish à moyen terme (2–4 semaines) ou amélioration mono-catégorie. Cycle suivant. |
| **P3** | Long terme / ambition (> 1 mois) ou très faible ROI immédiat. Backlog. |

L'effort est en **jours-ingénieur** (1 personne, focus). L'impact liste les
catégories de la matrice qui gagnent au moins +0.3 point sur leur note.
