#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Preserve the existing local configuration bootstrap behavior. The generated
# file remains ignored; only a safe example template may be copied.
if [ ! -f .env ] && [ -f .env.example ]; then
  echo "→ Copying .env.example to ignored local .env"
  cp .env.example .env
fi

require_python_3_12() {
  local detected_major_minor="$1"
  local label="$2"
  echo "❌ $label uses Python $detected_major_minor, but Atlas requires Python 3.12."
  echo "   Install Python 3.12, then rerun: bash scripts/bootstrap.sh"
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
  echo "❌ Could not find Python 3.12. Install it, then rerun: bash scripts/bootstrap.sh"
  exit 1
fi
PY_MAJOR_MINOR="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
if [ "$PY_MAJOR_MINOR" != "3.12" ]; then
  require_python_3_12 "$PY_MAJOR_MINOR" "$PYTHON_BIN"
fi

RULES_VENV_DIR="$PROJECT_ROOT/.venv-rules"
FINLYNQ_VENV_DIR="$PROJECT_ROOT/.venv-finlynq"
RULES_VENV_PY="$RULES_VENV_DIR/bin/python"
FINLYNQ_VENV_PY="$FINLYNQ_VENV_DIR/bin/python"

ensure_venv() {
  local venv_dir="$1"
  local venv_py="$2"
  local label="$3"
  if [ -d "$venv_dir" ]; then
    local venv_mm
    venv_mm="$($venv_py -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || echo unknown)"
    if [ "$venv_mm" != "3.12" ]; then
      echo "❌ $label environment at $venv_dir uses Python $venv_mm; recreate it with Python 3.12."
      exit 1
    fi
    echo "→ Reusing $label environment: $venv_dir (Python $venv_mm)"
  else
    echo "→ Creating $label environment: $venv_dir (Python 3.12)"
    "$PYTHON_BIN" -m venv "$venv_dir"
  fi
}

echo "========================================="
echo "🐍 Atlas isolated Python environment setup"
echo "========================================="
ensure_venv "$RULES_VENV_DIR" "$RULES_VENV_PY" "Rules Service"
ensure_venv "$FINLYNQ_VENV_DIR" "$FINLYNQ_VENV_PY" "Finlynq"

if [ "${UPGRADE_PACKAGING_TOOLS:-0}" = "1" ]; then
  echo "→ Upgrading packaging tools in both isolated environments"
  "$RULES_VENV_PY" -m pip install --upgrade pip wheel setuptools
  "$FINLYNQ_VENV_PY" -m pip install --upgrade pip wheel setuptools
else
  echo "→ Keeping installed packaging tools (set UPGRADE_PACKAGING_TOOLS=1 to upgrade them)"
fi

echo "→ Installing Rules Service pins only into .venv-rules"
"$RULES_VENV_PY" -m pip install -r services/rules-service/requirements.txt
echo "→ Installing Finlynq pins only into .venv-finlynq"
"$FINLYNQ_VENV_PY" -m pip install -r services/finlynq/requirements.txt

if [ "${RUN_SERVICE_TESTS:-1}" = "1" ]; then
  echo "→ Running Rules Service tests with .venv-rules"
  (cd services/rules-service && "$RULES_VENV_PY" -m pytest -q)
  echo "→ Running Finlynq tests with .venv-finlynq"
  (cd services/finlynq && "$FINLYNQ_VENV_PY" -m pytest -q)
else
  echo "→ RUN_SERVICE_TESTS=0: skipping service tests"
fi

echo "✅ Atlas environments are ready."
echo "   Rules Service: .venv-rules/bin/python"
echo "   Finlynq:       .venv-finlynq/bin/python"
