#!/bin/bash
# Installation script for quest requirements with blis build workaround
# This script sets compiler flags to suppress warnings during blis compilation

set -e

echo "Installing quest requirements with blis build workaround..."

# Set compiler flags to suppress unused function warnings
export CFLAGS="-Wno-unused-function -Wno-error=unused-function"
export CPPFLAGS="-Wno-unused-function -Wno-error=unused-function"

# Try to install with binary wheels first (but allow source builds if needed)
echo "Attempting to install packages..."
echo "Note: Some packages may need to build from source (e.g., blis)"
echo "Compiler warnings will be suppressed during build..."
echo ""
echo "Note: PyTorch is installed from PyPI (CPU version)."
echo "For CUDA support, install PyTorch separately after this completes:"
echo "  pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
echo ""

# Install with source builds allowed, but prefer binary wheels
pip install --prefer-binary -r requirements.txt

echo ""
echo "Installation complete!"
echo ""
echo "If you encountered errors, you may need to:"
echo "1. Install build dependencies: sudo apt-get install build-essential python3-dev"
echo "2. Check the error messages above for specific package issues"
echo "3. For CUDA-enabled PyTorch, install separately (see note above)"

