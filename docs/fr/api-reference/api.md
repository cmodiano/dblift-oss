# Référence API

## DBLiftClient

La classe cliente principale pour l'accès programmatique à DBLift.

::: api.client.DBLiftClient
    options:
      show_root_heading: true
      show_source: true
      show_signature_annotations: true
      separate_signature: true

## Démarrage Rapide

```python
from api.client import DBLiftClient
from db.plugins.postgresql.provider import PostgreSqlJdbcProvider
from config import DbliftConfig

# Créer le fournisseur
config = DbliftConfig.from_file("dblift.yaml")
provider = PostgreSqlJdbcProvider(config)

# Créer le client
client = DBLiftClient(
    provider=provider,
    migrations_dir="./migrations"
)

# Exécuter les migrations
result = client.migrate()
if result.success:
    print(f"Appliqué {len(result.migrations_applied)} migrations")
```

## Méthodes Principales

### migrate()

Appliquer les migrations en attente à la base de données.

```python
result = client.migrate(
    target_version="1.5.0",  # Optionnel : migrer vers une version spécifique
    dry_run=False,            # Prévisualiser sans appliquer
    show_sql=False,           # Inclure le SQL des migrations dans les sorties/rapports
    tags="core,init",         # Filtrer par étiquettes
    recursive=True            # Rechercher dans les sous-dossiers
)
```

### undo()

Annuler des migrations appliquées.

```python
result = client.undo(
    target_version="1.0.0",  # Optionnel : annuler jusqu'à une version spécifique
    dry_run=True,             # Prévisualiser sans appliquer
    show_sql=True             # Inclure le SQL d'annulation correspondant
)
```

### info()

Obtenir des informations sur le statut des migrations.

```python
result = client.info()
print(f"Version actuelle : {result.current_schema_version}")
print(f"Migrations appliquées : {len(result.migrations_applied)}")
print(f"Toutes les migrations : {len(result.migrations)}")
```

Voir la [documentation complète en anglais](../api-reference/api.md) pour plus de détails.
