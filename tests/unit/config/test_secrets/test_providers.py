"""Tests for each secrets provider (mocked SDKs)."""

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

from config.secrets._provider_base import SecretsResolutionError
from config.secrets._secrets_config import SecretsConfig

# ---------------------------------------------------------------------------
# HashiCorp Vault
# ---------------------------------------------------------------------------


class TestHashiCorpVaultProvider:
    @pytest.fixture()
    def config(self) -> SecretsConfig:
        return SecretsConfig(vault_url="http://vault:8200", vault_token="test-token")

    @pytest.fixture()
    def provider(self, config: SecretsConfig) -> "HashiCorpVaultProvider":
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        return HashiCorpVaultProvider(config)

    def test_scheme(self, provider: "HashiCorpVaultProvider") -> None:
        assert provider.scheme == "vault"

    def test_is_available_with_token(self, provider: "HashiCorpVaultProvider") -> None:
        assert provider.is_available() is True

    def test_is_available_without_token(self) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        p = HashiCorpVaultProvider(SecretsConfig(vault_url="http://vault:8200"))
        assert p.is_available() is False

    def test_is_available_uses_env_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        monkeypatch.setenv("VAULT_TOKEN", "env-token")
        p = HashiCorpVaultProvider(SecretsConfig(vault_url="http://vault:8200"))
        assert p.is_available() is True

    def test_resolve_returns_field_from_secret(self, config: SecretsConfig) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.read.return_value = {"data": {"password": "db-secret", "user": "admin"}}
            p = HashiCorpVaultProvider(config)
            result = p.resolve("vault://secret/myapp/db#password")

        assert result == "db-secret"
        mock_client.read.assert_called_once_with("secret/myapp/db")

    def test_resolve_kv_v2_unwraps_nested_data(self, config: SecretsConfig) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        kv_v2_response = {
            "data": {
                "data": {"password": "kv2-secret"},
                "metadata": {"version": 3},
            }
        }
        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.read.return_value = kv_v2_response
            p = HashiCorpVaultProvider(config)
            result = p.resolve("vault://secret/data/myapp/db#password")

        assert result == "kv2-secret"

    def test_resolve_missing_hash_raises(self, provider: "HashiCorpVaultProvider") -> None:
        with pytest.raises(SecretsResolutionError, match="#"):
            provider.resolve("vault://secret/myapp/db")

    def test_resolve_missing_field_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.read.return_value = {"data": {"other": "val"}}
            p = HashiCorpVaultProvider(config)
            with pytest.raises(SecretsResolutionError, match="password"):
                p.resolve("vault://secret/myapp/db#password")

    def test_resolve_non_dict_secret_data_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            # KV v2 inner data is a scalar rather than a dict
            mock_client.read.return_value = {
                "data": {"data": "not-a-dict", "metadata": {"version": 1}}
            }
            p = HashiCorpVaultProvider(config)
            with pytest.raises(SecretsResolutionError, match="not a key-value object"):
                p.resolve("vault://secret/data/myapp/db#password")

    def test_resolve_vault_error_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.read.side_effect = Exception("connection refused")
            p = HashiCorpVaultProvider(config)
            with pytest.raises(SecretsResolutionError, match="connection refused"):
                p.resolve("vault://secret/myapp/db#password")

    def test_env_vault_addr_used_when_no_config_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from config.secrets.providers._hashicorp_vault import HashiCorpVaultProvider

        monkeypatch.setenv("VAULT_ADDR", "http://env-vault:8200")
        monkeypatch.setenv("VAULT_TOKEN", "env-token")
        with patch("hvac.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.read.return_value = {"data": {"pw": "s"}}
            p = HashiCorpVaultProvider(SecretsConfig())
            p.resolve("vault://path/secret#pw")
            _, kwargs = mock_cls.call_args
            assert kwargs.get("url") == "http://env-vault:8200"


# ---------------------------------------------------------------------------
# AWS Secrets Manager
# ---------------------------------------------------------------------------


class TestAwsSecretsManagerProvider:
    @pytest.fixture()
    def config(self) -> SecretsConfig:
        return SecretsConfig(aws_region="us-east-1")

    def test_scheme(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        assert AwsSecretsManagerProvider(config).scheme == "aws-secrets"

    def test_is_available_when_boto3_present(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        assert AwsSecretsManagerProvider(config).is_available() is True

    def test_resolve_json_secret_with_field(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        secret_payload = json.dumps({"password": "aws-db-secret", "username": "admin"})
        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretString": secret_payload}
            p = AwsSecretsManagerProvider(config)
            result = p.resolve("aws-secrets://prod/myapp/db#password")

        assert result == "aws-db-secret"
        mock_client.get_secret_value.assert_called_once_with(SecretId="prod/myapp/db")

    def test_resolve_plain_string_secret_no_field(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretString": "plain-password"}
            p = AwsSecretsManagerProvider(config)
            result = p.resolve("aws-secrets://prod/myapp/plain-secret")

        assert result == "plain-password"

    def test_resolve_binary_secret_decoded(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretBinary": b"binary-password"}
            p = AwsSecretsManagerProvider(config)
            result = p.resolve("aws-secrets://prod/myapp/bin-secret")

        assert result == "binary-password"

    def test_resolve_neither_string_nor_binary_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {}
            p = AwsSecretsManagerProvider(config)
            with pytest.raises(SecretsResolutionError, match="SecretBinary"):
                p.resolve("aws-secrets://prod/myapp/empty-secret")

    def test_resolve_non_object_json_with_field_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretString": "[1,2,3]"}
            p = AwsSecretsManagerProvider(config)
            with pytest.raises(SecretsResolutionError, match="not a JSON object"):
                p.resolve("aws-secrets://prod/myapp/array-secret#password")

    def test_resolve_missing_field_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        secret_payload = json.dumps({"other": "val"})
        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretString": secret_payload}
            p = AwsSecretsManagerProvider(config)
            with pytest.raises(SecretsResolutionError, match="password"):
                p.resolve("aws-secrets://prod/myapp/db#password")

    def test_resolve_aws_error_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.side_effect = Exception("ResourceNotFoundException")
            p = AwsSecretsManagerProvider(config)
            with pytest.raises(SecretsResolutionError, match="ResourceNotFoundException"):
                p.resolve("aws-secrets://prod/myapp/db#password")

    def test_uses_env_region_when_no_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from config.secrets.providers._aws_secrets_manager import AwsSecretsManagerProvider

        monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-west-1")
        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_secret_value.return_value = {"SecretString": "val"}
            p = AwsSecretsManagerProvider(SecretsConfig())
            p.resolve("aws-secrets://secret")
            mock_client_fn.assert_called_once_with("secretsmanager", region_name="eu-west-1")


# ---------------------------------------------------------------------------
# AWS SSM Parameter Store
# ---------------------------------------------------------------------------


class TestAwsSsmProvider:
    @pytest.fixture()
    def config(self) -> SecretsConfig:
        return SecretsConfig(aws_region="us-east-1")

    def test_scheme(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_ssm import AwsSsmProvider

        assert AwsSsmProvider(config).scheme == "aws-ssm"

    def test_is_available(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_ssm import AwsSsmProvider

        assert AwsSsmProvider(config).is_available() is True

    def test_resolve_parameter(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_ssm import AwsSsmProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_parameter.return_value = {"Parameter": {"Value": "ssm-password"}}
            p = AwsSsmProvider(config)
            result = p.resolve("aws-ssm:///prod/db/password")

        assert result == "ssm-password"
        mock_client.get_parameter.assert_called_once_with(
            Name="/prod/db/password", WithDecryption=True
        )

    def test_resolve_strips_double_slash_prefix(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_ssm import AwsSsmProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_parameter.return_value = {"Parameter": {"Value": "v"}}
            p = AwsSsmProvider(config)
            # aws-ssm://prod/param (no leading slash)
            p.resolve("aws-ssm://prod/param")
            mock_client.get_parameter.assert_called_once_with(
                Name="prod/param", WithDecryption=True
            )

    def test_resolve_ssm_error_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._aws_ssm import AwsSsmProvider

        with patch("boto3.client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client_fn.return_value = mock_client
            mock_client.get_parameter.side_effect = Exception("ParameterNotFound")
            p = AwsSsmProvider(config)
            with pytest.raises(SecretsResolutionError, match="ParameterNotFound"):
                p.resolve("aws-ssm:///prod/db/password")


# ---------------------------------------------------------------------------
# Azure Key Vault
# ---------------------------------------------------------------------------


class TestAzureKeyVaultProvider:
    @pytest.fixture()
    def config(self) -> SecretsConfig:
        return SecretsConfig()

    def test_scheme(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        assert AzureKeyVaultProvider(config).scheme == "azure-keyvault"

    def test_is_available(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        assert AzureKeyVaultProvider(config).is_available() is True

    def test_resolve_secret(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        with (
            patch("azure.keyvault.secrets.SecretClient") as mock_client_cls,
            patch("azure.identity.DefaultAzureCredential"),
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_secret = MagicMock()
            mock_secret.value = "azure-db-secret"
            mock_client.get_secret.return_value = mock_secret

            p = AzureKeyVaultProvider(config)
            result = p.resolve("azure-keyvault://myvault.vault.azure.net/secrets/db-password")

        assert result == "azure-db-secret"
        mock_client_cls.assert_called_once_with(
            vault_url="https://myvault.vault.azure.net",
            credential=mock_client_cls.call_args[1]["credential"],
        )
        mock_client.get_secret.assert_called_once_with("db-password", version=None)

    def test_resolve_secret_with_version(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        with (
            patch("azure.keyvault.secrets.SecretClient") as mock_client_cls,
            patch("azure.identity.DefaultAzureCredential"),
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_secret = MagicMock()
            mock_secret.value = "azure-versioned-secret"
            mock_client.get_secret.return_value = mock_secret

            p = AzureKeyVaultProvider(config)
            result = p.resolve(
                "azure-keyvault://myvault.vault.azure.net/secrets/db-password/abc123"
            )

        assert result == "azure-versioned-secret"
        mock_client.get_secret.assert_called_once_with("db-password", version="abc123")

    def test_resolve_null_value_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        with (
            patch("azure.keyvault.secrets.SecretClient") as mock_client_cls,
            patch("azure.identity.DefaultAzureCredential"),
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_secret = MagicMock()
            mock_secret.value = None  # disabled or deleted secret
            mock_client.get_secret.return_value = mock_secret

            p = AzureKeyVaultProvider(config)
            with pytest.raises(SecretsResolutionError, match="no value"):
                p.resolve("azure-keyvault://myvault.vault.azure.net/secrets/db-password")

    def test_resolve_invalid_uri_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        p = AzureKeyVaultProvider(config)
        with pytest.raises(SecretsResolutionError, match="azure-keyvault"):
            # Missing /secrets/ segment
            p.resolve("azure-keyvault://myvault.vault.azure.net/db-password")

    def test_resolve_azure_error_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        with (
            patch("azure.keyvault.secrets.SecretClient") as mock_client_cls,
            patch("azure.identity.DefaultAzureCredential"),
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.get_secret.side_effect = Exception("SecretNotFound")

            p = AzureKeyVaultProvider(config)
            with pytest.raises(SecretsResolutionError, match="SecretNotFound"):
                p.resolve("azure-keyvault://myvault.vault.azure.net/secrets/db-password")

    def test_resolve_empty_host_uses_configured_vault_name(self) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        cfg = SecretsConfig(azure_vault_name="myvault")
        with (
            patch("azure.keyvault.secrets.SecretClient") as mock_client_cls,
            patch("azure.identity.DefaultAzureCredential"),
        ):
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_secret = MagicMock()
            mock_secret.value = "resolved-value"
            mock_client.get_secret.return_value = mock_secret

            p = AzureKeyVaultProvider(cfg)
            result = p.resolve("azure-keyvault:///secrets/db-password")

        assert result == "resolved-value"
        mock_client_cls.assert_called_once_with(
            vault_url="https://myvault.vault.azure.net",
            credential=mock_client_cls.call_args[1]["credential"],
        )

    def test_resolve_empty_host_no_vault_name_raises(self) -> None:
        from config.secrets.providers._azure_keyvault import AzureKeyVaultProvider

        p = AzureKeyVaultProvider(SecretsConfig())
        with pytest.raises(SecretsResolutionError, match="vault_name"):
            p.resolve("azure-keyvault:///secrets/db-password")


# ---------------------------------------------------------------------------
# GCP Secret Manager
# ---------------------------------------------------------------------------


class TestGcpSecretsProvider:
    @pytest.fixture()
    def config(self) -> SecretsConfig:
        return SecretsConfig(gcp_project_id="my-project")

    def test_scheme(self, config: SecretsConfig) -> None:
        from config.secrets.providers._gcp_secrets import GcpSecretsProvider

        assert GcpSecretsProvider(config).scheme == "gcp-secrets"

    def test_is_available(self, config: SecretsConfig) -> None:
        from config.secrets.providers._gcp_secrets import GcpSecretsProvider

        assert GcpSecretsProvider(config).is_available() is True

    def test_resolve_secret_version(self, config: SecretsConfig) -> None:
        from config.secrets.providers._gcp_secrets import GcpSecretsProvider

        with patch("google.cloud.secretmanager.SecretManagerServiceClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_response = MagicMock()
            mock_response.payload.data = b"gcp-db-secret"
            mock_client.access_secret_version.return_value = mock_response

            p = GcpSecretsProvider(config)
            result = p.resolve(
                "gcp-secrets://projects/my-project/secrets/db-password/versions/latest"
            )

        assert result == "gcp-db-secret"
        mock_client.access_secret_version.assert_called_once_with(
            name="projects/my-project/secrets/db-password/versions/latest"
        )

    def test_resolve_gcp_error_raises(self, config: SecretsConfig) -> None:
        from config.secrets.providers._gcp_secrets import GcpSecretsProvider

        with patch("google.cloud.secretmanager.SecretManagerServiceClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client
            mock_client.access_secret_version.side_effect = Exception("PermissionDenied")

            p = GcpSecretsProvider(config)
            with pytest.raises(SecretsResolutionError, match="PermissionDenied"):
                p.resolve("gcp-secrets://projects/my-project/secrets/db-password/versions/latest")
