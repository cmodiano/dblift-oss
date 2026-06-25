# Integration Tests

This directory contains integration tests that verify how different components of DBLift work together. Unlike unit tests, these tests focus on component interactions and real-world scenarios.

## Directory Structure

```
integration/
├── cli/          # CLI integration tests
├── config/       # Configuration integration tests
├── core/         # Core functionality integration tests
├── db/           # Database integration tests
├── docker-compose.yml  # Database container definitions
└── conftest.py   # Shared test fixtures
```

## Test Categories

### CLI Integration Tests
- Command execution flow
- User input/output handling
- Error reporting
- Command-line argument processing

### Configuration Integration Tests
- Configuration loading from multiple sources
- Configuration precedence
- Database connection with configuration
- Environment variable handling
- File-based configuration
- Mixed configuration sources

### Core Integration Tests
- Migration execution
- Transaction management
- Error handling and recovery
- Component interaction

### Database Integration Tests
- Database connections
- SQL execution
- Transaction handling
- Database-specific features

## Test Setup

### Prerequisites
- Python 3.11+
- pytest
- Docker
- Docker Compose
- Required database drivers

### Database Containers

The tests use Docker containers to provide real database instances:

```yaml
services:
  oracle:     # Oracle XE
  postgres:   # PostgreSQL 15
  mysql:      # MySQL 8.0
  sqlserver:  # SQL Server 2022
  db2:        # DB2 11.5
```

To start the containers:
```bash
docker-compose up -d
```

To stop the containers:
```bash
docker-compose down
```

### Configuration
1. Create test configuration files in `tests/integration/config/test_data/`
2. Set up test environment variables
3. Configure test database connections

### Running Tests

To run all integration tests:
```bash
pytest tests/integration/
```

To run specific category:
```bash
pytest tests/integration/config/
```

To run specific test:
```bash
pytest tests/integration/config/test_config_integration.py
```

## Test Fixtures

Integration tests use fixtures to:
- Set up test environment
- Create test data
- Manage database connections
- Clean up resources

### Database Container Fixtures

```python
@pytest.fixture(scope="session")
def db_containers(docker_client):
    """Start and manage database containers."""
    # Start containers
    docker_client.containers.run(
        "docker/compose:latest",
        command="up -d",
        volumes={...},
        working_dir='/workdir',
        detach=True
    )
    
    # Wait for containers to be healthy
    for service in ['oracle', 'postgres', 'mysql', 'sqlserver', 'db2']:
        container = docker_client.containers.get(f"{compose_dir.name}_{service}_1")
        while True:
            health = container.attrs['State']['Health']['Status']
            if health == 'healthy':
                break
            elif health == 'unhealthy':
                raise Exception(f"Container {service} is unhealthy")
            time.sleep(1)
    
    yield
    
    # Stop containers
    docker_client.containers.run(
        "docker/compose:latest",
        command="down",
        volumes={...},
        working_dir='/workdir'
    )
```

### Database Configuration Fixtures

```python
@pytest.fixture(scope="session")
def db_configs() -> Dict[str, Dict[str, Any]]:
    """Get database configurations for test containers."""
    return {
        "oracle": {...},
        "postgres": {...},
        "mysql": {...},
        "sqlserver": {...},
        "db2": {...}
    }
```

## Best Practices

1. **Test Independence**
   - Each test should be independent
   - Tests should not rely on each other
   - Clean up after each test

2. **Resource Management**
   - Use fixtures for setup and cleanup
   - Properly close database connections
   - Clean up temporary files
   - Stop containers after tests

3. **Error Handling**
   - Test both success and failure scenarios
   - Verify error messages
   - Check error recovery
   - Handle container health checks

4. **Configuration**
   - Use test-specific configuration
   - Don't rely on production settings
   - Document configuration requirements
   - Use container-specific settings

5. **Database Testing**
   - Use test databases in containers
   - Clean up test data
   - Handle database-specific features
   - Test all supported databases

## Example Test

```python
@pytest.mark.parametrize("db_type", ["oracle", "postgres", "mysql", "sqlserver", "db2"])
def test_all_database_types(self, db_type, db_configs, db_containers):
    """Test connection to all supported database types."""
    # Create configuration for the database type
    config = DbliftConfig.from_dict({
        "database": db_configs[db_type]
    })
    
    # Get database provider
    db_provider = get_db_provider(config.database)
    
    # Test connection
    with db_provider.connect() as conn:
        assert conn is not None
        # Test basic query
        with conn.cursor() as cursor:
            if db_type == "oracle":
                cursor.execute("SELECT 1 FROM DUAL")
            elif db_type == "postgres":
                cursor.execute("SELECT 1")
            elif db_type == "mysql":
                cursor.execute("SELECT 1")
            elif db_type == "sqlserver":
                cursor.execute("SELECT 1")
            elif db_type == "db2":
                cursor.execute("SELECT 1 FROM SYSIBM.SYSDUMMY1")
            result = cursor.fetchone()
            assert result[0] == 1
```

## Notes

- Integration tests are slower than unit tests
- They require more setup and cleanup
- They need Docker and database containers
- They test real-world scenarios
- They verify component interactions
- They help catch integration issues
- They complement unit tests
- They provide end-to-end testing
- They test all supported databases
- They verify container health 