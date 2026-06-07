"""Integration tests: secret URIs resolved end-to-end through DbliftConfig.from_dict()."""

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

from config.secrets._resolver import clear_cache


@pytest.fixture(autouse=True)
def _clear_resolver_cache() -> None:
    clear_cache()


class TestSecretsConfigFromDict:
    def test_empty_secrets_block_gives_defaults(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict({})
        assert cfg.vault_url is None
        assert cfg.vault_token is None
        assert cfg.aws_region is None
        assert cfg.azure_vault_name is None
        assert cfg.gcp_project_id is None
        assert cfg.cache_ttl_seconds == 60.0

    def test_nested_vault_block_parsed(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict(
            {
                "vault": {
                    "url": "https://vault.example.com",
                    "token": "tok",
                    "namespace": "prod",
                }
            }
        )
        assert cfg.vault_url == "https://vault.example.com"
        assert cfg.vault_token == "tok"
        assert cfg.vault_namespace == "prod"

    def test_aws_block_parsed(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict({"aws": {"region": "eu-west-1"}})
        assert cfg.aws_region == "eu-west-1"

    def test_azure_block_parsed(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict({"azure": {"vault_name": "myvault"}})
        assert cfg.azure_vault_name == "myvault"

    def test_gcp_block_parsed(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict({"gcp": {"project_id": "my-proj"}})
        assert cfg.gcp_project_id == "my-proj"

    def test_cache_ttl_parsed(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict({"cache_ttl_seconds": 120})
        assert cfg.cache_ttl_seconds == 120.0


class TestDbliftConfigResolvesSecrets:
    """End-to-end: DbliftConfig.from_dict() resolves vault:// URIs in the database block."""

    def _make_config_data(self, password_value: str) -> dict:
        return {
            "database": {
                "url": "postgresql+psycopg://prod-db:5432/myapp",
                "username": "myuser",
                "password": password_value,
            }
        }

    def test_plain_password_unchanged(self) -> None:
        from config.dblift_config import DbliftConfig

        cfg = DbliftConfig.from_dict(self._make_config_data("plain-password"))
        assert cfg.database.password == "plain-password"

    def test_vault_uri_resolved_in_database_password(self) -> None:
        from config.dblift_config import DbliftConfig

        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.read.return_value = {"data": {"password": "example-vault-pw"}}

            cfg = DbliftConfig.from_dict(
                {
                    "database": {
                        "url": "postgresql+psycopg://prod-db:5432/myapp",
                        "username": "myuser",
                        "password": "vault://secret/myapp/db#password",
                    },
                    "secrets": {
                        "vault": {
                            "url": "http://vault:8200",
                            "token": "test-token",
                        }
                    },
                }
            )

        assert cfg.database.password == "example-vault-pw"

    def test_aws_secrets_uri_resolved_in_database_password(self) -> None:
        from config.dblift_config import DbliftConfig

        secret_payload = json.dumps({"password": "example-aws-pw"})
        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretString": secret_payload}

            cfg = DbliftConfig.from_dict(
                {
                    "database": {
                        "url": "postgresql+psycopg://prod-db:5432/myapp",
                        "username": "myuser",
                        "password": "aws-secrets://prod/myapp/db#password",
                    },
                    "secrets": {"aws": {"region": "us-east-1"}},
                }
            )

        assert cfg.database.password == "example-aws-pw"

    def test_secrets_config_stored_on_dblift_config(self) -> None:
        from config.dblift_config import DbliftConfig

        cfg = DbliftConfig.from_dict(
            {
                "database": {
                    "url": "postgresql+psycopg://localhost:5432/db",
                    "username": "u",
                    "password": "p",
                },
                "secrets": {
                    "vault": {"url": "https://vault.example.com", "token": "tok"},
                    "cache_ttl_seconds": 30,
                },
            }
        )
        assert cfg.secrets.vault_url == "https://vault.example.com"
        assert cfg.secrets.vault_token == "tok"
        assert cfg.secrets.cache_ttl_seconds == 30.0

    def test_no_secrets_block_uses_defaults(self) -> None:
        from config.dblift_config import DbliftConfig

        cfg = DbliftConfig.from_dict(
            {
                "database": {
                    "url": "postgresql+psycopg://localhost:5432/db",
                    "username": "u",
                    "password": "p",
                }
            }
        )
        from config.secrets._secrets_config import SecretsConfig

        assert isinstance(cfg.secrets, SecretsConfig)


class TestSecretsConfigFromDictFiltersSecretUris:
    """SecretsConfig.from_dict must treat URI-valued provider fields as None.

    When a provider config field (aws_region, vault_token, …) is itself a
    secret URI, passing the raw URI string to the provider causes boto3/hvac
    to use it as a region / URL, which silently skips env-var fallbacks and
    breaks Phase-1 bootstrap resolution.
    """

    def test_secret_uri_as_aws_region_is_treated_as_none(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict({"aws": {"region": "aws-ssm:///prod/region"}})
        assert cfg.aws_region is None

    def test_secret_uri_as_vault_token_is_treated_as_none(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict(
            {"vault": {"url": "https://vault.example.com", "token": "aws-secrets://prod/tok"}}
        )
        assert cfg.vault_url == "https://vault.example.com"
        assert cfg.vault_token is None

    def test_plain_string_values_are_preserved(self) -> None:
        from config.secrets._secrets_config import SecretsConfig

        cfg = SecretsConfig.from_dict(
            {
                "vault": {"url": "https://vault.example.com", "token": "s.mytoken"},
                "aws": {"region": "us-east-1"},
                "azure": {"vault_name": "myvault"},
                "gcp": {"project_id": "my-project"},
            }
        )
        assert cfg.vault_url == "https://vault.example.com"
        assert cfg.vault_token == "s.mytoken"
        assert cfg.aws_region == "us-east-1"
        assert cfg.azure_vault_name == "myvault"
        assert cfg.gcp_project_id == "my-project"
        assert cfg.cache_ttl_seconds == 60.0
