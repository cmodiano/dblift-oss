# Development Setup

Guide for setting up a development environment for DBLift.

## Prerequisites

- Python 3.11+
- Git

## Installation

1. **Clone the repository**:
```bash
git clone https://github.com/cmodiano/dblift.git
cd dblift
```

2. **Create a virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install the project and development dependencies**:
```bash
python -m pip install -e ".[dev]"
```

4. **Verify the CLI entry point**:
```bash
dblift --version
```

## Project Structure

```
dblift/
├── api/              # Public API client
├── cli/              # Command-line interface
├── config/           # Configuration management
├── core/             # Core migration engine
├── db/               # Database providers
├── tests/            # Test suite
└── docs/             # Documentation
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_migration_executor.py
```

## Code Quality

```bash
# Format code
black .

# Check types
mypy .

# Lint
flake8 .

# Sort imports
isort .
```

## Building Documentation

```bash
# Install documentation dependencies
pip install -r requirements-docs.txt

# Build documentation
mkdocs build

# Serve documentation locally
mkdocs serve
```

## Next Steps

- Read the [Testing Guide](testing.md)
- Check [Contributing Guidelines](contributing.md)
- See [Adding Database Support](adding-database-support.md)
