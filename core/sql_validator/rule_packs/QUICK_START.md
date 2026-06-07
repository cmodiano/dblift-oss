# Quick Start: Declarative Rule Configuration

## Create Your Rules Configuration File

Create a file named `.dblift_rules_config.yaml` (or any name you prefer):

```yaml
# .dblift_rules_config.yaml

# Include entire rule packs
rule_packs:
  - performance
  - security

# Add specific rules by name (from any pack)
rules:
  - fk_must_have_index
  - no_select_star

# Exclude specific rules (even if included via packs)
exclude_rules:
  - some_rule_to_disable

# Add your own custom rules
custom_rules:
  - name: my_custom_rule
    type: pattern
    prohibit: "DROP DATABASE"
    message: "DROP DATABASE not allowed"
    severity: error
```

## Use It

```python
from core.migration.validation.rule_packs import RuleSelector
from core.migration.validation.linting.rule_engine import RuleEngine

# Load rules from YAML config
selector = RuleSelector()
rules = selector.load_from_yaml(".dblift_rules_config.yaml")

# Use with RuleEngine
engine = RuleEngine("postgresql")
engine.load_rules_from_dict(rules)

# Validate SQL
violations = engine.check_sql("SELECT * FROM users")
```

## Common Patterns

### Pattern 1: Full Pack
```yaml
rule_packs:
  - performance
```

### Pattern 2: Multiple Packs
```yaml
rule_packs:
  - performance
  - security
  - naming
```

### Pattern 3: Pack + Specific Rules
```yaml
rule_packs:
  - performance

rules:
  - no_string_concatenation_in_sql  # From security pack
  - table_name_snake_case            # From naming pack
```

### Pattern 4: Exclude Rules
```yaml
rule_packs:
  - performance
  - security

exclude_rules:
  - no_select_star  # Disable this rule
```

### Pattern 5: Custom Rules Only
```yaml
custom_rules:
  - name: company_specific_rule
    type: pattern
    prohibit: "DROP TABLE"
    message: "Company policy: No DROP TABLE"
    severity: error
```

## Available Rule Packs

- `naming` - Naming conventions (24 rules)
- `best_practices` - SQL best practices (20 rules)
- `security` - Security rules (21 rules)
- `performance` - Performance optimization (27 rules)

## Find Rule Names

```python
from core.migration.validation.rule_packs import RuleSelector

selector = RuleSelector()

# List all packs
print(selector.list_available_packs())

# List rules in a pack
print(selector.list_rules_in_pack("performance"))

# Get rule info
print(selector.get_rule_info("fk_must_have_index"))
```

## See Also

- [DECLARATIVE_CONFIG.md](DECLARATIVE_CONFIG.md) - Detailed documentation
- [README.md](README.md) - Complete guide
- [USAGE_EXAMPLES.md](USAGE_EXAMPLES.md) - More examples
