"""Static and fast-fail tests for the Atlas local-port stop wrapper."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


STOP_SH = Path(__file__).resolve().parent.parent / "stop.sh"


def test_stop_sh_is_valid_bash() -> None:
    subprocess.run(["bash", "-n", str(STOP_SH)], check=True, capture_output=True, text=True)


def test_stop_sh_uses_the_same_atlas_port_profile_as_startup() -> None:
    text = STOP_SH.read_text(encoding="utf-8")
    assert 'ATLAS_UI_PORT="${ATLAS_UI_PORT-3333}"' in text
    assert 'ATLAS_RULES_PORT="${ATLAS_RULES_PORT-8888}"' in text
    assert 'ATLAS_FINLYNQ_PORT="${ATLAS_FINLYNQ_PORT-8889}"' in text
    assert 'port_state "$ATLAS_FINLYNQ_PORT"' in text
    assert 'port_state "$ATLAS_RULES_PORT"' in text
    assert 'port_state "$ATLAS_UI_PORT"' in text
    assert 'lsof -a -p "$pid" -d cwd -Fn' in text
    assert '*"-m uvicorn app.main:app"*|*next-server*|"next dev"*) return 0' in text
    for variable in ("ATLAS_UI_PORT", "ATLAS_RULES_PORT", "ATLAS_FINLYNQ_PORT"):
        assert text.count(f'"${variable}"') >= 2, variable


@pytest.mark.parametrize(
    "name,value",
    [("ATLAS_UI_PORT", ""), ("ATLAS_RULES_PORT", "abc"), ("ATLAS_FINLYNQ_PORT", "22")],
)
def test_stop_sh_rejects_invalid_port_values_before_reading_pidfiles(name: str, value: str) -> None:
    result = subprocess.run(
        ["bash", str(STOP_SH)],
        env={**os.environ, name: value},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert name in result.stdout
    assert "non-privileged numeric TCP port" in result.stdout
