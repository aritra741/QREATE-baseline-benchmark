#!/bin/bash
# WDIRS Setup Script — HPC variant.
#
# Differences from setup.sh (which assumes a laptop with brew/apt + sudo):
#   - No sudo, no system package manager: everything goes through `module load`
#     (if your cluster uses Lmod/Environment Modules) or user-space installs.
#   - Uses Python's built-in SQLite support; no database service is required.
#   - Checks Ollama without trying to install it via a system package manager.
#   - Assumes pip install needs network access, which many clusters only allow
#     from the login node, not compute nodes — run this script on the login
#     node, then submit the actual WDIRS job (sbatch/srun) separately.
#
# Usage (from systems/WDIRS/):
#   module load python/3.11 2>/dev/null || true   # adjust to your cluster's module name
#   bash setup_hpc.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo "=================================="
echo "WDIRS Setup (HPC)"
echo "=================================="

# --- [1/6] Python -----------------------------------------------------------
echo -e "\n${YELLOW}[1/6] Checking Python...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}python3 not found on PATH.${NC}"
    echo "Try: module avail python   then   module load python/<version>"
    exit 1
fi
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"
if ! python3 -c 'import sys; exit(0 if sys.version_info >= (3, 9) else 1)'; then
    echo -e "${RED}Error: Python 3.9+ required. Load a newer module.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python OK${NC}"

# --- [2/6] SQLite -----------------------------------------------------------
echo -e "\n${YELLOW}[2/6] Checking Python SQLite support...${NC}"
if python3 -c 'import sqlite3; print(sqlite3.sqlite_version)' >/dev/null 2>&1; then
    sqlite_version=$(python3 -c 'import sqlite3; print(sqlite3.sqlite_version)')
    echo -e "${GREEN}✓ Python SQLite available: ${sqlite_version}${NC}"
else
    echo -e "${RED}Python was built without sqlite3 support.${NC}"
    echo "Load a different Python module before creating the virtual environment."
    exit 1
fi

# --- [3/6] Ollama (check only) ----------------------------------------------
echo -e "\n${YELLOW}[3/6] Checking Ollama...${NC}"
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}✓ ollama found${NC}"
    if ollama list 2>/dev/null | grep -q "qwen2.5:7b-instruct"; then
        echo -e "${GREEN}✓ qwen2.5:7b-instruct already pulled${NC}"
    else
        echo -e "${YELLOW}Model not pulled yet. If this node has internet:${NC}"
        echo "    ollama pull qwen2.5:7b-instruct"
        echo -e "${YELLOW}If compute nodes are offline, pull on the login node, then either:${NC}"
        echo "    - share \$OLLAMA_MODELS / ~/.ollama across nodes (shared filesystem), or"
        echo "    - rsync the pulled model directory to the compute node before your job runs"
    fi
else
    echo -e "${YELLOW}ollama not found on PATH.${NC}"
    echo "  No-sudo install (user-space binary):"
    echo "    curl -fsSL https://ollama.com/download/ollama-linux-amd64.tgz -o /tmp/ollama.tgz"
    echo "    mkdir -p \$HOME/.local/ollama && tar -xzf /tmp/ollama.tgz -C \$HOME/.local/ollama"
    echo "    export PATH=\"\$HOME/.local/ollama/bin:\$PATH\"   # add to ~/.bashrc too"
    echo "  Then start the server yourself (no systemd on most HPC nodes):"
    echo "    nohup ollama serve > \$HOME/ollama.log 2>&1 &"
fi

# --- [4/6] Virtual environment ----------------------------------------------
echo -e "\n${YELLOW}[4/6] Creating virtual environment...${NC}"
if [ -d "venv" ]; then
    echo "venv/ already exists here — leaving it in place."
else
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created at $(pwd)/venv${NC}"
fi

source venv/bin/activate
echo -e "${GREEN}✓ venv activated: $(which python)${NC}"

# --- [5/6] Dependencies -------------------------------------------------------
echo -e "\n${YELLOW}[5/6] Installing Python dependencies...${NC}"
pip install --upgrade pip
# --prefer-binary avoids compiling heavy packages (torch deps, faiss) from
# source on nodes without a full build toolchain.
pip install --prefer-binary -r requirements.txt
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo -e "\n${YELLOW}[5b/6] Downloading spaCy model...${NC}"
python -m spacy download en_core_web_sm
echo -e "${GREEN}✓ spaCy model downloaded${NC}"

# --- [6/6] Directories --------------------------------------------------------
echo -e "\n${YELLOW}[6/6] Creating working directories...${NC}"
mkdir -p .cache .databases .indexes .sieves
echo -e "${GREEN}✓ Directories created${NC}"

echo -e "\n${GREEN}=================================="
echo "HPC setup complete."
echo "==================================${NC}"
echo ""
echo "Reminders before running diagnostics/run_config_grid.py on this cluster:"
echo "  1. source venv/bin/activate   (do this in every new shell/job script)"
echo "  2. Ensure Ollama is serving qwen2.5:7b-instruct -- check with: ollama list"
echo "  3. If submitting via SLURM, put steps 1-2 plus the python invocation"
echo "     inside your sbatch script; pip/ollama-pull network access usually"
echo "     only works from the login node, so do the install there first,"
echo "     THEN sbatch the actual grid run."
echo "  4. Example job:"
echo "       cd systems/WDIRS && source venv/bin/activate"
echo "       python diagnostics/run_config_grid.py --dataset Player \\"
echo "           --query-subdirs Filter Agg Join --token-budget 10846866 \\"
echo "           --out ../../results/spp_config_grid_Player"
