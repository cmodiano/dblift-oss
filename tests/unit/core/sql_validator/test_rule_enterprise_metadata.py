"""Enterprise metadata propagation for SQL validation rules."""

from pathlib import Path

import pytest

from core.sql_validator.linting.rule_engine import RuleEngine

pytestmark = [pytest.mark.unit]


def test_pattern_rule_metadata_is_copied_to_violation():
    engine = RuleEngine("postgresql")
    engine.load_rules_from_dict(
        {
            "rules": [
                {
                    "name": "no_drop_table_without_ticket",
                    "type": "pattern",
                    "regex": "(?i)DROP\\s+TABLE",
                    "message": "DROP TABLE requires approved change evidence",
                    "severity": "error",
                    "rationale": "Dropping tables can permanently remove data.",
                    "remediation": "Attach an approved change ticket or use an archival migration.",
                    "control_mapping": ["SOX-CC7.2", "ISO27001-A.12.1.2"],
                    "override_policy": {
                        "requires": ["owner", "reason", "ticket", "expires_at"],
                        "max_days": 30,
                    },
                }
            ]
        }
    )

    violations = engine.check_sql("DROP TABLE customers;", Path("V9__drop_customers.sql"))

    assert len(violations) == 1
    violation = violations[0]
    assert violation.rule_id == "no_drop_table_without_ticket"
    assert violation.rationale == "Dropping tables can permanently remove data."
    assert violation.remediation == "Attach an approved change ticket or use an archival migration."
    assert violation.control_mapping == ["SOX-CC7.2", "ISO27001-A.12.1.2"]
    assert violation.override_policy == {
        "requires": ["owner", "reason", "ticket", "expires_at"],
        "max_days": 30,
    }
