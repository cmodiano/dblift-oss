@echo off
setlocal

echo Setting up DBLift environment...

:: Create directories if they don't exist
if not exist logs mkdir logs
if not exist migrations mkdir migrations

:: Create a sample configuration file if it doesn't exist
if not exist dblift.yaml (
    echo Creating sample configuration file...
    (
        echo # DBLift Configuration
        echo.
        echo database:
        echo   type: sqlserver  # or oracle
        echo   server: localhost
        echo   port: 1433  # for SQL Server (use 1521 for Oracle)
        echo   database_name: mydatabase
        echo   schema: dbo  # for SQL Server (use your schema name for Oracle)
        echo   username: username
        echo   password: password
        echo.  
        echo migrations_dir: migrations
        echo log_format: text  # text, json, or html
        echo log_level: INFO   # DEBUG, INFO, WARNING, ERROR
    ) > dblift.yaml
    echo Sample configuration file created: dblift.yaml
)

:: Create a sample migration if migrations directory is empty
dir /b migrations 2>nul | find /v /c "" > %temp%\count
set /p count=<%temp%\count
if %count%==0 (
    echo Creating sample migration...
    (
        echo -- Sample migration script
        echo -- Create a simple table
        echo.
        echo CREATE TABLE sample_table (
        echo     id INT PRIMARY KEY,
        echo     name VARCHAR(100) NOT NULL,
        echo     created_date DATETIME DEFAULT CURRENT_TIMESTAMP
        echo );
        echo.
        echo -- Insert some initial data
        echo INSERT INTO sample_table (id, name) VALUES (1, 'Sample Data');
    ) > migrations\V1_0_0__Initial_schema.sql
    echo Sample migration created: migrations\V1_0_0__Initial_schema.sql
)

echo.
echo DBLift environment setup complete!
echo To run DBLift, use: python -m dblift [command]
echo For example: python -m dblift info --config dblift.yaml

endlocal 
