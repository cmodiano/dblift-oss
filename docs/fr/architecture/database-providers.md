# Système de Fournisseurs de Base de Données

**Emplacement** : `db/plugins/`

Chaque base de données a un fournisseur qui implémente une interface commune à travers 5 composants spécialisés.

## Architecture des Fournisseurs

Chaque fournisseur implémente ces 5 composants :

1. **ConnectionManager** - Crée les connexions de base de données
2. **QueryExecutor** - Exécute les instructions SQL
3. **SchemaOperations** - Opérations DDL de schéma
4. **LockingManager** - Verrouillage des migrations
5. **HistoryManager** - Suivi de l'historique des migrations

## Bases de Données Supportées

| Base de données | Emplacement du Fournisseur | Type de Connexion |
|-----------------|---------------------------|-------------------|
| PostgreSQL | `db/plugins/postgresql/` | SQLAlchemy natif (`psycopg`) |
| MySQL | `db/plugins/mysql/` | SQLAlchemy natif (`PyMySQL`) |
| SQL Server | `db/plugins/sqlserver/` | SQLAlchemy natif (`pymssql`) |
| Oracle | `db/plugins/oracle/` | SQLAlchemy natif (`python-oracledb`) |
| DB2 | `db/plugins/db2/` | SQLAlchemy natif (`ibm_db_sa`) |
| SQLite | `db/plugins/sqlite/` | Python natif (`sqlite3`) |
| Cosmos DB | `db/plugins/cosmosdb/` | Azure SDK (avec traduction pseudo-SQL) |

Voir la [documentation complète en anglais](../architecture/database-providers.md) pour plus de détails.
