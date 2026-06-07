"""Tests for rule selector."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from core.sql_validator.rule_packs.rule_selector import RuleSelector, create_rules_from_selection


@pytest.mark.unit
class TestRuleSelector:
    """Test RuleSelector class."""

    def test_selector_creation_default_dir(self):
        """Test creating selector with default directory."""
        selector = RuleSelector()
        assert selector.rule_packs_dir is not None
        assert selector._rule_cache == {}

    def test_selector_creation_custom_dir(self):
        """Test creating selector with custom directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            selector = RuleSelector(rule_packs_dir=Path(tmpdir))
            assert selector.rule_packs_dir == Path(tmpdir)

    def test_is_rule_pack(self):
        """Test checking if name is a rule pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text("rules: []")

            selector = RuleSelector(rule_packs_dir=pack_dir)
            assert selector._is_rule_pack("test_pack") is True
            assert selector._is_rule_pack("nonexistent") is False

    def test_load_rule_pack(self):
        """Test loading a rule pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(
                yaml.dump(
                    {
                        "rules": [
                            {"name": "rule1", "type": "pattern", "prohibit": "DROP TABLE"},
                            {"name": "rule2", "type": "pattern", "prohibit": "DELETE"},
                        ]
                    }
                )
            )

            selector = RuleSelector(rule_packs_dir=pack_dir)
            rules = selector._load_rule_pack("test_pack")

            assert len(rules) == 2
            assert rules[0]["name"] == "rule1"
            assert rules[1]["name"] == "rule2"

    def test_load_rule_pack_cached(self):
        """Test that rule pack is cached."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1"}]}))

            selector = RuleSelector(rule_packs_dir=pack_dir)
            rules1 = selector._load_rule_pack("test_pack")
            rules2 = selector._load_rule_pack("test_pack")

            assert len(rules1) == 1
            assert len(rules2) == 1
            assert "test_pack" in selector._rule_cache

    def test_load_rule_pack_nonexistent(self):
        """Test loading nonexistent rule pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            selector = RuleSelector(rule_packs_dir=Path(tmpdir))
            rules = selector._load_rule_pack("nonexistent")
            assert rules == []

    def test_load_rule_pack_invalid_format(self):
        """Test loading rule pack with invalid format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text("invalid: yaml: content:")

            selector = RuleSelector(rule_packs_dir=pack_dir)
            rules = selector._load_rule_pack("test_pack")
            assert rules == []

    def test_extract_rules_from_pack(self):
        """Test extracting rules from pack data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            selector = RuleSelector(rule_packs_dir=Path(tmpdir))

            pack_data = {
                "rules": [
                    {"name": "rule1", "type": "pattern"},
                    {"name": "rule2", "type": "pattern"},
                    "invalid",  # Should be skipped
                ]
            }

            rules = selector._extract_rules_from_pack("test_pack", pack_data)
            assert len(rules) == 2

    def test_extract_rules_from_pack_invalid_rules(self):
        """Test extracting rules when rules is not a list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            selector = RuleSelector(rule_packs_dir=Path(tmpdir))

            pack_data = {"rules": "not a list"}

            rules = selector._extract_rules_from_pack("test_pack", pack_data)
            assert rules == []

    def test_find_rule_by_name(self):
        """Test finding a rule by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(
                yaml.dump(
                    {
                        "rules": [
                            {"name": "rule1", "type": "pattern"},
                            {"name": "rule2", "type": "pattern"},
                        ]
                    }
                )
            )

            selector = RuleSelector(rule_packs_dir=pack_dir)
            rule = selector._find_rule_by_name("rule1")

            assert rule is not None
            assert rule["name"] == "rule1"

    def test_find_rule_by_name_not_found(self):
        """Test finding nonexistent rule."""
        with tempfile.TemporaryDirectory() as tmpdir:
            selector = RuleSelector(rule_packs_dir=Path(tmpdir))
            rule = selector._find_rule_by_name("nonexistent")
            assert rule is None

    def test_select_rules_string_pack(self):
        """Test selecting rules from string pack name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            selector = RuleSelector(rule_packs_dir=pack_dir)
            result = selector.select_rules("test_pack")

            assert "rules" in result
            assert len(result["rules"]) == 1
            assert result["rules"][0]["name"] == "rule1"

    def test_select_rules_list_packs(self):
        """Test selecting rules from list of pack names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file1 = pack_dir / "pack1.yaml"
            pack_file1.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))
            pack_file2 = pack_dir / "pack2.yaml"
            pack_file2.write_text(yaml.dump({"rules": [{"name": "rule2", "type": "pattern"}]}))

            selector = RuleSelector(rule_packs_dir=pack_dir)
            result = selector.select_rules(["pack1", "pack2"])

            assert len(result["rules"]) == 2

    def test_select_rules_duplicate_handling(self):
        """Test that duplicate rules are handled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(
                yaml.dump(
                    {
                        "rules": [
                            {"name": "rule1", "type": "pattern"},
                            {"name": "rule1", "type": "pattern"},  # Duplicate
                        ]
                    }
                )
            )

            selector = RuleSelector(rule_packs_dir=pack_dir)
            result = selector.select_rules("test_pack")

            # Should only include one instance
            assert len(result["rules"]) == 1

    def test_select_rules_custom_rule_dict(self):
        """Test selecting custom rule from dict."""
        selector = RuleSelector()

        custom_rule = {"name": "custom_rule", "type": "pattern", "prohibit": "DROP"}
        result = selector.select_rules([custom_rule])

        assert len(result["rules"]) == 1
        assert result["rules"][0]["name"] == "custom_rule"

    def test_select_rules_mixed_packs_and_rules(self):
        """Test selecting from mixed packs and individual rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            selector = RuleSelector(rule_packs_dir=pack_dir)
            result = selector.select_rules(["test_pack", "rule1"])

            # Should have rule1 from pack and rule1 found individually
            assert len(result["rules"]) >= 1

    def test_select_rules_dict_config(self):
        """Test selecting rules from dict configuration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            selector = RuleSelector(rule_packs_dir=pack_dir)
            config = {
                "rule_packs": ["test_pack"],
                "rules": ["rule1"],
                "exclude_rules": [],
            }
            result = selector.select_rules(config)

            assert "rules" in result
            assert len(result["rules"]) >= 1

    def test_select_from_config_with_exclude(self):
        """Test selecting rules with exclusions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(
                yaml.dump(
                    {
                        "rules": [
                            {"name": "rule1", "type": "pattern"},
                            {"name": "rule2", "type": "pattern"},
                        ]
                    }
                )
            )

            selector = RuleSelector(rule_packs_dir=pack_dir)
            config = {
                "rule_packs": ["test_pack"],
                "exclude_rules": ["rule1"],
            }
            result = selector._select_from_config(config)

            rule_names = [r["name"] for r in result["rules"]]
            assert "rule1" not in rule_names
            assert "rule2" in rule_names

    def test_select_from_config_custom_rules(self):
        """Test selecting rules with custom rules."""
        selector = RuleSelector()

        config = {
            "custom_rules": [
                {"name": "custom1", "type": "pattern"},
                {"name": "custom2", "type": "pattern"},
            ]
        }
        result = selector._select_from_config(config)

        assert len(result["rules"]) == 2
        assert result["rules"][0]["name"] == "custom1"

    def test_select_from_config_invalid_pack_name(self):
        """Test handling invalid pack names."""
        selector = RuleSelector()

        config = {"rule_packs": [123, "valid_pack"]}  # Invalid: not a string
        result = selector._select_from_config(config)

        # Should handle gracefully
        assert "rules" in result

    def test_load_from_yaml(self):
        """Test loading rules from YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            yaml_config = pack_dir / "config.yaml"
            yaml_config.write_text(yaml.dump({"rule_packs": ["test_pack"], "rules": ["rule1"]}))

            selector = RuleSelector(rule_packs_dir=pack_dir)
            result = selector.load_from_yaml(yaml_config)

            assert "rules" in result
            assert len(result["rules"]) >= 1

    def test_load_from_yaml_nonexistent(self):
        """Test loading from nonexistent YAML file."""
        selector = RuleSelector()

        with pytest.raises(FileNotFoundError):
            selector.load_from_yaml("nonexistent.yaml")

    def test_load_from_yaml_empty(self):
        """Test loading from empty YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_file = Path(tmpdir) / "empty.yaml"
            yaml_file.write_text("")

            selector = RuleSelector()
            result = selector.load_from_yaml(yaml_file)

            assert result["rules"] == []

    def test_load_from_yaml_invalid_format(self):
        """Test loading from invalid YAML format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yaml_file = Path(tmpdir) / "invalid.yaml"
            yaml_file.write_text("not a dict: invalid")

            selector = RuleSelector()
            result = selector.load_from_yaml(yaml_file)

            assert result["rules"] == []

    def test_list_available_packs(self):
        """Test listing available rule packs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file1 = pack_dir / "pack1.yaml"
            pack_file1.write_text("rules: []")
            pack_file2 = pack_dir / "pack2.yaml"
            pack_file2.write_text("rules: []")

            selector = RuleSelector(rule_packs_dir=pack_dir)
            packs = selector.list_available_packs()

            assert "pack1" in packs
            assert "pack2" in packs

    def test_list_rules_in_pack(self):
        """Test listing rules in a pack."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(
                yaml.dump(
                    {
                        "rules": [
                            {"name": "rule1", "type": "pattern"},
                            {"name": "rule2", "type": "pattern"},
                        ]
                    }
                )
            )

            selector = RuleSelector(rule_packs_dir=pack_dir)
            rules = selector.list_rules_in_pack("test_pack")

            assert "rule1" in rules
            assert "rule2" in rules

    def test_get_rule_info(self):
        """Test getting rule information."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(
                yaml.dump(
                    {
                        "rules": [
                            {
                                "name": "rule1",
                                "type": "pattern",
                                "severity": "error",
                                "message": "Test message",
                                "target": "table",
                            }
                        ]
                    }
                )
            )

            selector = RuleSelector(rule_packs_dir=pack_dir)
            info = selector.get_rule_info("rule1")

            assert info is not None
            assert info["name"] == "rule1"
            assert info["type"] == "pattern"
            assert info["severity"] == "error"

    def test_get_rule_info_not_found(self):
        """Test getting info for nonexistent rule."""
        selector = RuleSelector()
        info = selector.get_rule_info("nonexistent")
        assert info is None

    def test_get_rule_info_no_name(self):
        """Test getting info for rule without name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"type": "pattern"}]}))  # No name

            selector = RuleSelector(rule_packs_dir=pack_dir)
            # This should not crash, but may return None or handle gracefully
            rules = selector._load_rule_pack("test_pack")
            assert len(rules) == 1


@pytest.mark.unit
class TestCreateRulesFromSelection:
    """Test create_rules_from_selection convenience function."""

    def test_create_rules_from_selection_string(self):
        """Test creating rules from string selection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            result = create_rules_from_selection("test_pack", rule_packs_dir=pack_dir)

            assert "rules" in result
            assert len(result["rules"]) == 1

    def test_create_rules_from_selection_list(self):
        """Test creating rules from list selection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            result = create_rules_from_selection(["test_pack"], rule_packs_dir=pack_dir)

            assert "rules" in result
            assert len(result["rules"]) == 1

    def test_create_rules_from_selection_dict(self):
        """Test creating rules from dict selection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pack_dir = Path(tmpdir)
            pack_file = pack_dir / "test_pack.yaml"
            pack_file.write_text(yaml.dump({"rules": [{"name": "rule1", "type": "pattern"}]}))

            config = {"rule_packs": ["test_pack"]}
            result = create_rules_from_selection(config, rule_packs_dir=pack_dir)

            assert "rules" in result
            assert len(result["rules"]) == 1
