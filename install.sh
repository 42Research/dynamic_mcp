#!/bin/bash
# Installation script for Dynamic MCP Server

set -e

echo "Installing Dynamic MCP Server..."

# Check if Python 3.10+ is available
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
REQUIRED_VERSION="3.10"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo "Error: Python $REQUIRED_VERSION or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "dynamic_mcp_env" ]; then
    echo "Creating virtual environment..."
    python3 -m venv dynamic_mcp_env
fi

# Activate virtual environment
echo "Activating virtual environment..."
source dynamic_mcp_env/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Install package in development mode
echo "Installing Dynamic MCP Server..."
pip install -e .

echo "Installation completed successfully!"
echo ""
echo "To run the server:"
echo "  source dynamic_mcp_env/bin/activate"
echo "  dynamic-mcp"
echo ""
echo "To run tests:"
echo "  source dynamic_mcp_env/bin/activate"
echo "  pytest"
