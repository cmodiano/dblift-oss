# Declarative Rule Configuration

DBLift supports declarative YAML configuration for selecting rules from rule packs. This allows you to combine rule packs, individual rules, and custom rules in a single configuration file.

## Configuration File Format

Create a YAML file (e.g., `.dblift_rules_config.yaml`) with the following structure:

```yaml
# Rule packs to include (loads all rules from these packs)
rule_packs:
  - performance
  - security
  - naming

# Individual rules to include (by name, from any pack)
rules:
  - fk_must_have_index
  - no_select_star
  - table_name_snake_case

# Rules to exclude (removes these rules even if included via packs)
exclude_rules:
  - some_rule_to_disable

# Custom rules to add (define your own rules)
custom_rules:
  - name: my_custom_rule
    type: pattern
    prohibit: "DROP DATABASE"
    message: "DROP DATABASE is not allowed"
    severity: error
```

## Usage Examples

### Example 1: Use Full Rule Packs

```yaml
rule_packs:
  - performance
  - security
```

This loads all rules from the `performance` and `security` packs.

### Example 2: Mix Packs and Individual Rules

```yaml
rule_packs:
  - performance

rules:
  - no_string_concatenation_in_sql  # From security pack
  - table_name_snake_case            # From naming pack
```

This loads all rules from `performance` pack, plus two specific rules from other packs.

### Example 3: Exclude Specific Rules

```yaml
rule_packs:
  - performance
  - security

exclude_rules:
  - no_select_star  # Disable this rule even though it's in performance pack
```

### Example 4: Add Custom Rules

```yaml
rule_packs:
  - performance

custom_rules:
  - name: no_drop_production
    type: pattern
    prohibit: "DROP TABLE"
    message: "DROP TABLE not allowed in production migrations"
    severity: error
    suggestion: "Use ALTER TABLE ... DROP COLUMN instead"

  - name: require_company_prefix
    type: naming
    target: table
    pattern: "^company_.*$"
    message: "Tables must start with 'company_' prefix"
    severity: warning
```

### Example 5: Minimal Configuration

```yaml
# Just use individual rules
rules:
  - fk_must_have_index
  - no_select_star
  - update_delete_must_have_where
```

## Loading the Configuration

### Method 1: Using RuleSelector

```python
from core.migration.validation.rule_packs import RuleSelector
from pathlib import Path

selector = RuleSelector()
rules = selector.load_from_yaml(Path(".dblift_rules_config.yaml"))

# Use with RuleEngine
from core.migration.validation.linting.rule_engine import RuleEngine

engine = RuleEngine("postgresql")
engine.load_rules_from_dict(rules)
```

### Method 2: Using Convenience Function

```python
from core.migration.validation.rule_packs import RuleSelector
from pathlib import Path
import yaml

# Load config and create rules
selector = RuleSelector()
with open(".dblift_rules_config.yaml") as f:
    config = yaml.safe_load(f)
rules = selector.select_rules(config)
```

### Method 3: In dblift.yaml

```yaml
# dblift.yaml
validation:
  enabled: true
  rules_config_file: ".dblift_rules_config.yaml"  # If supported
  # OR
  rules_file: ".dblift_rules.yaml"  # After generating from config
```

## Configuration Options

### `rule_packs` (List[str])

List of rule pack names to include. All rules from these packs will be loaded.

Available packs:
- `naming` - Naming conventions
- `best_practices` - SQL best practices
- `security` - Security-focused rules
- `performance` - Performance optimization rules

### `rules` (List[str])

List of individual rule names to include. Rules are searched across all available packs.

Example rule names:
- `fk_must_have_index`
- `no_select_star`
- `table_name_snake_case`
- `no_string_concatenation_in_sql`
- `update_delete_must_have_where`

### `exclude_rules` (List[str])

List of rule names to exclude. These rules will be removed even if they're included via `rule_packs`.

Useful for:
- Disabling specific rules from a pack
- Temporarily disabling rules during migration
- Customizing rule sets for different environments

### `custom_rules` (List[Dict])

List of custom rule definitions. Each rule follows the standard rule format:

```yaml
custom_rules:
  - name: rule_name          # Required: Unique rule identifier
    type: pattern            # Required: pattern, naming, presence, or relational
    prohibit: "SELECT *"     # Pattern-specific: Pattern to prohibit
    message: "Rule message"  # Required: Human-readable message
    severity: warning        # Optional: error, warning, or info (default: warning)
    target: table           # Optional: Target object type
    suggestion: "Fix it"     # Optional: Suggestion for fixing
```

## Rule Deduplication

Rules are automatically deduplicated by name. If the same rule appears in multiple packs or is specified multiple times, only one instance will be included.

## Order of Operations

1. Load all rules from `rule_packs`
2. Add individual rules from `rules`
3. Add custom rules from `custom_rules`
4. Remove rules listed in `exclude_rules`

## Finding Rule Names

To find available rule names:

```python
from core.migration.validation.rule_packs import RuleSelector

selector = RuleSelector()

# List all packs
packs = selector.list_available_packs()
print(packs)  # ['best_practices', 'naming', 'performance', 'security']

# List rules in a pack
rules = selector.list_rules_in_pack("performance")
print(rules)  # ['fk_must_have_index', 'no_select_star', ...]

# Get info about a specific rule
info = selector.get_rule_info("fk_must_have_index")
print(info)
```

## Real-World Examples

### Example: Production Rules

```yaml
# .dblift_rules_production.yaml
rule_packs:
  - performance
  - security
  - best_practices

exclude_rules:
  - no_select_star  # Allow SELECT * in views for production

custom_rules:
  - name: require_audit_columns
    type: presence
    target: table
    must_have_columns: ["created_at", "updated_at", "created_by"]
    message: "Production tables must have audit columns"
    severity: error
```

### Example: Development Rules

```yaml
# .dblift_rules_dev.yaml
rule_packs:
  - naming
  - best_practices

rules:
  - fk_must_have_index  # From performance pack

exclude_rules:
  - require_audit_columns  # Relaxed for dev
```

### Example: Team-Specific Rules

```yaml
# .dblift_rules_team.yaml
rule_packs:
  - performance

rules:
  - table_name_snake_case
  - column_name_snake_case

custom_rules:
  - name: require_team_prefix
    type: naming
    target: table
    pattern: "^(team1_|team2_).*$"
    message: "Tables must start with team prefix"
    severity: warning
```

## Best Practices

1. **Start with full packs**: Begin with complete rule packs, then customize
2. **Use exclude_rules**: Instead of copying rules, use exclude to remove unwanted ones
3. **Document custom rules**: Add comments explaining why custom rules exist
4. **Version control**: Keep rule configuration files in version control
5. **Environment-specific**: Create different configs for dev/staging/production
6. **Review regularly**: Periodically review and update rule selections

## Migration from Programmatic Selection

If you're currently using programmatic selection:

**Before:**
```python
rules = create_rules_from_selection([
    "performance",
    "security",
    "fk_must_have_index"
])
```

**After:**
```yaml
# .dblift_rules_config.yaml
rule_packs:
  - performance
  - security
rules:
  - fk_must_have_index
```

```python
selector = RuleSelector()
rules = selector.load_from_yaml(".dblift_rules_config.yaml")
```
