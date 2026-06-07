# Démarrage

Bienvenue dans DBLift ! Ce guide vous aidera à démarrer rapidement.

## Installation

### Étape 1 : Télécharger DBLift

Visitez la [page des releases](https://github.com/cmodiano/dblift/releases) et téléchargez la version pour votre système d'exploitation :

- **Windows** : `dblift-windows-x64.zip`
- **macOS (Intel)** : `dblift-macos-x64.tar.gz`
- **macOS (Apple Silicon)** : `dblift-macos-arm64.tar.gz`
- **Linux** : `dblift-linux-x64.tar.gz`

### Étape 2 : Extraire les Fichiers

- **Windows** : Clic droit sur le fichier téléchargé et sélectionnez "Extraire tout"
- **macOS/Linux** : Ouvrez le Terminal et exécutez :
  ```bash
  tar xzf dblift-*.tar.gz
  ```

### Étape 3 : Vérifier l'Installation

Ouvrez votre terminal ou invite de commande et exécutez :

```bash
# Sur Windows
C:\chemin\vers\dblift\dblift.bat --version

# Sur macOS/Linux
/path/to/dblift/dblift --version
```

Vous devriez voir le numéro de version de DBLift. Vous êtes prêt !

## Votre Première Migration {#votre-premiere-migration}

Créons votre premier changement de base de données en 4 étapes simples :

### Étape 1 : Créer un Dossier de Projet

Créez un dossier pour votre projet de base de données et naviguez-y :
```bash
mkdir mon-projet-base-de-donnees
cd mon-projet-base-de-donnees
```

### Étape 2 : Informer DBLift sur Votre Base de Données

Créez un fichier appelé `dblift.yaml` avec les détails de connexion à votre base de données :

```yaml
database:
  url: "postgresql+psycopg://localhost:5432/madb"
  schema: "public"
  username: "monutilisateur"
  password: "monmotdepasse"

migrations:
  directory: "./migrations"
```

!!! tip "Astuce"
    Remplacez les valeurs ci-dessus par vos détails de base de données réels. Bases de données supportées : PostgreSQL, SQL Server, Oracle, MySQL, DB2, SQLite, Azure Cosmos DB.

### Étape 3 : Créer Votre Premier Fichier de Migration

Créez un dossier appelé `migrations` et ajoutez votre premier fichier de migration :

```bash
mkdir migrations
```

Créez un fichier : `migrations/V1_0_0__create_users_table.sql`

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

!!! note "Nommage des Fichiers de Migration"
    Le `V1_0_0` est le numéro de version, et tout ce qui suit `__` (double underscore) est une description. Ce nommage aide DBLift à suivre quels changements ont été appliqués.

### Étape 4 : Appliquer Votre Migration

Exécutez cette commande :
```bash
dblift migrate
```

C'est tout ! DBLift créera la table `users` dans votre base de données et se souviendra que cette migration a été appliquée.

## Comprendre les Bases

### Qu'est-ce qu'une Migration ?

Les migrations sont des fichiers SQL qui décrivent les changements à apporter à votre base de données. Chaque fichier représente un changement (comme créer une table, ajouter une colonne ou insérer des données).

Pensez aux migrations comme à un livre de recettes pour votre base de données :
- Chaque recette (fichier de migration) décrit un changement
- Elles sont numérotées dans l'ordre
- DBLift garde une trace des recettes que vous avez déjà suivies
- Vous pouvez toujours voir ce qui a été fait et ce qui est en attente

### Comment Fonctionnent les Fichiers de Migration

Les fichiers de migration suivent un modèle de nommage qui indique des informations importantes à DBLift :

```
V1_0_0__create_users_table.sql
│││││││└─ Description (ce que fait ce changement)
│││││││
││││││└─ Séparateur double underscore
│││││└─ Numéro de version (1.0.0)
││││└─ Type de version (V = migration versionnée)
```

### Trois Types de Migrations

1. **Migrations Versionnées** (Commence par `V`)
   - Exécutées une fois, dans l'ordre
   - Exemple : `V1_0_0__create_users_table.sql`
   - Utilisation : Créer des tables, ajouter des colonnes, changements de schéma

2. **Migrations Répétables** (Commence par `R`)
   - Réexécutées chaque fois que le fichier change
   - Exemple : `R__create_dashboard_view.sql`
   - Utilisation : Vues, procédures stockées, fonctions

3. **Migrations d'Annulation** (Commence par `U`)
   - Annulent une migration versionnée spécifique
   - Exemple : `U1_0_0__drop_users_table.sql`
   - Utilisation : Annuler des changements si nécessaire

## Prochaines Étapes

Maintenant que vous avez créé votre première migration, consultez :

- **[Guide de Configuration](configuration.md)** - Apprenez toutes les options de configuration
- **[Référence des Commandes](commands.md)** - Découvrez toutes les commandes disponibles
- **[Meilleures Pratiques](best-practices.md)** - Conseils pour des migrations efficaces
