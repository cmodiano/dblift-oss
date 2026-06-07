# Référence des Fournisseurs de Base de Données

Implémentations de fournisseurs de base de données pour chaque base de données supportée.

## Fournisseur de Base

::: db.base_provider
    options:
      show_root_heading: true
      show_source: true

## Architecture des Fournisseurs

Chaque fournisseur de base de données implémente une interface commune à travers 5 composants spécialisés :

1. **ConnectionManager** - Crée et configure les connexions de base de données
2. **QueryExecutor** - Exécute les instructions SQL
3. **SchemaOperations** - Opérations DDL de schéma
4. **LockingManager** - Mécanisme de verrouillage des migrations
5. **HistoryManager** - Suivi de l'historique des migrations

Voir l'[Architecture des Fournisseurs de Base de Données](../architecture/database-providers.md) pour des informations détaillées.

## Bases de Données Supportées

- **PostgreSQL** (`db.plugins.postgresql`) - Fournisseur natif SQLAlchemy
- **MySQL** (`db.plugins.mysql`) - Fournisseur natif SQLAlchemy
- **SQL Server** (`db.plugins.sqlserver`) - Fournisseur natif SQLAlchemy
- **Oracle** (`db.plugins.oracle`) - Fournisseur natif SQLAlchemy
- **DB2** (`db.plugins.db2`) - Fournisseur natif SQLAlchemy
- **SQLite** (`db.plugins.sqlite`) - Fournisseur Python natif
- **Cosmos DB** (`db.plugins.cosmosdb`) - Fournisseur Azure SDK

Voir la [documentation complète en anglais](../api-reference/db.md) pour plus de détails.
