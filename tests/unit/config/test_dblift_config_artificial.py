from unittest.mock import patch

import pytest
import yaml

pytestmark = [pytest.mark.unit]

from config.dblift_config import DbliftConfig


# Artificial: to_dict with all optional fields set
def test_to_dict_all_optionals():
    config = DbliftConfig.from_dict(
        {
            "database": {
                "url": "postgresql+psycopg://localhost:5432/db",
                "username": "pg",
                "password": "pw",
            }
        }
    )
    config.extra_params = {"foo": "bar"}
    config.tags = "t1"
    config.exclude_tags = "t2"
    config.versions = "v1"
    config.exclude_versions = "v2"
    config.placeholders = {"x": "y"}
    # journal_dir is always None in practice (journal is always in-memory only)
    # but to_dict() can serialize it if set (for testing purposes)
    config.journal_dir = "jdir"
    config.retryable_error_categories = ["foo", "bar"]
    d = config.to_dict()
    assert d["extra_params"]["foo"] == "bar"
    assert d["tags"] == "t1"
    # journal_dir is included in dict if set (though in practice it's always None)
    assert d["journal_dir"] == "jdir"
    assert d["retryable_error_categories"] == ["foo", "bar"]


# Artificial: patch os.path.isabs and os.path.exists
@patch("os.path.isabs", return_value=True)
@patch("os.path.exists", return_value=False)
@patch.object(DbliftConfig, "_load_yaml_file", return_value={})
def test_path_normalization_and_file_existence(mock_load_yaml, mock_exists, mock_isabs, tmp_path):
    # Should skip file loading branch and not raise
    args = {
        "db_url": "postgresql+psycopg://localhost:5432/db",
        "db_username": "pg",
        "db_password": "pw",
        "config_file": str(tmp_path / "nofile.yaml"),
    }
    config = DbliftConfig.from_all_sources(args)
    assert config.database.username == "pg"


# Artificial: patch yaml.safe_load to return None or malformed data in _load_yaml_file
@patch("yaml.safe_load", return_value=None)
def test_load_yaml_file_none(mock_safe_load, tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("")
    result = DbliftConfig._load_yaml_file(str(f))
    assert result == {}


@patch("yaml.safe_load", return_value={"database": 123})
def test_load_yaml_file_malformed(mock_safe_load, tmp_path):
    f = tmp_path / "malformed.yaml"
    f.write_text("foo: bar")
    result = DbliftConfig._load_yaml_file(str(f))
    assert result["database"] == 123


# Artificial: simulate yaml.YAMLError in from_file
@patch("yaml.safe_load", side_effect=yaml.YAMLError("bad yaml"))
def test_from_file_yaml_error(mock_safe_load, tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text(":not yaml:")
    with pytest.raises(yaml.YAMLError):
        DbliftConfig.from_file(str(f))
