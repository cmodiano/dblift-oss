"""Configuration for SQL validation and linting."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ValidationConfig:
    """Configuration for SQL validation (business rules and performance analysis)."""

    # Enable/disable validation
    enabled: bool = True

    # Business rules configuration
    rules_file: Optional[str] = None  # Path to YAML rules file
    rule_profile: Optional[str] = None  # Built-in profile name
    rules: List[str] = field(default_factory=list)  # Rule pack names and individual rule names
    fail_on: str = "error"  # Minimum finding severity that fails validation
    severity_threshold: str = "warning"  # Minimum severity to report: error, warning, info

    # Performance analysis configuration
    performance_enabled: bool = True  # Enable performance analysis
    performance_rules: Dict[str, str] = field(
        default_factory=lambda: {
            "cartesian_product": "error",
            "missing_where_clause": "warning",
            "select_star": "warning",
            "correlated_subquery": "info",
        }
    )

    # File filtering
    exclude_patterns: List[str] = field(default_factory=list)  # Patterns to exclude from validation

    # Output configuration
    output_format: str = "console"  # console, json, sarif, github-actions, gitlab, compact, html

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        if self.rules_file and (self.rule_profile or self.rules):
            raise ValueError("--rules-file cannot be combined with --profile or --rules")

        valid_severities = ["error", "warning", "info"]
        if self.severity_threshold not in valid_severities:
            raise ValueError(
                f"Invalid severity_threshold: {self.severity_threshold}. "
                f"Must be one of: {', '.join(valid_severities)}"
            )

        valid_formats = ["console", "json", "sarif", "github-actions", "gitlab", "compact", "html"]
        if self.output_format not in valid_formats:
            raise ValueError(
                f"Invalid output_format: {self.output_format}. "
                f"Must be one of: {', '.join(valid_formats)}"
            )
        valid_fail_on = ["never", "error", "warning", "info"]
        if self.fail_on not in valid_fail_on:
            raise ValueError(
                f"Invalid fail_on: {self.fail_on}. " f"Must be one of: {', '.join(valid_fail_on)}"
            )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ValidationConfig":
        """
        Create ValidationConfig from dictionary.

        Args:
            data: Configuration dictionary

        Returns:
            ValidationConfig instance
        """
        return cls(
            enabled=data.get("enabled", True),
            rules_file=data.get("rules_file"),
            rule_profile=data.get("rule_profile"),
            rules=list(data.get("rules", [])),
            fail_on=data.get("fail_on", "error"),
            severity_threshold=data.get("severity_threshold", "warning"),
            performance_enabled=data.get("performance_enabled", True),
            performance_rules=data.get(
                "performance_rules",
                {
                    "cartesian_product": "error",
                    "missing_where_clause": "warning",
                    "select_star": "warning",
                    "correlated_subquery": "info",
                },
            ),
            exclude_patterns=data.get("exclude_patterns", []),
            output_format=data.get("output_format", "console"),
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Configuration as dictionary
        """
        return {
            "enabled": self.enabled,
            "rules_file": self.rules_file,
            "rule_profile": self.rule_profile,
            "rules": list(self.rules),
            "fail_on": self.fail_on,
            "severity_threshold": self.severity_threshold,
            "performance_enabled": self.performance_enabled,
            "performance_rules": self.performance_rules,
            "exclude_patterns": self.exclude_patterns,
            "output_format": self.output_format,
        }

    def get_rules_path(self) -> Optional[Path]:
        """
        Get Path object for rules file if configured.

        Returns:
            Path to rules file or None
        """
        if self.rules_file:
            return Path(self.rules_file)
        return None
