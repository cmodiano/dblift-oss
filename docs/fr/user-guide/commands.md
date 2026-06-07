# Référence des Commandes

Ce guide couvre toutes les commandes DBLift et leur utilisation.

## Tâches Courantes

### Appliquer les Changements à Votre Base de Données {#appliquer-les-changements-a-votre-base-de-donnees}

**Voir ce qui doit être appliqué :**
```bash
dblift info
```
Cela vous montre quelles migrations sont en attente (pas encore appliquées) et lesquelles sont déjà faites.

**Appliquer les migrations en attente :**
```bash
dblift migrate
```
Cela exécutera toutes les migrations qui n'ont pas encore été appliquées, dans l'ordre.

**Prévisualiser les changements avant de les appliquer :**
```bash
dblift migrate --dry-run
```
Cela montre ce qui se passerait sans faire de changements réels.

**Prévisualiser les SQL avant de les appliquer :**
```bash
dblift migrate --dry-run --show-sql
```
Cela affiche les migrations en attente et les instructions SQL sans modifier la base.

### Vérifier le Statut des Migrations

**Voir toutes les migrations :**
```bash
dblift info
```

Vous verrez un résumé et un tableau standardisé avec les colonnes **Undoable** qui indique s'il existe une migration d'annulation correspondante prête à annuler le changement.

!!! tip "Astuce"
    Chaque commande CLI se termine maintenant par une bannière de complétion comme ci-dessus, incluant le temps d'exécution total. Cela rend les logs d'automatisation beaucoup plus faciles à scanner.

### Annuler les Changements

Si vous devez annuler une migration :

**Étape 1 : Créer une migration d'annulation**

Pour chaque migration versionnée `V1_0_1__add_email_column.sql`, créez un fichier d'annulation correspondant `U1_0_1__remove_email_column.sql` :

```sql
-- U1_0_1__remove_email_column.sql
ALTER TABLE users DROP COLUMN email;
```

**Étape 2 : Exécuter le rollback**
```bash
dblift undo --target-version=1.0.0
```

Cela annulera toutes les migrations après la version 1.0.0.

## Commandes Quotidiennes

Voici les commandes que vous utiliserez le plus souvent :

| Commande | Ce qu'elle fait | Quand l'utiliser |
|----------|-----------------|------------------|
| `dblift info` | Affiche le statut de toutes les migrations | Vérifier ce qui est appliqué et ce qui est en attente |
| `dblift migrate` | Applique les migrations en attente | Déployer les changements de base de données |
| `dblift migrate --dry-run` | Prévisualise sans appliquer | Vérifier ce qui va se passer avant de le faire |
| `dblift migrate --dry-run --show-sql` | Prévisualise les migrations et le SQL sans appliquer | Relire le SQL exact avant exécution |
| `dblift undo --dry-run --show-sql` | Prévisualise les scripts d'annulation et le SQL sans appliquer | Relire le SQL de rollback avant exécution |
| `dblift undo --target-version=X` | Revient à une version spécifique | Annuler des changements récents |
| `dblift validate` | Vérifie les migrations pour les erreurs | Avant d'appliquer les changements |
| `dblift baseline --baseline-version=X` | Marque les migrations comme déjà appliquées | Travailler avec des bases de données existantes |

**Exemples Rapides :**

```bash
# Le workflow habituel
dblift info                    # Voir ce qui est en attente
dblift validate               # Vérifier les erreurs
dblift migrate                # Appliquer les changements

# Annulation
dblift undo --target-version=1.0.0

# Travailler avec des bases de données existantes
dblift baseline --baseline-version=2.0.0
```

## Prochaines Étapes

- Apprenez les **[Meilleures Pratiques](best-practices.md)** pour des migrations efficaces
- Consultez **[Dépannage](troubleshooting.md)** si vous rencontrez des problèmes
- Voir la **[Référence API](../api-reference/cli.md)** pour la documentation complète des commandes
