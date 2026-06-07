# Moteur de Migration

**Emplacement** : `core/migration/executor/`

Le moteur de migration orchestre toutes les opérations de changement de base de données.

## Composants Principaux

### MigrationExecutor

Orchestrateur central qui gère le cycle de vie des migrations.

**Emplacement** : `core/migration/executor/migration_executor.py`

**Responsabilités Clés** :
- Charger les scripts de migration
- Calculer l'état des migrations (en attente/appliquées)
- Exécuter les commandes via le fournisseur de base de données
- Enregistrer les résultats dans la table d'historique
- Gérer les snapshots de schéma

Voir la [documentation complète en anglais](../architecture/migration-engine.md) pour plus de détails.
