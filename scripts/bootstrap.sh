#!/usr/bin/env bash
set -euo pipefail

echo "========================================="
echo "🚀 Starting Finance Copilot Phase 0 Setup"
echo "========================================="

# 1. Environment Management
if [ ! -f .env ]; then
    echo "-> Copying example environment variables from .env.example to .env"
    cp .env.example .env
else
    echo "-> Found existing .env file. Skipping copy."
fi

# 2. Initial Service Setup (e.g., database migration, initial data load)
# NOTE: Add specific initialization commands here if services require it (e.g., 'docker compose run --rm rules-service migrate')
echo "-> Running placeholder service setup checks..."
# Placeholder for future migrations/initialization scripts

# 3. Python local virtualenv
#    Convention: project-root .venv, Python 3.12 (matches services/rules-service/Dockerfile
#    `FROM python:3.12-slim`). Honors the project-root `.python-version` file. Never
#    `pip install` into system Python — it pollutes the host and conflicts between projects.
require_python_3_12() {
    # Hard-fail with remediation when the available interpreter cannot be used.
    local detected_major_minor="$1"
    local label="$2"
    echo "❌ $label uses Python $detected_major_minor, but this project requires 3.12."
    echo "   services/rules-service/requirements.txt pins pydantic==2.7.4 which has no"
    echo "   prebuilt macOS arm64 wheels for 3.13 or 3.14; pip will try to compile"
    echo "   pydantic-core from source (slow, requires a Rust toolchain, often fails)."
    echo ""
    echo "   Fix (macOS):   brew install python@3.12 && rm -rf .venv && bash scripts/bootstrap.sh"
    echo "   Fix (Ubuntu):  sudo apt install python3.12 python3.12-venv && rm -rf .venv && bash scripts/bootstrap.sh"
    echo "   Fix (Windows): winget install Python.Python.3.12  (or: choco install python312)"
    echo "   Fix (other):   install Python 3.12 via your manager of choice, then re-run."
    exit 1
}

PYTHON_BIN="${PYTHON_BIN:-}"
if [ -z "$PYTHON_BIN" ]; then
    for candidate in /opt/homebrew/bin/python3.12 python3.12 python3; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi
if [ -z "$PYTHON_BIN" ]; then
    echo "❌ Could not find a python3 interpreter on PATH."
    echo "   Install Python 3.12 (see remediation in CLAUDE.md → Python setup)."; exit 1
fi
PY_MAJOR_MINOR="$("$PYTHON_BIN" -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PY_MAJOR_MINOR" != "3.12" ]; then
    require_python_3_12 "$PY_MAJOR_MINOR" "$PYTHON_BIN"
fi

# .venv reuse invariant: if .venv already exists, its interpreter MUST also be 3.12.
# A previous run on 3.13/3.14 would have left a poisoned venv — refuse to reuse it
# so the contributor cannot silently end up with a broken venv via re-running this script.
if [ -d .venv ]; then
    VENV_MM="$(.venv/bin/python -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo unknown)"
    if [ "$VENV_MM" != "3.12" ]; then
        echo "❌ Existing .venv was created from Python $VENV_MM but this project requires 3.12."
        echo "   Recreate it: rm -rf .venv && bash scripts/bootstrap.sh"
        exit 1
    fi
    echo "-> Found existing .venv on Python $VENV_MM. (delete with \`rm -rf .venv\` to recreate)"
else
    echo "-> Creating .venv at project root using $PYTHON_BIN (Python $PY_MAJOR_MINOR)"
    "$PYTHON_BIN" -m venv .venv
fi
echo "-> Upgrading pip/wheel/setuptools inside .venv"
.venv/bin/python -m pip install --upgrade pip wheel setuptools
echo "-> Installing services/rules-service/requirements.txt into .venv"
.venv/bin/pip install -r services/rules-service/requirements.txt
echo "-> Installing services/finlynq/requirements.txt into .venv (parser + categorizer deps)"
# Finlynq's parser/categorizer suite depends on pdfplumber / pytesseract /
# pandas / ofxparse / openpyxl / xlrd / reportlab / Pillow. Installing
# them here prevents start.sh from re-installing on every run.
.venv/bin/pip install -r services/finlynq/requirements.txt
echo "-> Running rules-service tests (pytest discovers tests/ via pytest.ini pythonpath = .)"
# cd into rules-service so pytest auto-discovers pytest.ini and pythonpath = .
# injects the rules-service dir into sys.path; explicit --rootdir from project
# root misses this.
( cd services/rules-service && ../../.venv/bin/python -m pytest -q )
echo "-> Running finlynq tests (parser/categorizer suite; pytest.ini pythonpath = .)"
# Same trick: cd into services/finlynq so its pytest.ini injects the
# Finlynq app/ dir into sys.path for the flat `from app.main import app`
# imports used in tests/*.
( cd services/finlynq && ../../.venv/bin/python -m pytest -q )

# 4. Build and Run Services
echo ""
echo "========================================="
echo "✅ Phase 0 Setup Complete."
echo "To work locally:"
echo "  source .venv/bin/activate             # activate Python venv"
echo "  cd ui && rm -rf .next && npm run dev  # start the dashboard"
echo "To build and start all services (Docker):"
echo "  docker compose up --build"
echo "========================================="
