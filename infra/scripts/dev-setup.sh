#!/usr/bin/env bash
# RayOlly Developer Setup Script
# Run once after cloning: ./infra/scripts/dev-setup.sh

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     RayOlly Developer Environment Setup  ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
echo ""

# --- Check prerequisites ---
echo -e "${YELLOW}[1/7] Checking prerequisites...${NC}"

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${RED}  ✗ $1 not found. Please install it first.${NC}"
        exit 1
    fi
    echo -e "${GREEN}  ✓ $1 found${NC}"
}

check_cmd docker
check_cmd python3
check_cmd node
check_cmd npm

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)

if (( $(echo "$PYTHON_VERSION < 3.12" | bc -l) )); then
    echo -e "${RED}  ✗ Python 3.12+ required (found $PYTHON_VERSION)${NC}"
    exit 1
fi
if (( NODE_VERSION < 22 )); then
    echo -e "${YELLOW}  ⚠ Node 22+ recommended (found $NODE_VERSION)${NC}"
fi

# --- Python virtual environment ---
echo -e "\n${YELLOW}[2/7] Setting up Python virtual environment...${NC}"
cd backend
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}  ✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}  ✓ Virtual environment already exists${NC}"
fi

source .venv/bin/activate
pip install -e ".[dev]" --quiet 2>/dev/null
echo -e "${GREEN}  ✓ Python dependencies installed${NC}"
cd ..

# --- Frontend dependencies ---
echo -e "\n${YELLOW}[3/7] Installing frontend dependencies...${NC}"
cd frontend
npm install --silent 2>/dev/null
echo -e "${GREEN}  ✓ Node modules installed${NC}"
cd ..

# --- Environment file ---
echo -e "\n${YELLOW}[4/7] Setting up environment...${NC}"
if [ ! -f "backend/.env" ]; then
    cp backend/.env.example backend/.env
    echo -e "${GREEN}  ✓ .env file created from .env.example${NC}"
    echo -e "${YELLOW}    → Edit backend/.env to add your RAYOLLY_AI_ANTHROPIC_API_KEY${NC}"
else
    echo -e "${GREEN}  ✓ .env file already exists${NC}"
fi

# --- Git hooks ---
echo -e "\n${YELLOW}[5/7] Setting up git hooks...${NC}"
if command -v pre-commit &> /dev/null; then
    pre-commit install --install-hooks 2>/dev/null
    echo -e "${GREEN}  ✓ pre-commit hooks installed${NC}"
else
    echo -e "${GREEN}  ✓ Git hooks already in .git/hooks/${NC}"
fi

# --- Start infrastructure ---
echo -e "\n${YELLOW}[6/7] Starting infrastructure services...${NC}"
make dev
echo -e "${GREEN}  ✓ Docker services started${NC}"

# --- Initialize database ---
echo -e "\n${YELLOW}[7/7] Waiting for ClickHouse and initializing schemas...${NC}"
sleep 5  # Wait for ClickHouse to be ready
make init-db 2>/dev/null && echo -e "${GREEN}  ✓ ClickHouse schemas created${NC}" || echo -e "${YELLOW}  ⚠ Schema init deferred (ClickHouse may still be starting)${NC}"

# --- Done ---
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║     Setup complete! Next steps:          ║${NC}"
echo -e "${GREEN}╠══════════════════════════════════════════╣${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║  1. make api     → Backend on :8080      ║${NC}"
echo -e "${GREEN}║  2. make web     → Frontend on :3000     ║${NC}"
echo -e "${GREEN}║  3. make test    → Run tests             ║${NC}"
echo -e "${GREEN}║  4. make help    → All commands          ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}║  API docs: http://localhost:8080/docs    ║${NC}"
echo -e "${GREEN}║  Dashboard: http://localhost:3000        ║${NC}"
echo -e "${GREEN}║                                          ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════╝${NC}"
