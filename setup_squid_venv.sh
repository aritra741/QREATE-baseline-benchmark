#!/bin/bash
# Setup script for SQUiD virtual environment
# This creates a venv with all dependencies needed for:
#   - preprocess_squid_data.py
#   - run_challenging_queries.py (with SQUiD system)

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_NAME="venv_squid"
VENV_PATH="$SCRIPT_DIR/$VENV_NAME"

echo "=========================================="
echo "SQUiD Virtual Environment Setup"
echo "=========================================="
echo ""

# Check Python version
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Create virtual environment
if [ -d "$VENV_PATH" ]; then
    echo "Virtual environment already exists at: $VENV_PATH"
    read -p "Remove and recreate? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "Removing existing virtual environment..."
        rm -rf "$VENV_PATH"
    else
        echo "Using existing virtual environment."
        echo ""
        echo "To activate:"
        echo "  source $VENV_PATH/bin/activate"
        echo ""
        echo "To install/update dependencies:"
        echo "  pip install -r requirements_squid.txt"
        exit 0
    fi
fi

echo "Creating virtual environment at: $VENV_PATH"
python3 -m venv "$VENV_PATH"

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_PATH/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip setuptools wheel

# Install requirements
echo ""
echo "Installing dependencies from requirements_squid.txt..."
pip install -r "$SCRIPT_DIR/requirements_squid.txt"

# Download spacy models
echo ""
echo "Downloading spacy language models..."
python -m spacy download en_core_web_sm || echo "Warning: Failed to download en_core_web_sm"
python -m spacy download en_core_web_md || echo "Warning: Failed to download en_core_web_md"

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Virtual environment created at: $VENV_PATH"
echo ""
echo "To activate the environment:"
echo "  source $VENV_PATH/bin/activate"
echo ""
echo "To deactivate:"
echo "  deactivate"
echo ""
echo "Next steps:"
echo "  1. Ensure Ollama is installed and running:"
echo "     - Install: https://ollama.ai"
echo "     - Pull model: ollama pull qwen2.5:7b-instruct"
echo "     - Start server: ollama serve"
echo ""
echo "  2. Run preprocessing:"
echo "     python preprocess_squid_data.py --dataset all"
echo ""
echo "  3. Run challenging queries:"
echo "     python run_challenging_queries.py --systems squid"
echo ""


