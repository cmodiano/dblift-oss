# DBLift Rule Packs

This directory contains predefined rule packs for SQL validation in DBLift. These rule packs help enforce best practices, security, performance, and naming conventions in your database migrations.

## Available Rule Packs

### 1. `naming.yaml`
**Naming Conventions** - Rules for consistent naming across database objects:
- Table naming (snake_case, no reserved words)
- Column naming (snake_case, ID columns, timestamps, booleans, FKs)
- Index naming (prefixes: idx_, ix_, pk_, uk_, fk_)
- Constraint naming (pk_, fk_, uk_, ck_, df_ prefixes)
- View, procedure, function, sequence, trigger naming

### 2. `best_practices.yaml`
**Best Practices** - Common SQL best practices:
- Table structure (primary keys, comments, audit columns)
- Column requirements (NOT NULL, defaults, data types)
- Foreign key best practices (indexes, cascade rules)
- Query quality (avoid SELECT *, require WHERE clauses)
- Data type best practices

### 3. `security.yaml`
**Security** - Security-focused validation rules:
- SQL injection prevention (string concatenation, dynamic SQL)
- Sensitive data protection (passwords, PII, encryption)
- Access control (GRANT statements, roles)
- Input validation (CHECK constraints, length limits)
- Audit and compliance requirements

### 4. `performance.yaml`
**Performance** - Performance optimization rules:
- Index requirements (FKs, frequently queried columns)
- Query anti-patterns (SELECT *, cartesian joins, correlated subqueries)
- Function usage in WHERE clauses
- Join optimization
- Large result set handling

## Built-in Profiles

DBLift also ships named profiles for CI usage:

- `core` - high-signal rules for security and destructive migration safety.
- `enterprise` - security, best practices, and performance rule packs.
- `strict` - naming, security, best practices, and performance rule packs.
- `technical-debt` - naming, best practices, and performance cleanup work.

Use profiles directly from the CLI:

```bash
dblift validate-sql migrations/ --profile enterprise --fail-on warning --format github-actions
```

Profiles select rules only. They do not change `--fail-on`, output format, or
the configured severity threshold.

## Enterprise Evidence Metadata

Rules can include metadata that appears in JSON finding details and HTML
evidence reports:

```yaml
rationale: "Why this rule matters."
remediation: "How to resolve the finding."
control_mapping:
  - "SOC2-CC7.2"
override_policy:
  requires:
    - owner
    - reason
    - ticket
    - expires_at
  max_days: 30
```

Use this metadata for high-signal enterprise rules where reviewers need to
understand the risk, the expected remediation, and the control evidence behind
the policy.

## Governed Exceptions

Rules may define exceptions, but production-grade exceptions should carry an
owner, a reason, a ticket, and an expiration date when the rule's
`override_policy.requires` asks for them:

```yaml
exceptions:
  - when: "DROP TABLE staging_import"
    owner: "data-platform"
    reason: "Ephemeral staging object"
    ticket: "DBA-123"
    expires_at: "2999-07-01"
```

Incomplete exceptions are reported as validation errors instead of silently
suppressing the policy.

## Usage

### Option 1: Declarative YAML Configuration (Recommended)

Create a YAML configuration file to declaratively select rules:

```yaml
# .dblift_rules_config.yaml
rule_packs:
  - performance
  - security

rules:
  - fk_must_have_index
  - no_select_star

exclude_rules:
  - some_rule_to_disable

custom_rules:
  - name: my_custom_rule
    type: pattern
    prohibit: "DROP DATABASE"
    message: "DROP DATABASE not allowed"
    severity: error
```

Load it:

```python
from core.migration.validation.rule_packs import RuleSelector

selector = RuleSelector()
rules = selector.load_from_yaml(".dblift_rules_config.yaml")
```

See [DECLARATIVE_CONFIG.md](DECLARATIVE_CONFIG.md) for detailed documentation.

### Option 2: Use a Full Rule Pack

Load an entire rule pack:

```yaml
# dblift.yaml
validation:
  enabled: true
  rules_file: "core/migration/validation/rule_packs/performance.yaml"
```

### Option 3: Use Rule Selector Programmatically

Select specific rule packs and/or individual rules:

```python
from core.migration.validation.rule_packs import create_rules_from_selection

# Load full pack
rules = create_rules_from_selection("performance")

# Load multiple packs
rules = create_rules_from_selection(["performance", "security"])

# Load pack + individual rules
rules = create_rules_from_selection([
    "performance",
    "security",
    "fk_must_have_index",  # Individual rule name
    "no_select_star"
])

# Custom rule + packs
rules = create_rules_from_selection([
    "performance",
    {
        "name": "custom_rule",
        "type": "pattern",
        "prohibit": "DROP DATABASE",
        "message": "Custom rule message",
        "severity": "error"
    }
])
```

### Option 3: Combine in YAML Configuration

Create a custom rules file that combines packs:

```yaml
# .dblift_rules.yaml
# Import rules from packs programmatically or copy rules manually
rules:
  # Rules from performance pack
  - name: fk_must_have_index
    type: relational
    target: foreign_key
    requires_index: true
    message: "Foreign keys must have indexes for join performance"
    severity: error

  # Rules from security pack
  - name: no_string_concatenation_in_sql
    type: pattern
    prohibit: "(?i)(\\+|CONCAT|\\|\\|).*SELECT"
    message: "String concatenation can lead to SQL injection"
    severity: error

  # Custom rules
  - name: my_custom_rule
    type: pattern
    # ... your custom rule
```

## Rule Selection Examples

### Example 1: Performance + Security

```python
from core.migration.validation.rule_packs import RuleSelector

selector = RuleSelector()
rules = selector.select_rules(["performance", "security"])
```

### Example 2: Specific Rules Only

```python
selector = RuleSelector()
rules = selector.select_rules([
    "fk_must_have_index",
    "no_select_star",
    "update_delete_must_have_where"
])
```

### Example 3: Pack + Exceptions

```python
selector = RuleSelector()
rules = selector.select_rules([
    "performance",
    "security"
])
# Then modify rules to disable specific ones
rules["rules"] = [
    r for r in rules["rules"]
    if r.get("name") not in ["some_rule_to_disable"]
]
```

## Listing Available Rules

```python
from core.migration.validation.rule_packs import RuleSelector

selector = RuleSelector()

# List all available packs
packs = selector.list_available_packs()
print(packs)  # ['best_practices', 'naming', 'performance', 'security']

# List rules in a pack
rules = selector.list_rules_in_pack("performance")
print(rules)  # ['fk_must_have_index', 'no_select_star', ...]

# Get info about a specific rule
info = selector.get_rule_info("fk_must_have_index")
print(info)  # {'name': 'fk_must_have_index', 'type': 'relational', ...}
```

## Rule Types

Rules support four types:

1. **naming**: Validate identifier naming conventions (regex-based)
2. **pattern**: Detect SQL patterns and anti-patterns (regex-based)
3. **presence**: Check for required elements (requires SQL Model parsing)
4. **relational**: Validate relationships between objects (requires SQL Model parsing)

## Rule Severity Levels

- **error**: Must be fixed (blocks migration)
- **warning**: Should be addressed (doesn't block)
- **info**: Nice to fix (informational)

## Exceptions

Rules can include exceptions to skip validation in specific cases:

```yaml
- name: require_primary_key
  type: presence
  target: table
  must_have_primary_key: true
  exceptions:
    - table_matches: ".*_log.*"      # Skip for log tables
    - table_matches: ".*_temp.*"      # Skip for temp tables
```

Supported exception types:
- `table_matches`: Regex pattern for table names
- `when`: SQL pattern to match (e.g., "COUNT(*)")
- `in_views`: Skip when SQL is in a view
- `in_temp_tables`: Skip when SQL is in a temp table

## Creating Custom Rules

You can create custom rules by adding them to your selection:

```python
custom_rules = [
    {
        "name": "my_custom_rule",
        "type": "pattern",
        "prohibit": "DROP TABLE",
        "message": "Custom message",
        "severity": "error"
    }
]

rules = create_rules_from_selection(["performance", custom_rules])
```

Or create a custom YAML file:

```yaml
# custom_rules.yaml
rules:
  - name: my_custom_rule
    type: pattern
    prohibit: "DROP TABLE"
    message: "Custom message"
    severity: error
```

Then load it:

```python
from core.migration.validation.linting.rule_engine import RuleEngine

engine = RuleEngine("postgresql")
engine.load_rules_from_file(Path("custom_rules.yaml"))
```

## Best Practices

1. **Start with full packs**: Begin with complete rule packs to get comprehensive coverage
2. **Customize gradually**: Add or remove individual rules as needed
3. **Use appropriate severity**: Set severity based on your team's standards
4. **Document exceptions**: Document why exceptions are needed
5. **Review regularly**: Periodically review and update your rule selection
