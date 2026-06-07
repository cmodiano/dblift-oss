# DBLift Rule Packs - Usage Examples

Quick reference guide for using DBLift rule packs.

## Quick Start

### Use Full Rule Pack

```python
from core.migration.validation.rule_packs import create_rules_from_selection

# Load entire performance pack
rules = create_rules_from_selection("performance")
```

### Combine Multiple Packs

```python
# Load performance + security packs
rules = create_rules_from_selection(["performance", "security"])

# Load all packs
rules = create_rules_from_selection(["naming", "best_practices", "security", "performance"])
```

### Select Individual Rules

```python
from core.migration.validation.rule_packs import RuleSelector

selector = RuleSelector()

# Select specific rules by name
rules = selector.select_rules([
    "fk_must_have_index",
    "no_select_star",
    "update_delete_must_have_where"
])
```

### Combine Packs + Individual Rules

```python
# Load performance pack + specific security rules
rules = create_rules_from_selection([
    "performance",
    "no_string_concatenation_in_sql",  # From security pack
    "no_dynamic_sql_without_validation"  # From security pack
])
```

## Integration Examples

### With SqlLinter

```python
from pathlib import Path
from core.migration.validation.linting.sql_linter import SqlLinter
from core.migration.validation.rule_packs import create_rules_from_selection
import yaml

# Create rules from selection
rules_dict = create_rules_from_selection(["performance", "security"])

# Save to temporary file or use directly
with open("temp_rules.yaml", "w") as f:
    yaml.dump(rules_dict, f)

# Use with SqlLinter
linter = SqlLinter(
    dialect="postgresql",
    custom_rules_path=Path("temp_rules.yaml")
)

result = linter.lint_file(Path("migration.sql"))
```

### With RuleEngine Directly

```python
from core.migration.validation.linting.rule_engine import RuleEngine
from core.migration.validation.rule_packs import create_rules_from_selection

# Create rules
rules_dict = create_rules_from_selection(["performance", "security"])

# Load into RuleEngine
engine = RuleEngine("postgresql")
engine.load_rules_from_dict(rules_dict)

# Check SQL
violations = engine.check_sql("SELECT * FROM users")
```

### In Configuration File

```yaml
# dblift.yaml
validation:
  enabled: true
  # Option 1: Use full pack
  rules_file: "core/migration/validation/rule_packs/performance.yaml"
  
  # Option 2: Create custom file that combines packs
  # rules_file: ".dblift_rules.yaml"
```

Then create `.dblift_rules.yaml`:

```yaml
# .dblift_rules.yaml
# Generated using: create_rules_from_selection(["performance", "security"])
rules:
  - name: fk_must_have_index
    type: relational
    # ... rule definition
```

## Common Use Cases

### Use Case 1: Performance-Focused Team

```python
rules = create_rules_from_selection([
    "performance",
    "best_practices"  # Includes FK indexing, etc.
])
```

### Use Case 2: Security-Critical Application

```python
rules = create_rules_from_selection([
    "security",
    "best_practices",
    "performance"  # Performance matters but security first
])
```

### Use Case 3: Naming Standards Enforcement

```python
rules = create_rules_from_selection([
    "naming",
    "best_practices"  # Includes structure requirements
])
```

### Use Case 4: Custom Selection

```python
selector = RuleSelector()

# Get all available rules
all_packs = selector.list_available_packs()
print(all_packs)  # ['best_practices', 'naming', 'performance', 'security']

# List rules in a pack
perf_rules = selector.list_rules_in_pack("performance")
print(perf_rules[:5])  # ['fk_must_have_index', 'no_select_star', ...]

# Select specific rules
rules = selector.select_rules([
    "fk_must_have_index",      # From performance
    "no_string_concatenation_in_sql",  # From security
    "table_name_snake_case"    # From naming
])
```

### Use Case 5: Add Custom Rules

```python
custom_rules = [
    {
        "name": "no_drop_production",
        "type": "pattern",
        "prohibit": "DROP TABLE",
        "message": "DROP TABLE not allowed in production migrations",
        "severity": "error"
    }
]

rules = create_rules_from_selection([
    "performance",
    "security",
    custom_rules  # Add custom rules
])
```

## Rule Pack Contents

### naming.yaml
- Table naming conventions
- Column naming conventions
- Index naming conventions
- Constraint naming conventions
- View/procedure/function naming

### best_practices.yaml
- Table structure requirements
- Column best practices
- Foreign key best practices
- Query quality rules
- Data type best practices

### security.yaml
- SQL injection prevention
- Sensitive data protection
- Access control
- Input validation
- Audit requirements

### performance.yaml
- Index requirements
- Query anti-patterns
- Function usage optimization
- Join optimization
- Large result set handling

## Tips

1. **Start broad, then narrow**: Begin with full packs, then customize
2. **Use severity levels**: Adjust severity based on your team's needs
3. **Document exceptions**: If you add exceptions, document why
4. **Review regularly**: Periodically review your rule selection
5. **Test incrementally**: Add rules gradually to avoid overwhelming your team
