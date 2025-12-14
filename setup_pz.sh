#!/bin/bash
# Setup script for Palimpzest (PZ) baseline system

set -e  # Exit on error

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PZ_DIR="$PROJECT_ROOT/systems/PZ"
VENV_DIR="$PZ_DIR/pz_venv"

echo "=========================================="
echo "Palimpzest (PZ) Setup"
echo "=========================================="
echo ""
echo "Project root: $PROJECT_ROOT"
echo "PZ directory: $PZ_DIR"
echo "Venv location: $VENV_DIR"
echo ""

# Check if venv already exists
if [ -d "$VENV_DIR" ]; then
    echo "✓ Virtual environment already exists at $VENV_DIR"
    read -p "Recreate it? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing venv..."
        rm -rf "$VENV_DIR"
    else
        echo "Skipping venv creation."
        SKIP_VENV=1
    fi
fi

# Create venv if needed
if [ "$SKIP_VENV" != "1" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
fi

# Activate venv
echo ""
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "✓ Virtual environment activated"

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel
echo "✓ pip upgraded"

# Install full Palimpzest system
echo ""
echo "Installing FULL Palimpzest system (from PZ_original/palimpzest/)..."
cd "$PZ_DIR"
if [ -d "PZ_original/palimpzest" ]; then
    echo "✓ Found PZ_original/palimpzest, installing in development mode..."
    pip install -e "PZ_original/palimpzest/"
    echo "✓ Full Palimpzest installed"
else
    echo "⚠ PZ_original/palimpzest not found, installing from PyPI as fallback..."
    pip install palimpzest>=1.3.0
    echo "✓ Palimpzest from PyPI installed"
fi

# Install additional dependencies
echo ""
echo "Installing additional dependencies..."
pip install -r requirements.txt
echo "✓ All dependencies installed"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Activate the PZ environment:"
echo "   source systems/PZ/pz_venv/bin/activate"
echo ""
echo "2. Run challenging queries with PZ:"
echo "   python run_challenging_queries.py --systems pz --query-types simple filter projection"
echo ""
echo "3. Or run with all systems:"
echo "   python run_challenging_queries.py --systems all"
echo ""
echo "Note: Ensure Ollama is running before executing queries"
echo "=========================================="

