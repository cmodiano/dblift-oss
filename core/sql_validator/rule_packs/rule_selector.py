"""Rule selection system for DBLift validation rules.

This module provides functionality to select rules from rule packs:
- Load full rule packs
- Select individual rules by name
- Combine multiple rule packs
- Combine rule packs with individual rules
- Load from declarative YAML configuration
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

import yaml  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


class RuleSelector:
    """
    Selector for combining rule packs and individual rules.

    Supports:
    - Loading full rule packs: "performance", "security", etc.
    - Selecting individual rules: ["fk_must_have_index", "no_select_star"]
    - Combining both: ["performance", "security", "fk_must_have_index"]
    - Loading from declarative YAML configuration
    """

    def __init__(self, rule_packs_dir: Optional[Path] = None):
        """
        Initialize the rule selector.

        Args:
            rule_packs_dir: Directory containing rule pack YAML files.
                          If None, uses default rule_packs directory.
        """
        if rule_packs_dir is None:
            rule_packs_dir = Path(__file__).parent

        self.rule_packs_dir = rule_packs_dir
        self._rule_cache: Dict[str, Dict[str, Any]] = {}

    def select_rules(
        self,
        selection: Union[str, List[Union[str, Dict[str, Any]]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Select rules based on pack names and/or individual rule names.

        Args:
            selection: Can be:
                - String: Name of a rule pack (e.g., "performance")
                - List of strings: Multiple rule packs and/or rule names
                - List of dicts: Custom rule definitions
                - Mixed: Combination of packs, rule names, and custom rules
                - Dict: YAML-style configuration with 'rule_packs', 'rules', 'exclude_rules'

        Returns:
            Dictionary with "rules" key containing list of selected rules

        Examples:
            >>> selector = RuleSelector()
            >>> # Load full pack
            >>> rules = selector.select_rules("performance")
            >>> # Load multiple packs
            >>> rules = selector.select_rules(["performance", "security"])
            >>> # Load pack + individual rules
            >>> rules = selector.select_rules(["performance", "fk_must_have_index"])
            >>> # YAML-style configuration
            >>> rules = selector.select_rules({
            ...     "rule_packs": ["performance", "security"],
            ...     "rules": ["fk_must_have_index"],
            ...     "exclude_rules": ["some_rule"]
            ... })
        """
        # Handle YAML-style dictionary configuration
        if isinstance(selection, dict):
            return self._select_from_config(selection)

        if isinstance(selection, str):
            selection = [selection]

        selected_rules: List[Dict[str, Any]] = []
        seen_rule_names: Set[str] = set()

        for item in selection:
            if isinstance(item, dict):
                # Custom rule definition
                rule_name = item.get("name", "unknown")
                if isinstance(rule_name, str) and rule_name not in seen_rule_names:
                    selected_rules.append(item)
                    seen_rule_names.add(rule_name)
            elif isinstance(item, str):
                # Could be a pack name or rule name
                if self._is_rule_pack(item):
                    # Load entire pack
                    pack_rules = self._load_rule_pack(item)
                    for pack_rule in pack_rules:
                        rule_name = pack_rule.get("name")
                        if isinstance(rule_name, str) and rule_name not in seen_rule_names:
                            selected_rules.append(pack_rule)
                            seen_rule_names.add(rule_name)
                else:
                    # Try to find rule by name across all packs
                    rule = self._find_rule_by_name(item)
                    if rule is None:
                        logger.warning(f"Rule or pack '{item}' not found. Skipping.")
                    else:
                        rule_name = rule.get("name")
                        if isinstance(rule_name, str) and rule_name not in seen_rule_names:
                            selected_rules.append(rule)
                            seen_rule_names.add(rule_name)
            else:
                logger.warning(
                    "Unsupported selection item type '%s'. Skipping.", type(item).__name__
                )

        return {"rules": selected_rules}

    def _select_from_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Select rules from a YAML-style configuration dictionary.

        Args:
            config: Configuration dictionary with:
                - rule_packs: List of rule pack names
                - rules: List of individual rule names
                - exclude_rules: List of rule names to exclude
                - custom_rules: List of custom rule definitions

        Returns:
            Dictionary with "rules" key containing selected rules
        """
        selected_rules: List[Dict[str, Any]] = []
        seen_rule_names: Set[str] = set()

        # Load rule packs
        rule_packs = config.get("rule_packs") or []
        for pack_name in rule_packs:
            if not isinstance(pack_name, str):
                logger.warning("Rule pack names must be strings. Skipping invalid entry.")
                continue
            pack_rules = self._load_rule_pack(pack_name)
            for pack_rule in pack_rules:
                rule_name = pack_rule.get("name")
                if isinstance(rule_name, str) and rule_name not in seen_rule_names:
                    selected_rules.append(pack_rule)
                    seen_rule_names.add(rule_name)

        # Add individual rules
        individual_rules = config.get("rules") or []
        for rule_name in individual_rules:
            if not isinstance(rule_name, str):
                logger.warning("Rule names must be strings. Skipping invalid entry.")
                continue
            rule = self._find_rule_by_name(rule_name)
            if rule is None:
                logger.warning(f"Rule '{rule_name}' not found. Skipping.")
                continue
            rule_name_val = rule.get("name")
            if isinstance(rule_name_val, str) and rule_name_val not in seen_rule_names:
                selected_rules.append(rule)
                seen_rule_names.add(rule_name_val)

        # Add custom rules
        custom_rules = config.get("custom_rules") or []
        for custom_rule in custom_rules:
            if isinstance(custom_rule, dict):
                rule_name = custom_rule.get("name", "unknown")
                if isinstance(rule_name, str) and rule_name not in seen_rule_names:
                    selected_rules.append(custom_rule)
                    seen_rule_names.add(rule_name)

        # Exclude specified rules
        exclude_rules = config.get("exclude_rules") or []
        if exclude_rules:
            exclude_set = {name for name in exclude_rules if isinstance(name, str)}
            selected_rules = [
                rule
                for rule in selected_rules
                if isinstance(rule, dict) and rule.get("name") not in exclude_set
            ]

        return {"rules": selected_rules}

    def load_from_yaml(self, yaml_path: Union[str, Path]) -> Dict[str, Any]:
        """
        Load rule selection from a YAML configuration file.

        Args:
            yaml_path: Path to YAML configuration file

        Returns:
            Dictionary with "rules" key containing selected rules

        Example YAML format:
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
                prohibit: "DROP TABLE"
                message: "Custom message"
                severity: error
        """
        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Rule configuration file not found: {yaml_path}")

        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config:
                logger.warning(f"Empty configuration file: {yaml_path}")
                return {"rules": []}
            if not isinstance(config, dict):
                logger.warning(
                    f"Invalid configuration format in {yaml_path}. Expected a dictionary."
                )
                return {"rules": []}

            return self._select_from_config(config)
        except Exception as e:
            logger.error(f"Failed to load rule configuration from {yaml_path}: {e}")
            raise

    def _is_rule_pack(self, name: str) -> bool:
        """
        Check if a name corresponds to a rule pack file.

        Args:
            name: Name to check

        Returns:
            True if a rule pack file exists with this name
        """
        pack_file = self.rule_packs_dir / f"{name}.yaml"
        return pack_file.exists()

    def _load_rule_pack(self, pack_name: str) -> List[Dict[str, Any]]:
        """
        Load a rule pack by name.

        Args:
            pack_name: Name of the rule pack (without .yaml extension)

        Returns:
            List of rules from the pack
        """
        if pack_name in self._rule_cache:
            pack_data = self._rule_cache[pack_name]
            return self._extract_rules_from_pack(pack_name, pack_data)

        pack_file = self.rule_packs_dir / f"{pack_name}.yaml"
        if not pack_file.exists():
            logger.error(f"Rule pack '{pack_name}' not found at {pack_file}")
            return []

        try:
            with open(pack_file, "r", encoding="utf-8") as f:
                pack_data = yaml.safe_load(f)
                if not isinstance(pack_data, dict):
                    logger.error(
                        f"Rule pack '{pack_name}' has invalid format. Expected a dictionary."
                    )
                    return []
                self._rule_cache[pack_name] = pack_data
                return self._extract_rules_from_pack(pack_name, pack_data)
        except Exception as e:
            logger.error(f"Failed to load rule pack '{pack_name}': {e}")
            return []

    def _extract_rules_from_pack(
        self, pack_name: str, pack_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        rules_data = pack_data.get("rules", [])
        if not isinstance(rules_data, list):
            logger.error(f"Rule pack '{pack_name}' has invalid 'rules' section. Expected a list.")
            return []
        rules: List[Dict[str, Any]] = []
        for rule in rules_data:
            if isinstance(rule, dict):
                rules.append(rule)
            else:
                logger.warning(
                    "Skipping rule entry in pack '%s' because it is not a dictionary.",
                    pack_name,
                )
        return rules

    def _find_rule_by_name(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """
        Find a rule by name across all available rule packs.

        Args:
            rule_name: Name of the rule to find

        Returns:
            Rule dictionary if found, None otherwise
        """
        # Get all YAML files in rule packs directory
        for pack_file in self.rule_packs_dir.glob("*.yaml"):
            if pack_file.name == "__init__.py" or pack_file.name == "example_rules_config.yaml":
                continue

            pack_name = pack_file.stem
            rules = self._load_rule_pack(pack_name)

            for rule in rules:
                if isinstance(rule, dict) and rule.get("name") == rule_name:
                    return rule

        return None

    def list_available_packs(self) -> List[str]:
        """
        List all available rule pack names.

        Returns:
            List of rule pack names (without .yaml extension)
        """
        packs = []
        for pack_file in self.rule_packs_dir.glob("*.yaml"):
            if pack_file.name != "__init__.py":
                packs.append(pack_file.stem)
        return sorted(packs)

    def list_rules_in_pack(self, pack_name: str) -> List[str]:
        """
        List all rule names in a specific pack.

        Args:
            pack_name: Name of the rule pack

        Returns:
            List of rule names in the pack
        """
        rules = self._load_rule_pack(pack_name)
        return [
            rule_name
            for rule_name in (rule.get("name") for rule in rules)
            if isinstance(rule_name, str)
        ]

    def get_rule_info(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific rule.

        Args:
            rule_name: Name of the rule

        Returns:
            Dictionary with rule information, or None if not found
        """
        rule = self._find_rule_by_name(rule_name)
        if rule:
            name = rule.get("name")
            if not isinstance(name, str):
                return None
            return {
                "name": name,
                "type": rule.get("type"),
                "severity": rule.get("severity", "warning"),
                "message": rule.get("message"),
                "target": rule.get("target"),
            }
        return None


def create_rules_from_selection(
    selection: Union[str, List[Union[str, Dict[str, Any]]], Dict[str, Any]],
    rule_packs_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Convenience function to create a rules dictionary from a selection.

    Args:
        selection: Rule pack names, rule names, custom rules, or YAML config dict
        rule_packs_dir: Optional directory containing rule packs

    Returns:
        Dictionary with "rules" key containing selected rules

    Examples:
        >>> # Use full pack
        >>> rules = create_rules_from_selection("performance")
        >>> # Combine packs
        >>> rules = create_rules_from_selection(["performance", "security"])
        >>> # Pack + individual rules
        >>> rules = create_rules_from_selection(["performance", "fk_must_have_index"])
        >>> # YAML config dict
        >>> rules = create_rules_from_selection({
        ...     "rule_packs": ["performance"],
        ...     "rules": ["fk_must_have_index"]
        ... })
    """
    selector = RuleSelector(rule_packs_dir)
    return selector.select_rules(selection)
