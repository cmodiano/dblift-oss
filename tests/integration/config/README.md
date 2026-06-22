# Configuration Integration Tests

## Purpose

This directory contains integration tests specifically for the configuration system, testing:
- Configuration file loading and parsing
- Environment variable loading and precedence
- Native URL parsing for all supported databases
- Configuration validation and error handling
- Extra parameters in native connection strings

## Why Separate?

These tests focus on the **configuration system itself**, which is different from:
- **Command tests** (`tests/integration/commands/`) - Test CLI commands
- **Feature tests** (`tests/integration/features/`) - Test migration features
- **Parser tests** (`tests/integration/parsers/`) - Test SQL parsing

## Files

### `test_config_integration.py`
Tests for the `DbliftConfig` and database configuration classes:
- Loading from YAML files
- Loading from environment variables
- Precedence rules (CLI args > env vars > config file)
- Native URL parsing (all databases)
- Configuration validation
- Extra parameters (SSL, application name, etc.)
- Round-trip serialization

## Running These Tests

```bash
# Run all config tests
python -m pytest tests/integration/config/ -v

# Run specific test
python -m pytest tests/integration/config/test_config_integration.py::TestConfigDatabaseIntegration::test_native_url_parsing -v
```

## Relationship to New Test Structure

The new integration test structure (commands/, features/, parsers/, etc.) uses the configuration system but doesn't explicitly test its edge cases. These tests fill that gap by:

1. **Testing config loading edge cases** - The new tests use `create_config()` helper which assumes config works
2. **Testing native URL parsing** - Complex parsing for 5+ database types needs dedicated tests
3. **Testing validation** - Ensures bad configs are caught early
4. **Testing precedence** - Critical for production deployments (env vars override files)

## Status

✅ **KEPT** - These tests provide value not covered by the new test structure

They should remain as they test a different concern (configuration system) rather than the migration workflow.
