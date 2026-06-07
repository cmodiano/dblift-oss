# Plan d'action regroupé par critère de qualité

> Référence : voir [`README.md`](./README.md) pour la méthodologie et
> [`priorities.md`](./priorities.md) pour les fiches détaillées de chaque
> action numérotée.

Chaque section liste : la note actuelle, la note cible (9), un résumé des
faiblesses identifiées, et la liste des actions (numéros référant à
`priorities.md`) qui contribuent à fermer l'écart. Lorsqu'une action
contribue à plusieurs catégories, elle apparaît dans chacune avec le **gain
estimé** sur cette catégorie.

---

## Lisibilité & structure — 7.5 → 9.0

**Faiblesses ciblées**
- `cli/main.py::main()` > 250 lignes.
- `cli/_command_handlers.py::_handle_validate_sql` à 137 lignes,
  imbrication 5+.
- Couverture inégale des type hints (`core/migration/migration.py` ~27 %).
- `.flake8` ignore 1 547 violations sans trajectoire de réduction.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 4 | Linter de docstrings sur `core/` + `cli/` | +0.4 | P0 |
| 5 | Ratchet flake8 E501 | +0.4 | P0 |
| 6 | Refactor `cli/main.py::main()` en 4 phases | +0.3 | P0 |
| 8 | Mypy strict `core/migration/` + `core/comparison/` | +0.3 | P1 |
| 9 | Décomposer fonctions E/F-rank résiduelles | +0.2 | P1 |
| 14 | Remplacer `__getattr__` dans `comparator.py` | +0.1 | P1 |
| 15 | Module docstrings `db/plugins/<X>/` | +0.2 | P1 |

**Définition de "atteint 9"** — les 4 actions P0 sont livrées + au moins 2
actions P1 (#8 et #9 prioritaires). Toute fonction publique a une docstring
exigible par CI.

---

## Maintenabilité — 8.5 → 9.0

**Faiblesses ciblées**
- 1 547 violations flake8 acceptées sans trajectoire de cleanup.
- `config/database_config.py` (1 504 LOC) et `config/dblift_config.py`
  (1 061 LOC) restent gros.
- Couverture mypy strict progressive ; pas encore global.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 5 | Ratchet flake8 E501 | +0.2 | P0 |
| 6 | Refactor `cli/main.py::main()` | +0.1 | P0 |
| 8 | Mypy strict `core/migration/` + `core/comparison/` | +0.2 | P1 |
| 9 | Décomposer fonctions E/F-rank | +0.3 | P1 |
| 17 | Découper classes de test monolithiques | +0.1 | P2 |
| 25 | Mypy strict global | +0.3 | P3 |
| 27 | Xenon `max-absolute = C` | +0.2 | P3 |

**Définition de "atteint 9"** — flake8 baseline strictement décroissant
≥ 6 mois, mypy strict couvre `core/` à 100 %, aucune fonction au rang F dans
`config/`.

---

## Évolutivité — 8.0 → 9.0

**Faiblesses ciblées**
- Comparator registry hardcodé (édition de `comparator.py:95` requise).
- ~25 occurrences de `# lint: allow-dialect-string` subsistent.
- `DbliftConfig` lookup par string, pas de résolution dynamique via le
  ProviderRegistry.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 11 | Plugin API pour classes de config | +0.4 | P1 |
| 13 | Comparator registry pluggable | +0.4 | P1 |
| 24 | Éliminer `# lint: allow-dialect-string` résiduels | +0.3 | P2 |

**Définition de "atteint 9"** — un dialecte tiers peut être ajouté **sans
toucher** au code de `core/` ni `config/`. Toute logique dialect-specific
vit dans `db/plugins/<X>/`. Le test d'intégration tiers fictif passe.

---

## Modularité — 7.5 → 9.0

**Faiblesses ciblées**
- `core/sql_generator/__init__.py:39-48` ré-exporte des generators depuis
  `db/plugins/` (couplage soft inversé).
- `__getattr__` paresseux dans `core/comparison/comparator.py`.
- Config non pluggable.
- Patterns d'accès mixtes au `ProviderRegistry`.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 2 | Sortir `site/` du repo | +0.2 | P0 |
| 11 | Plugin API pour classes de config | +0.3 | P1 |
| 12 | Supprimer ré-exports `core/sql_generator/__init__.py` | +0.4 | P1 |
| 14 | Remplacer `__getattr__` dans `comparator.py` | +0.3 | P1 |

**Définition de "atteint 9"** — `grep -r "from db.plugins" core/` retourne
zéro match. Pas d'autre import paresseux non documenté. Tous les accès
externes au `ProviderRegistry` passent par `api/_cli_support`.

---

## Simplicité — 7.5 → 9.0

**Faiblesses ciblées**
- 8 types de DB enums + ConfigBuilder + DbliftConfig (~25 attributs) =
  surface de configuration élevée.
- Fonctions encore au plafond F-rank de Xenon.
- 4-5 hops CLI → executor pour une opération triviale.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 6 | Refactor `cli/main.py::main()` | +0.2 | P0 |
| 9 | Décomposer fonctions E/F-rank | +0.4 | P1 |
| 12 | Supprimer ré-exports backward-compat | +0.2 | P1 |
| 26 | Réduire indirections CLI → executor ≤ 3 hops | +0.3 | P3 |
| 27 | Xenon `max-absolute = C` | +0.2 | P3 |
| 28 | Alternatives au `ConfigBuilder` | +0.2 | P3 |

**Définition de "atteint 9"** — aucune fonction publique > 60 lignes ;
aucune complexité > C ; appel CLI → executor en ≤ 3 hops mesurés.

---

## Fiabilité & robustesse — 7.5 → 9.0

**Faiblesses ciblées**
- 568 `except Exception:` dans le code.
- `execution_engine.py:957` `except Exception: pass` silencieux.
- Pas de doc de recovery sur crash JVM ou mid-migration.
- Plancher de couverture non enforcé (CI ne casse pas si la couverture régresse).
- Substitution silencieuse de `${DB_PASSWORD}` manquante.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 1 | Patch coverage PR via `pytest-testmon` (+ filet absolu push develop) | +0.3 | P0 |
| 7 | Remplacer `except Exception:` chemin chaud | +0.5 | P0 |
| 8 | Mypy strict `core/migration/` | +0.2 | P1 |
| 10 | Runbooks de recovery dans `docs/operations/` | +0.4 | P1 |
| 18 | Tests dédiés `execution_engine.py` | +0.3 | P2 |
| 19 | Quarantaine pour tests flaky | +0.1 | P2 |
| 20 | Benchmarks chemins chauds | +0.1 | P2 |

**Action additionnelle ciblée robustesse (à ouvrir comme action #31)**
- [ ] **#31 — Validation stricte des `${ENV}` placeholders au chargement de
  config.** Warning ou erreur si une variable d'env référencée n'est pas
  définie. Effort 0.5j, P0, gain Fiabilité +0.2.

**Définition de "atteint 9"** — zéro `except Exception:` non commenté dans
le chemin chaud, runbooks recovery complets, tout test d'erreur fournit un
type d'exception précis.

---

## Documentation — 8.5 → 9.0

**Faiblesses ciblées**
- Couverture docstrings inégale hors `api/`.
- Type hints non stricts globalement.
- `example/` léger ; pas d'exemple Python.
- Risque de divergence `database-providers.md` vs `adding-database-support.md`.
- `site/` rendu commité dans le repo.

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 2 | Sortir `site/` du repo | +0.1 | P0 |
| 3 | Supprimer `coverage.json` stale | +0.1 | P0 |
| 4 | Linter de docstrings sur `core/` + `cli/` | +0.3 | P0 |
| 10 | Runbooks de recovery | +0.2 | P1 |
| 15 | Module docstrings `db/plugins/<X>/` | +0.2 | P1 |
| 22 | Consolider doc des providers | +0.1 | P2 |
| 23 | Exemple Python complet | +0.2 | P2 |
| 29 | Diagrammes d'architecture par flow | +0.2 | P3 |

**Définition de "atteint 9"** — linter docstrings vert sur `core/`, `cli/`,
`db/plugins/`. Site mkdocs généré depuis CI. Au moins 1 exemple Python E2E
testé. Une seule source de vérité pour "ajouter un dialecte".

---

## Tests — 7.2 → 9.0

**Faiblesses ciblées**
- 6 879 mocks ; tests mock-heavy plutôt que real-execution.
- `coverage.json` à 6.6 % (stale) ; plancher 77 % non enforcé.
- Classes de tests monolithiques (test_main_cli_direct.py 1.8k LOC).
- Benchmarks quasi-idle (1 fichier, dispatch manuel).
- Pas de tests de mutation ; pas de quarantine flaky.
- Pas de mapping 1:1 source/test (execution_engine.py sans test dédié).

**Actions contributives**

| # | Action | Gain estimé | Priorité |
|---|---|---|---|
| 1 | Patch coverage PR via `pytest-testmon` | +0.5 | P0 |
| 3 | Supprimer `coverage.json` stale | +0.1 | P0 |
| 16 | Réduire mock-heaviness top 10 fichiers | +0.4 | P2 |
| 17 | Découper classes de test monolithiques | +0.3 | P2 |
| 18 | Tests dédiés `execution_engine.py` | +0.3 | P2 |
| 19 | Quarantaine flaky | +0.1 | P2 |
| 20 | Benchmarks chemins chauds | +0.2 | P2 |
| 21 | Essai tests de mutation | +0.2 | P2 |
| 30 | CI mutation testing modules changés | +0.2 | P3 |

**Définition de "atteint 9"** — couverture ≥ 80 % enforced, aucun fichier
test > 500 LOC, mapping 1:1 src/tests pour les modules core, benchmarks
avec baseline et regression gate. Mutation testing actif sur `api/` au
minimum.

---

## Matrice récapitulative effort × impact

Synthèse de toutes les actions classées par leverage (impact total / effort).
Idéal pour planifier un sprint.

| # | Action | Effort (j) | Catégories impactées | Leverage |
|---|---|---|---|---|
| 3 | Supprimer `coverage.json` stale | 0.1 | Tests, Doc | ⭐⭐⭐⭐⭐ |
| 2 | Sortir `site/` du repo | 0.5 | Doc, Modularité | ⭐⭐⭐⭐⭐ |
| 1 | Patch coverage PR (testmon) + filet 77 % push develop | 2-3 | Tests, Fiabilité | ⭐⭐⭐⭐⭐ |
| 19 | Quarantaine flaky | 1 | Tests, Fiabilité | ⭐⭐⭐⭐ |
| 6 | Refactor `cli/main.py::main()` | 1 | Lisibilité, Maint, Simpl | ⭐⭐⭐⭐ |
| 14 | Remplacer `__getattr__` comparator | 1 | Modularité, Lisibilité | ⭐⭐⭐⭐ |
| 23 | Exemple Python complet | 1.5 | Doc | ⭐⭐⭐ |
| 4 | Linter docstrings core/cli | 2 | Doc, Lisibilité | ⭐⭐⭐⭐ |
| 5 | Ratchet flake8 E501 | 1+continu | Lisibilité, Maint | ⭐⭐⭐⭐ |
| 15 | Module docstrings plugins | 2 | Doc, Lisibilité | ⭐⭐⭐ |
| 22 | Consolider doc providers | 1 | Doc | ⭐⭐⭐ |
| 7 | Remplacer `except Exception:` | 3 | Fiabilité | ⭐⭐⭐⭐⭐ |
| 10 | Runbooks recovery | 3 | Fiabilité, Doc | ⭐⭐⭐⭐ |
| 13 | Comparator registry pluggable | 3 | Évolutivité | ⭐⭐⭐ |
| 18 | Tests `execution_engine.py` | 3 | Tests, Fiabilité | ⭐⭐⭐⭐ |
| 20 | Benchmarks chemins chauds | 3 | Tests, Fiabilité | ⭐⭐⭐ |
| 24 | Éliminer dialect-strings | 3 | Évolutivité | ⭐⭐⭐ |
| 12 | Supprimer ré-exports sql_generator | 1 (+1 cycle) | Modularité, Simpl | ⭐⭐⭐⭐ |
| 9 | Décomposer fonctions E/F-rank | 4 | Simpl, Maint, Lisib | ⭐⭐⭐⭐ |
| 11 | Plugin API config | 4 | Évolutivité, Modularité | ⭐⭐⭐ |
| 21 | Essai mutation tests | 4 | Tests | ⭐⭐ |
| 8 | Mypy strict core/migration | 5 | Maint, Fiab, Lisib | ⭐⭐⭐⭐ |
| 17 | Découper classes de tests | 5 | Tests, Maint | ⭐⭐⭐ |
| 26 | Réduire indirections | 5 | Simplicité | ⭐⭐ |
| 28 | Alternatives ConfigBuilder | 5 | Simplicité | ⭐⭐ |
| 16 | Réduire mock-heaviness | 8 | Tests, Fiabilité | ⭐⭐⭐ |
| 25 | Mypy strict global | 10+ | Maint, Doc, Fiab | ⭐⭐⭐ |
| 27 | Xenon max-absolute = C | continu | Maint, Simpl | ⭐⭐ |
| 29 | Diagrammes par flow | 3 | Doc | ⭐⭐ |
| 30 | CI mutation testing | 5 | Tests | ⭐⭐ |
