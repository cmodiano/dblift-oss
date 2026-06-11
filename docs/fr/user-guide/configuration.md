# Guide de Configuration

Ce guide couvre toutes les options de configuration disponibles dans DBLift.

## Configuration de Base

Créez un fichier `dblift.yaml` à la racine de votre projet :

```yaml
database:
  url: "postgresql+psycopg://localhost:5432/madb"
  schema: "public"
  username: "monutilisateur"
  password: "monmotdepasse"

migrations:
  directory: "./migrations"  # Dossier unique (format legacy)
  recursive: true  # Rechercher dans les sous-dossiers (par défaut: true)

```

> **Le champ `schema` est obligatoire** pour tous les dialectes sauf SQLite (qui utilise toujours `main`). Il n'y a pas de valeur par défaut implicite — vous devez le définir soit dans `dblift.yaml`, soit en ligne de commande via `--db-schema`. DBLift crée les tables de métadonnées gérées dans ce schéma, donc une valeur absente ou incorrecte provoque des incohérences silencieuses entre schémas.

## Plusieurs Dossiers de Migrations

Vous pouvez spécifier plusieurs dossiers de migrations. Le premier est le dossier principal :

```yaml
migrations:
  directories:
    - ./migrations/core      # Dossier principal
    - ./migrations/features  # Dossier supplémentaire
  recursive: true  # Par défaut global pour tous les dossiers
```

## Paramètres Récursifs par Dossier

Contrôlez la recherche récursive par dossier. Utile lorsque certains dossiers ont des sous-dossiers et d'autres non :

```yaml
migrations:
  directories:
    - path: ./migrations/core
      recursive: true    # Rechercher dans les sous-dossiers récursivement
    - path: ./migrations/features
      recursive: false   # Seulement les fichiers de premier niveau
    - ./migrations/performance  # Utilise le paramètre récursif global (true)
  recursive: true  # Par défaut global pour les dossiers sans paramètre explicite
```

## Bases de Données Supportées

DBLift fonctionne avec ces bases de données :

| Base de données | Exemple d'URL de connexion | Extra driver |
|-----------------|---------------------------|--------------|
| PostgreSQL | `postgresql+psycopg://localhost:5432/madb` | `dblift[postgresql]` |
| SQL Server | `mssql+pymssql://localhost:1433/madb` | `dblift[sqlserver]` |
| Oracle | `oracle+oracledb://localhost:1521?sid=SID` | `dblift[oracle]` |
| MySQL | `mysql+pymysql://localhost:3306/madb` | `dblift[mysql]` |
| MariaDB | `mysql+pymysql://localhost:3306/madb` | `dblift[mariadb]` |
| DB2 | `ibm_db_sa://localhost:50000/madb` | `dblift[db2]` |
| SQLite | `/path/to/database.db` ou `:memory:` (voir [Configuration SQLite](#configuration-sqlite)) |
| Azure Cosmos DB | `https://account.documents.azure.com:443/` (voir [Configuration CosmosDB](#configuration-cosmosdb)) |

## Configuration SQLite

SQLite utilise un format de configuration plus simple car c'est une base de données basée sur fichiers :

```yaml
database:
  type: "sqlite"
  path: "/path/to/database.db"  # Ou utilisez ":memory:" pour une base en mémoire
  schema: "main"                 # Schéma par défaut de SQLite
```

### Base de Données en Mémoire (pour les tests)

```yaml
database:
  type: "sqlite"
  path: ":memory:"
  schema: "main"
```

### Utilisation de Variables d'Environnement

```bash
export DBLIFT_DB_TYPE="sqlite"
export DBLIFT_DB_PATH="/path/to/database.db"
```

### Notes Spécifiques à SQLite

- SQLite utilise le module natif Python `sqlite3`
- Pas de nom d'utilisateur/mot de passe nécessaire (SQLite n'a pas d'authentification)
- Le schéma est toujours "main" (SQLite ne supporte pas plusieurs schémas)
- Le chemin du fichier peut être absolu ou relatif au répertoire de travail
- Utilisez `:memory:` pour une base de données en mémoire (utile pour les tests)

## Configuration CosmosDB

Azure Cosmos DB utilise un format de configuration différent via le SDK Azure :

```yaml
database:
  type: "cosmosdb"
  account_endpoint: "https://your-account.documents.azure.com:443/"
  account_key: "your-account-key"  # Ou utilisez l'identité managée
  database_name: "your-database"
  # Optionnel : utiliser l'identité managée au lieu de account_key
  # use_managed_identity: true
```

### Pour le Développement Local (Émulateur CosmosDB)

```yaml
database:
  type: "cosmosdb"
  account_endpoint: "https://localhost:8081/"
  account_key: "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
  database_name: "your-database"
```

## Utilisation de Variables d'Environnement

Au lieu de mettre les mots de passe dans `dblift.yaml`, utilisez des variables d'environnement :

```bash
export DBLIFT_DB_URL="postgresql+psycopg://localhost:5432/madb"
export DBLIFT_DB_USERNAME="monutilisateur"
export DBLIFT_DB_PASSWORD="monmotdepasse"
```

!!! warning "Meilleure Pratique de Sécurité"
    Ne commitez jamais les mots de passe ou les identifiants sensibles dans le contrôle de version. Utilisez toujours des variables d'environnement pour les déploiements en production.

## Encodage de Fichier

Si vous utilisez des caractères spéciaux (é, ñ, ö, etc.) dans vos fichiers SQL, spécifiez l'encodage :

```yaml
migrations:
  script_encoding: "utf-8"
```

Par défaut, `script_encoding` est strict. Si un fichier de migration n'est pas valide pour cet encodage, DBLift signale une erreur d'encodage au lieu de remplacer silencieusement les caractères.

Pour laisser DBLift détecter l'encodage du script de migration avant la lecture, activez `detect_encoding` :

```yaml
migrations:
  script_encoding: "utf-8"
  detect_encoding: true
```

Quand la détection est activée, DBLift utilise l'encodage détecté pour ce fichier. Si la détection ou le décodage échoue, la migration échoue avec une erreur d'encodage claire.

## Prochaines Étapes

- Apprenez les **[Commandes](commands.md)** pour utiliser DBLift efficacement
- Consultez les **[Meilleures Pratiques](best-practices.md)** pour des conseils de configuration
- Voir **[Dépannage](troubleshooting.md)** si vous rencontrez des problèmes
