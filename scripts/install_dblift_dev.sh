#!/bin/bash

# Install DBLift in development mode

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install package in development mode
echo "Installing DBLift in development mode..."
pip install -e .

# Install production dependencies
echo "Installing production dependencies..."
pip install -r requirements.txt

# Install development dependencies
echo "Installing development dependencies..."
pip install -r requirements-dev.txt

echo "DBLift development environment setup complete"