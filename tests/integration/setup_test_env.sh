#!/bin/bash
# Script to set up the testing environment for dblift integration tests

# Detect OS and architecture
OS=$(uname -s)
ARCH=$(uname -m)

# Set environment variables based on platform
if [ "$OS" == "Darwin" ]; then
    echo "Detected macOS development environment"
    
    # Check if using Colima
    if docker context inspect 2>&1 | grep -q "colima"; then
        echo "Detected Colima as Docker provider"
        export DOCKER_PROVIDER="colima"
        
        # Special handling for ARM macs (M1/M2/M3)
        if [ "$ARCH" == "arm64" ]; then
            echo "Detected Apple Silicon (ARM architecture)"
            export MYSQL_PLATFORM="linux/amd64"
            export MYSQL_MEM_LIMIT="1g"
            echo "Configured MySQL for ARM emulation with memory limit"
        fi
    else
        echo "Docker Desktop detected"
        export DOCKER_PROVIDER="docker-desktop"
    fi
    
    echo "NOTE: DB2 is not supported on macOS and will be skipped"
    # Remove DB2 service from docker-compose if on macOS
    TEMP_FILE=$(mktemp)
    sed '/^  db2:/,/^    # healthcheck/d' docker-compose.yml > "$TEMP_FILE"
    mv "$TEMP_FILE" docker-compose.yml
else
    echo "Detected $(uname -s) operating system"
    export DOCKER_PROVIDER="default"
fi

# Ask which databases to start
echo ""
echo "Which databases would you like to start? (default: all available)"
echo "1) All available databases"
echo "2) Only SQL Server"
echo "3) Only Oracle"
echo "4) Only MySQL"
echo "5) Only PostgreSQL"
echo "6) SQL Server and Oracle (recommended for CI)"
echo "7) Custom selection"

read -p "Enter your choice (1-7): " DB_CHOICE

case $DB_CHOICE in
    2)
        DATABASES="sqlserver"
        ;;
    3)
        DATABASES="oracle"
        ;;
    4)
        DATABASES="mysql"
        ;;
    5)
        DATABASES="postgresql"
        ;;
    6)
        DATABASES="sqlserver oracle"
        ;;
    7)
        echo "Enter database names separated by spaces (sqlserver oracle mysql postgresql db2):"
        read -p "> " DATABASES
        ;;
    *)
        # Default is all available
        if [ "$OS" == "Darwin" ]; then
            DATABASES="sqlserver oracle mysql postgresql"
        else
            DATABASES="sqlserver oracle mysql postgresql db2"
        fi
        ;;
esac

# Start selected containers
echo "Starting database containers: $DATABASES"
echo "This may take a few minutes..."

for DB in $DATABASES; do
    echo "Starting $DB..."
    docker-compose up -d $DB
done

# Wait for containers to be healthy
echo "Waiting for containers to be ready..."
MAX_WAIT=300  # 5 minutes maximum wait time
WAIT_INTERVAL=10
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    # Check selected containers
    READY=true
    
    for DB in $DATABASES; do
        CONTAINER=$(docker-compose ps -q $DB)
        if [ -z "$CONTAINER" ]; then
            echo "$DB container not found"
            continue
        fi
        
        # Get container health status
        HEALTH=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null)
        NAME=$(docker inspect --format='{{.Name}}' "$CONTAINER" | sed 's/^\///')
        
        # If health check is not configured or container doesn't support it
        if [ -z "$HEALTH" ] || [ "$HEALTH" == "<nil>" ]; then
            # Check if container is running
            STATUS=$(docker inspect --format='{{.State.Status}}' "$CONTAINER")
            if [ "$STATUS" == "running" ]; then
                echo "$NAME is running (no health check)"
            else
                echo "$NAME is not ready (status: $STATUS)"
                READY=false
            fi
        else
            # Health check exists
            if [ "$HEALTH" == "healthy" ]; then
                echo "$NAME is healthy"
            else
                echo "$NAME is not ready (health: $HEALTH)"
                READY=false
            fi
        fi
    done
    
    # If all containers are ready, break out of the loop
    if [ "$READY" == "true" ]; then
        echo "All containers are ready!"
        break
    fi
    
    # Wait and increment elapsed time
    sleep $WAIT_INTERVAL
    ELAPSED=$((ELAPSED + WAIT_INTERVAL))
    echo "Still waiting for containers... (${ELAPSED}s elapsed)"
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "WARNING: Timed out waiting for containers to be ready."
    echo "Some containers may not be fully initialized. Check logs for details:"
    echo "docker-compose logs"
fi

# Extra wait time for MySQL on ARM macOS (known to need more time after "ready")
if [ "$OS" == "Darwin" ] && [ "$ARCH" == "arm64" ] && docker ps | grep -q "dblift_mysql"; then
    echo "Giving MySQL extra time to stabilize on Apple Silicon..."
    sleep 10
fi

# Update conftest.py for local testing with the selected databases
echo "Updating conftest.py to use selected databases: $DATABASES"
CONFTEST_PATH="conftest.py"

# Create array from space-separated string
read -ra DB_ARRAY <<< "$DATABASES"

# Format as Python list
PYTHON_LIST="["
for DB in "${DB_ARRAY[@]}"; do
    PYTHON_LIST+="\"$DB\", "
done
PYTHON_LIST="${PYTHON_LIST%, }]"  # Remove trailing comma and space

# Replace SUPPORTED_DBS line
sed -i.bak "s/^SUPPORTED_DBS = .*/SUPPORTED_DBS = $PYTHON_LIST/" "$CONFTEST_PATH"
rm -f "${CONFTEST_PATH}.bak"  # Clean up backup file

echo "Environment setup complete. Ready to run integration tests."
echo ""
echo "To run all tests:"
echo "  python -m pytest tests/integration/"
echo ""
echo "To run tests for specific databases:"
for DB in $DATABASES; do
    echo "  python -m pytest tests/integration/db/test_${DB}_integration.py"
done
echo ""
echo "To clean up: docker-compose down"