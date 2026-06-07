# Référence des Modules Core

Modules core pour l'exécution de migrations, l'analyse SQL et la gestion de schémas.

## Moteur de Migration

Le moteur de migration orchestre toutes les opérations de migration de base de données.

::: core.migration.executor.migration_executor.MigrationExecutor
    options:
      show_root_heading: true
      show_source: true
      show_signature_annotations: true

**Responsabilités Clés** :
- Exécuter les migrations dans l'ordre
- Gérer le cycle de vie des transactions
- Suivre l'état des migrations
- Gérer les erreurs et les rollbacks

Voir la [documentation complète en anglais](../api-reference/core.md) pour plus de détails sur tous les modules.
