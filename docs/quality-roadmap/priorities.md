# Plan d'action trié par priorité

> Référence : voir [`README.md`](./README.md) pour la méthodologie et
> [`categories.md`](./categories.md) pour la vue par critère.

Chaque fiche suit le format :

```
### N. Titre court
- Status: Todo / In progress / Done (#PR)
- Effort: Xj
- Impact: catégories qui gagnent ≥ +0.3
- Problème
- Action
- Critères d'acceptation
- Risques / dépendances
```

---

## P0 — À démarrer immédiatement (quick wins, gates CI bloquants)

### 1. Patch coverage sur PR via `pytest-testmon` (sélectif, < 2 min) — **REVERTED**
- [x] Status: Reverted (1.6.0). Le workflow `pr-patch-coverage.yml` et
  l'instrumentation testmon associée sont supprimés.
- **Pourquoi le rollback** — deux problèmes structurels sont apparus en
  production :
  1. **L'index testmon ne reste jamais chaud sur develop.** Le workflow
     `unit-tests.yml` ne tourne plus sur push develop (intentionnel,
     contrainte budget — voir commit `d04a661`), donc le cache
     `testmon-py3.11-develop-*` n'est jamais rafraîchi. Chaque PR retombe
     sur un fallback `restore-keys` très large qui ramène un index
     périmé ou nul ; testmon dégrade alors en "run all tests" pour des
     raisons de sûreté. Le supposé gain de sélectivité (~2 min P95) ne
     se matérialise jamais — le job tourne la suite quasi complète.
  2. **Le patch ≥ 80 % unit-only est trompeur.** Le projet a des suites
     d'intégration substantielles (postgresql, mysql, sqlserver, db2,
     oracle, cosmosdb, sqlite) qui contribuent significativement à la
     couverture finale. Gater à 80 % sur la couverture *unit* d'un
     diff fait échouer des PR dont les lignes touchées sont en réalité
     couvertes par les tests d'intégration — faux négatif systémique.
- **Alternatives évaluées avant rollback**
  - *Re-déclencher `unit-tests.yml` sur push develop* — 15+ min × matrix
    Python 3.11/3.12, multiplié par le throughput de merges develop :
    explose le budget GitHub Actions.
  - *Refresh nightly de l'index testmon* — viable techniquement mais ne
    règle pas le problème #2 (le patch unit-only reste trompeur), et
    ajoute de la mécanique pour un gate informatif.
  - *Refresh PR-time via second pytest invocation `--testmon-noselect`* —
    coûte autant qu'une exécution complète, défait le but du gate.
- **Cleanup livré**
  1. Suppression de `.github/workflows/pr-patch-coverage.yml`.
  2. Suppression des étapes "Restore testmon index", "Update testmon
     index", "Save testmon index" dans `unit-tests.yml`.
  3. Suppression du flag `pr-patch` et de la règle
     `individual_flags` correspondante dans `codecov.yml`.
  4. Retrait de `pytest-testmon>=2.2.0` de `pyproject.toml` et
     `requirements-dev.txt`.
  5. Mise à jour de la section "CI Test Evidence Policy" dans
     `CONTRIBUTING.md` pour refléter le nouveau modèle de gate
     (lint + xenon + bandit + gitleaks + pip-audit + regression
     matrix sur PR ; full unit + integration au release time).
- **Gate de remplacement** — Le filet de sécurité absolu `unit-tests.yml`
  + `--cov-fail-under=77` sur push main / release reste l'autorité.
  PR-time : checks légers + signal Bugbot / CodeRabbit / review humaine.

### 2. Sortir `site/` du repo et générer le site via CI
- [x] Status: Done (#339) — 71 fichiers untrackés, `docs.yml` continue
  de build + déployer le site fresh à chaque push main.
- Effort: 0.5j
- Impact: Documentation, Modularité
- **Problème** — 71 fichiers HTML/CSS générés par mkdocs étaient commités
  dans `site/` malgré la règle `site/` déjà présente à `.gitignore:85`
  (probablement ajoutés via `git add -f` ou commit antérieur à la règle).
  Pollue le diff, peut diverger des sources, alourdit le clone (~quelques MB).
- **Action**
  1. `.gitignore` déjà à jour (vérifié `site/` ligne 85, aucune modif).
  2. `git rm -r --cached site/` pour untracker les 71 fichiers.
  3. `.github/workflows/docs.yml` déjà en place : build via `mkdocs build`
     sur push develop / main, deploy GitHub Pages sur push main via
     `actions/upload-pages-artifact@v5` + `actions/deploy-pages@v5`.
     Aucun changement requis — le site continue d'être publié frais à
     chaque push main.
- **Critères d'acceptation**
  - `git ls-tree HEAD site/` retourne vide.
  - Le site mkdocs reste accessible (URL inchangée).

### 3. Supprimer le `coverage.json` stale
- [x] Status: Done (#338) — fichier untracké, `coverage.json` +
  `coverage-*.json` ajoutés à `.gitignore`.
- Effort: 0.1j
- Impact: Tests, Documentation
- **Problème** — `coverage.json` est commité à 6.6 % (rapport d'avril 2025),
  contredit le plancher 77 % et trompe quiconque l'ouvre.
- **Action** — `git rm coverage.json` + ajouter `coverage.json` et
  `coverage-*.json` à `.gitignore` (le pattern `.coverage*` ne couvre que
  le binaire avec point initial, pas le `.json` à la racine).
- **Critères d'acceptation** — fichier absent du repo, CI inchangée
  (la couverture est régénérée par chaque run codecov côté CI).

### 4. Étendre `check_api_docstrings.py` à `core/` et `cli/`
- [x] Status: Done (#340) + drive-to-zero complete (PR 1 #368, PR 2 this PR) —
  `--paths` + `--ratchet` shipped ; `.docstring-ratchet.json` désormais à
  `api=0, cli=0, core=0, db=0` (gate uniformément strict sur tous les
  roots, campagne `core/` 143 → 0 terminée en deux PRs) ; nouvelle
  heuristique privacy "public method on private class inherits privacy"
  + walk full chain (post-Bugbot).
- Effort: 2j
- Impact: Documentation, Lisibilité
- **Problème** — le linter de docstrings AST n'opérait que sur `api/`. Les
  modules `core/migration/`, `core/comparison/` accumulaient des manques de
  module/class docstrings sans gate CI.
- **Action livrée**
  1. `scripts/check_api_docstrings.py` accepte maintenant `--paths` (multi-root)
     et `--ratchet PATH` pour charger un cap par root.
  2. Heuristique privacy enrichie : une méthode (et `__init__`) d'une
     classe `_Private` hérite de la privacité — élimine les faux positifs
     sur classes nested helper (ex. `_Result` dans `_minimal_result`).
  3. **Ratchet `.docstring-ratchet.json`** au lieu d'un baseline
     fingerprint-style — appropriate quand les violations se comptent
     en centaines et que l'annotation inline-par-violation noierait les
     sources. Caps initiaux : `api=0`, `cli=0`, `core=127`. Le script
     suggère un cap plus serré quand le count chute (force la
     monotonie décroissante par PR).
  4. CI gate dans `.github/workflows/code-quality.yml` : la step
     existante api-strict est remplacée par
     `--paths api cli core --ratchet .docstring-ratchet.json`.
- **Critères d'acceptation atteints**
  - Toute nouvelle classe/fonction publique sans docstring dans `api/`
    ou `cli/` fait échouer la CI.
  - Toute PR qui pousse le count `core/` au-dessus de 127 échoue.
  - Toute PR qui baisse `core/` < 127 émet un nudge "lower the cap".

### 5. Démarrer le ratchet flake8 E501 (lignes longues)
- [x] Status: Done (#341) — `scripts/check_line_length.py` + ratchet
  `api=1, cli=20, config=13, core=550, db=400` ; gate CI dans
  `code-quality.yml`. "Keep in sync" docstring sur `_load_ratchet`
  documente la duplication assumée (rule-of-three pas encore atteinte).
- Effort: 1j (setup) + courant sur 2 cycles
- Impact: Lisibilité, Maintenabilité
- **Problème** — 984 violations E501 ignorées dans `.flake8` sans
  trajectoire de cleanup. Black à 100 chars ne split pas tout
  (string literals, signatures lourdes, commentaires denses).
- **Action livrée**
  1. `E501` reste dans `.flake8 ignore` (trop de dette pour faire échouer
     le job flake8 principal). Un gate séparé monte la garde.
  2. `scripts/check_line_length.py` lance
     `flake8 --isolated --select=E501 --max-line-length=100` sur les
     5 roots et compare au cap par-root dans `.flake8-e501-ratchet.json`.
     Même UX que `check_api_docstrings.py --ratchet` : fail si N>cap,
     pass + nudge "you can lower the cap by N" si N<cap.
  3. Caps initiaux (mesure sur develop `a55abd9`) :
     `api=1, cli=20, config=13, core=550, db=400` (au lieu des 1 147
     cités dans le roadmap — l'ancien chiffre incluait probablement
     `tests/`+`scripts/`).
  4. Step CI ajoutée dans `.github/workflows/code-quality.yml`
     ("Line-length ratchet (flake8 E501)").
- **Critères d'acceptation atteints**
  - Toute PR qui ajoute une ligne > 100 chars dans un root échoue.
  - Toute PR qui en supprime émet un nudge ; le contributeur commit
    le cap réduit dans la même PR.

### 6. Refactor `cli/main.py::main()` en 3-4 phases nommées
- [x] Status: Done (#342) — `main()` à rang radon **A (2)**, 4 helpers
  privés + `_CliContext` dataclass. Sémantique d'exit préservée
  (return None on success, sys.exit on failure).
- Effort: 1j
- Impact: Lisibilité, Maintenabilité, Simplicité
- **Problème** — fonction de 250+ lignes orchestrant parsing argv, license
  gate, logger setup, dispatch. Complexité Xenon élevée.
- **Action livrée** — `cli/main.py::main()` réduit à 4 lignes d'orchestration
  + docstring. État partagé encapsulé dans `_CliContext` (dataclass privé,
  8 champs annotés par phase d'écriture). 4 helpers privés :
  - `_parse_argv_and_load_config(argv) -> _CliContext` — extraction argv,
    namespace construction, 3 short-circuits terminaux (--version, no-args,
    license), config load + db_config validation.
  - `_gate_license(ctx) -> None` — LicenseManager.get_info, exit 1 sur
    LicenseError, persiste le token via `core.licensing._guard`.
  - `_setup_logging_and_output(ctx) -> CommandOutput` — short-circuit `db`
    subcommand, `_configure_logging`, attache license_info aux formatters,
    retourne le `CommandOutput` du workflow.
  - `_dispatch_command(ctx, output) -> int` — scripts dir resolution,
    client construction, placeholders, banner, multi-command loop dans
    try/except. Retourne 0 ou 1.
- **Critères d'acceptation atteints**
  - `radon cc cli/main.py` rapporte `main` en rang **A (1)**.
  - Aucun changement de comportement observable : mêmes branchements,
    mêmes ordres d'exit, mêmes side-effects sur les modules globaux
    (`base_command._console_main_header_printed`, etc.). Les 1.1k tests
    `test_main_cli*.py` pinnent le contrat ; ils valident en CI.

### 7. Remplacer les `except Exception:` du chemin chaud
- [x] Status: Done (#343) — 3 narrows dans les connection_managers
  (postgresql/sqlserver → `JAVA_EXC`, cosmosdb → `(AttributeError,
  ValueError)`). 3 sites Bucket A dans `execution_engine.py` gardés
  broad avec commentaires "rollback safety net" expliquant pourquoi.
  6 tests de régression fault-injection. Scope original ~20 sites
  invalidé par audit ; 14 autres sites Bucket B/C documentés et
  reportés.
- Effort: ~1j (scope révisé après audit)
- Impact: Fiabilité
- **Audit** — sur 21 `except Exception:` dans le scope cible (18 dans
  `core/migration/`, 3 dans `db/plugins/*/connection_manager.py`), un
  triage agent révèle 3 buckets :
  - **Bucket A — Rollback safety net (5 sites)** : le broad catch est
    CORRECT, on veut rollback sur n'importe quelle erreur puis re-raise.
    Narrow casserait le filet de sécurité.
  - **Bucket B — Best-effort SQLState/ErrorCode/formatting extraction
    (4 sites)** : narrow possible mais hasardeux (JNI/jpype peut lever
    n'importe quoi). Laisser broad avec commentaire.
  - **Bucket C — Ignore expected (12 sites)** : sqlglot parse fallbacks,
    decode/decompress fallbacks, introspection best-effort, JDBC close
    sur connexion morte, URL parse. Narrowable proprement.
- **Action livrée — scope minimal** :
  1. **3 narrows** dans les connection_managers (Bucket C) :
     - `postgresql/sqlserver` : `except Exception:` → `except JAVA_EXC:`
       (`db._jdbc_exceptions.JAVA_EXC` = `(jpype.JException,
       AttributeError, ValueError, TypeError, OSError, RuntimeError)` —
       la tuple canonique JDBC-boundary du projet).
     - `cosmosdb` : `except Exception:` → `except (AttributeError,
       ValueError):` (urllib.parse boundary).
  2. **Commentaires "rollback safety net"** ajoutés aux 3 sites
     `execution_engine.py` (Bucket A) qui en manquaient — explicitent
     pourquoi le broad catch est intentionnel et où le narrow se fait
     au call-site, pas ici.
  3. **3 tests de régression** dans
     `tests/unit/db/plugins/test_connection_manager_typed_exceptions.py`
     — pour chaque narrow, un cas in-tuple (swallowed, comportement
     pré-narrow préservé) et un cas out-of-tuple (KeyError synthetic
     propagated, comportement nouveau).
- **Critères d'acceptation atteints**
  - `grep -En "^[[:space:]]*except Exception:" core/migration/executor/
    db/plugins/*/connection_manager.py` retourne **3** matches (tous
    dans `execution_engine.py`, tous Bucket A avec commentaire "rollback
    safety net" expliquant pourquoi le broad est correct). Critère
    roadmap "< 5 avec annotation" ✓.
- **Hors scope (reporté en P3 si besoin)**
  - Les 4 sites Bucket B + 9 sites Bucket C restants — l'audit montre
    qu'ils sont déjà annotés ou bénéficieraient peu d'un narrow vs le
    risque de casser un fallback fonctionnel. Reportés conscientes.

---

## P1 — Cycle suivant (travail structurant multi-catégorie)

### 8. Étendre la mypy strict zone à `core/migration/` et `core/comparison/`
- [x] Status: Done (#H13g, dernière vague mergée) — `core/migration/`
  100% strict après 7 vagues (H13a-g), `core/comparison/` 100% strict
  depuis H4. Total : ~40 modules ajoutés, ~250 erreurs strict corrigées,
  4 vrais bugs de type détectés, ratchet E501 core `550 → 545`.
- Effort: 5j total — découpé en mini-PRs par sous-package
- Impact: Maintenabilité, Fiabilité, Lisibilité, Documentation
- **Audit (sur develop `d55e3d2`)** — `core/comparison/` 100% strict
  depuis la vague H4. `core/migration/` ~50 modules restants
  hors-strict, distribués sur : `commands/` (13), `executors/` (5),
  `executor/migration_executor.py` (1), `scripting/undo_script_generator`
  (6), `formats/` (3), `history/` (2), `journals/` (2), `snapshots/`
  (3), `ui/` (4), root leaves (6), ~5 `__init__.py`.
- **Action** — un mini-PR par sous-package, dans l'ordre risque croissant :
  - **Wave H13a — mergé (#344)** : `formats/` (3 modules) +
    `history/` (1 module). 6 erreurs strict corrigées.
  - **Wave H13b — mergé (#345)** : `journals/` (1 module) +
    `executor/migration_executor.py` (complète le sous-package
    `executor/`). 24 erreurs corrigées (5 journals + 19 executor).
  - **Wave H13c — mergé (#346)** : `undo_script_generator/` 5 modules
    restants (complète le sous-package). 29 erreurs corrigées + 1 fix
    CI (mypy 2.x narrowing trap : `table_name: Optional[str]` déclaré
    explicitement plutôt que retirer un `# type: ignore[assignment]`).
  - **Wave H13d — mergé (#347)** : `snapshots/schema_snapshot_service`
    (clôt snapshots/) + `executors/` 5 modules pluriel (clôt executors/).
    40 erreurs corrigées + 1 vrai bug `_filter_tables` détecté.
  - **Wave H13e — mergé (#348)** : root leaves `core/migration/` —
    `__init__`, `_type_match`, `clean_summary`, `encoding`,
    `migration.py`, `version_utils.py` (6 modules, 24 erreurs +
    suppression d'un `# type: ignore[no-untyped-call]` retiré en
    cascade une fois `dict_to_migration` typé).
  - **Wave H13f — mergé (#349)** : `ui/` 3 modules — clôt le sous-package
    ui/. 51 erreurs corrigées + 1 vrai bug de signature détecté.
  - **Wave H13g — PR ouverte** : `commands/` 13 modules — clôt le
    sous-package commands/ (dernier sous-package de `core/migration/`).
    79 erreurs corrigées dans 12 modules touchés (`base_command`,
    `clean_command`, `repair_command`, `snapshot_command`,
    `export_schema_command`, `_managed_object_filter`, `_diff_snapshot`).
    Majoritairement `type-arg` (`List[Dict]` → `List[Dict[str, Any]]`,
    `tuple` → `Tuple[...]`), `no-untyped-def` (params `config`,
    `executor`, `**kwargs`), et 4 stale `# type: ignore` retirés.
    Action #8 désormais **complète** : `core/migration/` 100% strict.
- **Critères d'acceptation par wave** — chaque mini-PR fait passer son
  sous-package en strict sans `# type: ignore` non-motivé ; le full
  mypy run sur `api/ cli/ config/ core/ db/` reste à 0 erreur (hors
  bruit env local types-PyYAML).

### 9. Décomposer les fonctions résiduelles E/F-rank
- [x] Status: Done — les trois sous-waves 9a/9b/9c sont mergées. Toutes
  les fonctions D/E-rank identifiées sont maintenant au rang ≤ A(3) en
  orchestrateur.
- Effort: 4j
- Impact: Simplicité, Maintenabilité, Lisibilité
- **Problème** — fonctions encore au plafond Xenon (depuis le split
  cli/handlers le file est maintenant `cli/handlers/validate_sql.py`):
  - `cli/handlers/validate_sql.py::_handle_validate_sql` (E=32) ← 9a
  - `core/sql_generator/diff_sql_generator.py::generate_from_diff` (D=26) ← 9b
  - `core/sql_generator/diff_sql_generator.py::_generate_table_property_changes` (D=29) ← 9c
- **Action** — appliquer le pattern PR-H14/H15 (orchestrateur A=2 +
  helpers privés A/B). Un mini-PR par fonction.
- **Critères d'acceptation par sous-wave** — la fonction cible descend
  ≤ B (10) au rang Xenon ; aucun test ne casse ; tous les gates verts.
- **Sub-waves**
  - **9a — PR ouverte** : `_handle_validate_sql` E(32) → orchestrateur
    A(2) + 6 helpers privés A/B (`_resolve_dialect`,
    `_build_validation_config`, `_resolve_output_mode`,
    `_collect_files_to_validate` B9, `_expand_file_arg` A5,
    `_run_validation_and_emit` B8). Mergé (#351).
  - **9b — Mergé (#352)** : `generate_from_diff` D(26) → orchestrateur
    **A(3)** + 5 helpers privés tous A. Pattern : 4 phases (modified
    tables, missing tables, extra tables, typed object changes) +
    `_build_expected_maps` classmethod qui utilise `getattr` sur les
    15 attrs `expected_<key>` du context, évitant un dict literal à
    16 branches.
  - **9c — Mergé** : `_generate_table_property_changes` D(29) →
    orchestrateur **A(2)** + 3 phase helpers (`_emit_inheritance_changes`
    B8 avec sous-helper `_coerce_inherits_to_list` A3,
    `_emit_system_versioning_changes` B7, `_emit_recreation_required_warning`
    A4) + un `_alter_table_stmt` A1 partagé. Le cascade de 8 `if` qui
    décidait quelle propriété entrait dans le warning est remplacée
    par une table `_RECREATION_REQUIRED_PROPERTIES` (predicate → label)
    — data, A rank, point d'extension unique pour ajouter une nouvelle
    propriété non-altérable.

### 10. Runbooks de recovery dans `docs/operations/`
- [x] Status: Done — cinq runbooks livrés sous
  `docs/operations/recovery/`, wirés dans `mkdocs.yml` (nav section
  `Operations`) et cross-référencés depuis `ARCHITECTURE.md` § 6.1
  ("Operations and recovery").
- Effort: 3j (livré)
- Impact: Fiabilité, Documentation
- **Problème** — pas de doc opérationnelle pour : JVM mort en cours de
  migration, lock timeout (Oracle DBMS_LOCK), corruption `schema_history`,
  rollback partiel sur DDL non transactionnel (MySQL).
- **Livré**
  1. `docs/operations/recovery/index.md` + 5 runbooks :
     `jvm-crash.md`, `oracle-lock-timeout.md`,
     `schema-history-corruption.md`, `partial-ddl-mysql.md`,
     `network-split.md`.
  2. Chaque runbook suit la même structure
     (Symptoms → Immediate response → Recovery → Verification →
     Prevention).
  3. `mkdocs.yml` nav section ajoutée, lien depuis `ARCHITECTURE.md`
     § 6.1 (nouvelle sous-section ajoutée pour absorber le pointeur).
- **Critères d'acceptation atteints** — 5 runbooks (JVM crash, lock
  timeout, history corruption, partial DDL, network split) + un index
  qui documente les diagnostics safe-by-default (`dblift info` + SELECT
  direct sur `dblift_schema_history`) et les bornes d'usage de
  `dblift repair`.

### 11. Plugin API pour les classes de config
- [x] Status: Done — `PluginInfo.config_class` ajouté, chaîne de
  résolution étendue dans `_resolve_config_class` (1. registry legacy →
  2. plugin metadata → 3. parent fallback), tous les plugins
  first-party déclarent leur `config_class`, et
  `tests/unit/db/test_provider_registry_config_class.py` (10 cas)
  pin le contrat.
- Effort: 4j (livré dans la portée d'un seul PR — la migration des
  configs existantes vers `db/plugins/<X>/config.py` reste un
  nice-to-have future puisque les eager imports actuels sont chargés
  par ~25 tests).
- Impact: Évolutivité, Modularité
- **Problème résolu** — un dialecte tiers peut maintenant livrer sa
  propre `BaseDatabaseConfig` via `PluginInfo(config_class=MyConfig, ...)`
  sans toucher à `config/_subclasses/` ni au bloc d'imports eager au
  bas de `config/database_config.py`.
- **Livré**
  1. Champ `PluginInfo.config_class: Optional[Type[Any]]` (Any pour
     éviter l'import circulaire `db.provider_registry` ↔
     `config.database_config` — narrowing au site de consommation).
  2. `_resolve_config_class` consulte le plugin registry comme path 2
     entre la lookup du registry legacy et le fallback parent
     `config_dialect`. Garde-fou runtime : un `config_class` qui n'est
     pas un sous-type de `BaseDatabaseConfig` est rejeté silencieusement
     pour empêcher un plugin mal configuré d'inverser le contrat.
  3. Chaque plugin first-party (`postgresql`, `mysql`, `sqlserver`,
     `oracle`, `db2`, `sqlite`, `cosmosdb`) déclare son `config_class`
     dans son `plugin.py`. `mariadb` continue à utiliser
     `config_dialect="mysql"` (pas de classe propre).
  4. Test `tests/unit/db/test_provider_registry_config_class.py`
     (10 cas, dont un plugin tiers synthétique `_ThirdPartyConfig` /
     `_ThirdPartyProvider` qui ne touche jamais le registry legacy).
- **Critères d'acceptation atteints** — un dialecte tiers n'a plus
  besoin de modifier `config/` ; il déclare son entry point
  `dblift.providers` dans son propre `pyproject.toml` et ses classes
  config + provider + quirks dans son propre package. Les imports
  eager au bas de `config/database_config.py` restent pour la
  rétrocompatibilité (25+ tests `from config.database_config import
  SQLiteConfig`), mais ne sont plus le mécanisme canonique
  d'enregistrement pour les nouveaux dialectes.

### 12. Supprimer les ré-exports backward-compat dans `core/sql_generator/__init__.py`
- [x] Status: Done — PR 1 (DeprecationWarning, #358) + PR 2 (suppression
  définitive). Le produit n'étant pas encore utilisé en production, le
  cycle de dépréciation a été raccourci au prochain release 1.7.0
  plutôt qu'au bump majeur 2.0.
- Effort: 1j PR 1 + 0.3j PR 2 (livré).
- Impact: Modularité, Simplicité.
- **Problème** — `core/sql_generator/__init__.py:39-48` ré-exporte les
  generators depuis `db/plugins/*/generator/` pour compat ancienne API.
  Couplage soft inversé qui rendait `core/` dépendant de `db/` à
  l'import time.
- **Livré (PR 1)**
  1. Imports eager remplacés par un `__getattr__` au niveau du module
     qui émet un `DeprecationWarning` ciblé sur le chemin plugin
     canonique (`db.plugins.<X>.generator.{alter,ddl}_generator`) et
     résout la classe via `importlib.import_module` au premier accès.
  2. Tables `_DEPRECATED_DIALECT_GENERATORS` (10) et
     `_DEPRECATED_DIALECT_ALTER_GENERATORS` (5) exposées pour la
     discoverability et l'introspection des tests.
  3. Bloc `TYPE_CHECKING` qui garde mypy / IDE go-to-definition
     fonctionnels sans payer l'import eager.
  4. Test `tests/unit/core/sql_generator/test_init_deprecation.py`
     (8 cas) qui pin le contrat : exactly-one-warning-per-access,
     message format, identity-equality avec la classe canonique,
     attribute-error normal pour un nom inconnu, symboles eagerly
     exportés silencieux.
  5. **Aucun consommateur in-repo n'utilise les paths legacy** —
     l'audit `grep -rn "from core\.sql_generator import.*SqlGenerator"`
     ne retourne que le module __init__ lui-même. Les tests et code
     production importent déjà depuis `db.plugins.<X>.generator.*`.
- **Critère d'acceptation partiel** — `core/sql_generator/__init__.py`
  et `core/sql_generator/alter/__init__.py` n'ont plus d'imports
  runtime depuis `db/plugins/*`. Les autres sites encore présents
  (`core/migration/sql/sql_execution_service.py` pour
  `is_tsql_batch_separator`, `core/migration/executor/execution_engine.py`
  pour les helpers Oracle SQL*Plus) sont architecturalement distincts
  et hors scope de ce quick win 1j.
- **Livré (PR 2)**
  1. Suppression du dict `_DEPRECATED_DIALECT_GENERATORS` (10 entries),
     `_DEPRECATED_DIALECT_ALTER_GENERATORS` (5 entries), des hooks
     PEP 562 `__getattr__` / `__dir__`, et des blocs `TYPE_CHECKING`
     dans `core/sql_generator/__init__.py` et
     `core/sql_generator/alter/__init__.py`.
  2. Retrait des 10 (resp. 5) noms legacy de `__all__`.
  3. Suppression de `tests/unit/core/sql_generator/test_init_deprecation.py`
     et remplacement par `test_init_removal.py` (5 cas) qui pin la
     suppression : noms absents de `__all__`, accès attribut lève
     `AttributeError`, chemins canoniques `db.plugins.<X>.generator.*`
     toujours valides.
- **Breaking change** — consumers must now import from the plugin path
  directly. The deprecation cycle ran inside a single minor release
  (1.6.0 → 1.7.0) because the product is not yet in production use.

### 13. Comparator registry pluggable
- [x] Status: Done — registry extrait dans
  `core/comparison/_comparator_registry.py` avec discovery via
  `dblift.comparators` entry-point group ; les 15 first-party comparators
  conservés inchangés ; un PR tiers ajoute un comparator sans toucher
  `core/`.
- Effort: 3j (livré dans un seul PR).
- Impact: Évolutivité, Modularité.
- **Problème résolu** — le `_COMPARATOR_REGISTRY` ClassVar de
  `ObjectComparator` (qui contenait en fait 15 types, pas 11 comme
  l'estimation initiale) listait les classes en dur. Ajouter un
  comparator pour un type exotique (custom sequence, PL/SQL package
  étendu) exigeait éditer `core/comparison/comparator.py`.
- **Livré**
  1. Nouveau module `core/comparison/_comparator_registry.py` exposant
     `get_comparator_class(name)`, `get_registered_names()`, et
     `register_external_comparator(name, cls)` (helper test-only).
  2. Les 15 comparators first-party migrés dans
     `_FIRST_PARTY_COMPARATORS` au niveau module — l'`ObjectComparator`
     ne les importe plus directement, sa `__getattr__` consulte la
     fonction du registry.
  3. Discovery externe via `importlib.metadata.entry_points(group="dblift.comparators")`,
     idempotente (flag `_external_discovered`), résiliente aux erreurs
     `ep.load()` (logged au niveau WARNING, plugin individuel ignoré
     sans casser le reste).
  4. First-party gagne sur collision : un plugin qui déclare
     `table_comparator` est silencieusement shadow par la classe
     first-party — protège le contrat core de plugins malveillants ou
     mal configurés.
  5. Test `tests/unit/core/comparison/test_comparator_registry.py`
     (16 cas) : invariants first-party, wiring externe (entry point
     résolu, idempotent, load-failure resilient, non-class skipped,
     shadow protection), helper `register_external_comparator`
     (TypeError sur non-class, ValueError sur shadow first-party),
     bout-en-bout via `ObjectComparator.synthetic_comparator`.
- **Critère d'acceptation atteint** — un dialecte tiers peut livrer son
  propre comparator en déclarant
  `[project.entry-points."dblift.comparators"]\nmy_custom = "pkg:Cls"`
  dans son `pyproject.toml` sans modifier `core/comparison/`.

### 14. Remplacer `__getattr__` paresseux dans `comparator.py`
- [x] Status: Done — 16 `@cached_property` typés remplacent le dispatch
  paresseux pour tous les first-party comparators ; `__getattr__` survit
  uniquement pour les comparators tiers déclarés via le entry-point
  group `dblift.comparators` (action #13).
- Effort: 1j (livré).
- Impact: Modularité, Lisibilité.
- **Problème résolu** — la dispatch via `__getattr__` retournait `Any`,
  forçant 16 `# type: ignore[no-any-return]` sur les méthodes
  `ObjectComparator.compare_*` et bloquant autocomplete IDE / navigation
  mypy vers les API per-type des comparators.
- **Livré**
  1. 16 accesseurs `@cached_property` au niveau classe, chacun annoté
     avec la classe comparator concrète (`TableComparator`,
     `IndexComparator`, `ModuleComparator`, …). Mypy et IDE voient
     maintenant le vrai type de retour.
  2. Les 15 imports per-type comparator reviennent dans
     `core/comparison/comparator.py` (extraits dans le registry par
     l'action #13, mais nécessaires ici pour à la fois l'instanciation
     dans le body de la property et l'annotation de retour).
  3. `__getattr__` conservé mais ne gère plus que les comparators tiers
     (les first-party sont interceptés par les descriptors property
     avant que la lookup n'atteigne `__getattr__`).
  4. 16 `# type: ignore[no-any-return]` retirés des méthodes
     `compare_*` — mypy passe sans ignore.
  5. 5 tests dans
     `tests/unit/core/comparison/test_comparator_registry.py::TestFirstPartyTypedProperties`
     qui pin (a) chaque accesseur retourne sa classe concrete, (b) la
     caching per-instance est respecté, (c) `TableComparator` reçoit
     bien le kwarg `log`, (d) un override tiers au nom d'un first-party
     est shadow par la property typée, (e) chaque return annotation est
     une classe concrète (pas `Any`).
- **Critères d'acceptation atteints** — autocomplete IDE et go-to-definition
  fonctionnent sur les 16 comparators ; `mypy --strict` sur
  `core/comparison/comparator.py` passe sans `# type: ignore` (vs 16 avant).

### 15. Module docstrings pour tous les `db/plugins/<X>/`
- [x] Status: Done (PR 3 of 3) — `db/` ratchet driven to zero, gate strict
- Effort: 2j (avec linter de la P0 #4)
- Impact: Documentation, Lisibilité
- **Problème** — beaucoup de modules quirks/provider plugins sans docstring
  expliquant le scope dialect-specific.
- **Action** — un docstring par module décrivant : (1) quirks couverts,
  (2) limitations connues, (3) lien vers la matrice ADR-0007.
- **Critères d'acceptation** — `check_api_docstrings.py --paths db --ratchet
  .docstring-ratchet.json` reste vert ; cap descend à zéro à terme.
- **Avancement** — PR 1 (action #15 PR 1, 2026-05-15) : 24 docstrings ajoutés
  (2 modules : `oracle/parser/__init__.py`, `postgresql/parser/__init__.py` ;
  8 classes `*Quirks` : `Db2Quirks`, `MysqlQuirks`, `SqliteQuirks`,
  `SqlserverQuirks`, `OracleQuirks`, `CosmosdbQuirks`, `PostgresqlQuirks`,
  `MariadbQuirks` ; 8 `__init__` one-liners ; 2 fonctions standalone :
  `MysqlQuirks.preserves_object_definition`, `cosmosdb.query_executor.replace_param`).
  Ratchet établi à `db: 119`.
- **PR 2** (action #15 PR 2, 2026-05-15) : 34 docstrings additionnels —
  modules `db/jvm_manager.py` + `db/data_access.py` ; module + classe
  `DummyProvider` + 13 méthodes sur `db/dummy_jdbc_provider.py` ; 2
  fonctions `db/error.py` ; 3 méthodes `db/introspection/extractors/`
  (misc/procedure/view) ; 1 méthode `db/base_quirks.py` ; 11 méthodes
  quirks sur `db/plugins/db2/quirks.py` (premier dialecte entièrement
  nettoyé). Ratchet descendu à `db: 85`.
- **PR 3** (action #15 PR 3, 2026-05-15) : 85 docstrings ajoutés sur les
  6 dialectes restants, faisant descendre le cap à `db: 0`. Couvre tous
  les overrides `*Quirks` des méthodes abstraites/défaut de `BaseQuirks` :
  `sqlserver/quirks.py` (16 méthodes), `postgresql/quirks.py` (16),
  `oracle/quirks.py` (16), `mysql/quirks.py` (16), `cosmosdb/quirks.py`
  (15), `sqlite/quirks.py` (6). Chaque docstring (1-3 lignes) explique
  le comportement dialect-specific (ex. `render_identity_clause` de PG
  retourne `None` pour les types SERIAL car l'auto-increment vit dans
  le nom du type ; `parser_class` d'Oracle route le regex vers
  `OracleParser` car sqlglot n'a pas de dialecte Oracle suffisant)
  plutôt que de répéter le contrat de la base. Style aligné sur
  `db/plugins/db2/quirks.py` (nettoyé en PR 2). Aucune annotation
  `# lint: allow-missing-docstring` n'a été utilisée. **Le gate est
  désormais strict pour `db/`** sur le même pied qu'`api/` et `cli/` :
  toute PR future qui introduit une violation public-surface
  manquante de docstring dans `db/` fait échouer la CI.

---

## P2 — Polish & qualité tests (cycle +2)

### 16. Réduire la mock-heaviness sur top 10 fichiers de tests
- [ ] Status: Todo
- Effort: 8j
- Impact: Tests, Fiabilité
- **Problème** — 6 879 imports de mocks. Les plus gros (`test_client_extended.py`,
  `test_cli.py`) mockent `Provider`, `Executor`, et toute la chaîne — testent
  les appels, pas le comportement.
- **Action**
  1. Identifier 10 fichiers les plus mock-heavy via grep.
  2. Pour chacun, ajouter une variante real-execution avec SQLite (provider
     léger, pas de JVM).
  3. Garder les mocks pour les cas réellement impossibles (Oracle DBMS_LOCK).
- **Critères d'acceptation** — ratio mocks/asserts divisé par 2 sur les
  fichiers traités ; vrais bugs attrapés par la nouvelle variante.

### 17. Découper les classes de test monolithiques
- [ ] Status: Todo
- Effort: 5j
- Impact: Tests, Maintenabilité
- **Problème** — `test_main_cli_direct.py` 1.8k lignes, `test_jdbc_provider_coverage.py`
  2k lignes, `test_v110_regressions.py` 703 lignes.
- **Action** — split par feature/command testé, avec une `conftest.py`
  locale pour les fixtures partagées. Cible : aucun fichier de test > 500 LOC.
- **Critères d'acceptation** — `find tests/ -name "test_*.py" -exec wc -l {} +`
  retourne max ≤ 500.

### 18. Tests dédiés pour `execution_engine.py`
- [ ] Status: Todo
- Effort: 3j
- Impact: Tests, Fiabilité
- **Problème** — pas de fichier de test dédié pour le coeur de l'exécution
  des migrations.
- **Action** — créer `tests/unit/core/migration/executor/test_execution_engine.py`
  couvrant : autocommit policy, transaction rollback, callbacks, partial
  failure, statement-by-statement vs batch.
- **Critères d'acceptation** — > 85 % de couverture ligne sur
  `execution_engine.py`.

### 19. Mécanisme de quarantaine pour tests flaky
- [ ] Status: Todo
- Effort: 1j
- Impact: Tests, Fiabilité
- **Problème** — pas de `pytest.mark.flaky` ni de quarantine. Un test
  intermittent bloque les PRs ou pollue les rétro-actions Bugbot.
- **Action**
  1. Ajouter `pytest-rerunfailures` aux dev deps.
  2. Définir un marker `@pytest.mark.flaky(reruns=2, reruns_delay=1)`
     dans `pytest.ini`.
  3. Documenter la politique : flaky markers temporaires (max 30j) avec
     issue de tracking liée.

### 20. Étendre les benchmarks aux chemins chauds
- [ ] Status: Todo
- Effort: 3j
- Impact: Tests, Fiabilité
- **Problème** — 1 seul benchmark (`test_bench_cpu_hot_paths.py`),
  workflow `benchmarks.yml` en `workflow_dispatch` uniquement.
- **Action**
  1. Ajouter benchmarks pour : SQL generator (diff_sql_generator),
     comparator (schema_comparator), parser (sqlglot_parser).
  2. Stocker baseline JSON par dialecte.
  3. Activer le workflow sur push develop ; échouer si regression > 30 %.

### 21. Essai de tests de mutation (mutmut)
- [ ] Status: Todo
- Effort: 4j
- Impact: Tests
- **Problème** — pas de mutation testing ; la couverture ligne peut être
  trompeuse.
- **Action**
  1. Pilote sur `api/` (déjà bien testé, scope contenu).
  2. Si > 80 % survival → travailler sur les killed mutants.
  3. Documenter le verdict — décider d'étendre ou pas à `core/migration/`.

### 22. Consolider la doc des providers
- [ ] Status: Todo
- Effort: 1j
- Impact: Documentation
- **Problème** — `docs/architecture/database-providers.md` et
  `docs/development/adding-database-support.md` se chevauchent.
- **Action** — auditer, fusionner en un seul document avec sections claires
  "Comprendre" (architecture) et "Étendre" (how-to).

### 23. Exemple Python complet avec walkthrough
- [ ] Status: Todo
- Effort: 1.5j
- Impact: Documentation
- **Problème** — `example/` ne montre que du SQL. Pas d'exemple
  `DBLiftClient` from scratch.
- **Action** — créer `example/python_quickstart/` avec :
  - `quickstart.py` (40 lignes, depuis config jusqu'à `client.migrate()`).
  - `README.md` commenté étape par étape.
  - Test E2E qui exécute le quickstart sur SQLite.

### 24. Éliminer les `# lint: allow-dialect-string` résiduels
- [ ] Status: Todo
- Effort: 3j
- Impact: Évolutivité
- **Problème** — ~25 occurrences subsistent dans
  `core/sql_generator/script_organizer.py` et
  `core/sql_generator/basic_table_ddl_generator.py`.
- **Action** — pour chacune, introduire un hook quirks (`order_drop_priority()`,
  `render_computed_column()` déjà partiellement fait) et déplacer la logique
  dans les plugins.
- **Critères d'acceptation** — `grep -r "allow-dialect-string" .` retourne
  zéro résultat dans `core/`.

---

## P3 — Backlog long terme (> 1 mois ou faible ROI immédiat)

### 25. Mypy strict global (`disallow_untyped_defs = true`)
- [ ] Status: Todo
- Effort: 10j+
- Impact: Maintenabilité, Documentation, Fiabilité
- **Action** — extension finale après que toutes les vagues H* aient été
  livrées. Passer la config globale (et non plus par overrides) en strict.

### 26. Réduire les couches d'indirection CLI → executor à ≤ 3 hops
- [ ] Status: Todo
- Effort: 5j
- Impact: Simplicité
- **Problème** — actuellement `cli/main → _command_handlers → api/client →
  _client_factory → core/executor + db/registry` = 4-5 hops.
- **Action** — mesurer via un script `scripts/call_graph_depth.py`, puis
  fusionner `_client_factory` dans `client` (ou inverse) si bénéfice clair.

### 27. Phase 2 Xenon : `max-absolute = C`
- [ ] Status: Todo
- Effort: continu sur 2 cycles
- Impact: Maintenabilité, Simplicité
- **Action** — durcir le seuil `xenon` dans `complexity.yml` de F→D puis D→C.

### 28. ConfigBuilder : alternatives plus déclaratives
- [ ] Status: Todo
- Effort: 5j
- Impact: Simplicité
- **Action** — explorer la suppression de `ConfigBuilder` au profit de
  `DbliftConfig.from_dict()` + Pydantic-like validation.

### 29. Diagrammes d'architecture par flow
- [ ] Status: Todo
- Effort: 3j
- Impact: Documentation
- **Action** — un diagramme mermaid par opération (migrate, undo, repair,
  diff, snapshot, baseline) dans `docs/architecture/flows/`.

### 30. CI mutation testing sur modules changés
- [ ] Status: Todo
- Effort: 5j
- Impact: Tests
- **Action** — si #21 concluant, GitHub Actions qui lance mutmut uniquement
  sur les fichiers touchés par le PR.
