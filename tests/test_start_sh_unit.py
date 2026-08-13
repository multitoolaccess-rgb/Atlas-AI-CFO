"""Hermetic regression tests for the Atlas lifecycle shell scripts."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def run_script(script: str, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(ROOT / script), *args],
        cwd=ROOT,
        env={**os.environ, **(env or {})},
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("script", ["start.sh", "stop.sh"])
@pytest.mark.parametrize("option", ["--help", "--check"])
def test_help_and_check_are_non_mutating(script: str, option: str, tmp_path: Path) -> None:
    """These modes do not make .run or invoke lifecycle side-effect commands."""
    run_dir = ROOT / ".run"
    before = sorted(run_dir.iterdir()) if run_dir.exists() else []
    marker = tmp_path / "command-called"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("npm", "rm", "nohup", "curl", "lsof", "kill", "pgrep", "sleep"):
        path = fake_bin / command
        path.write_text(f"#!/bin/sh\ntouch {marker}\nexit 99\n")
        path.chmod(0o755)

    result = run_script(script, option, env={"PATH": f"{fake_bin}:{os.environ['PATH']}"})

    assert result.returncode == 0, result.stderr
    assert "Atlas AI CFO" in result.stdout
    assert not marker.exists()
    after = sorted(run_dir.iterdir()) if run_dir.exists() else []
    assert after == before


def test_default_and_override_ports_match_for_start_and_stop() -> None:
    default_start = run_script("start.sh", "--check")
    default_stop = run_script("stop.sh", "--check")
    override = {"ATLAS_UI_PORT": "4333", "ATLAS_RULES_PORT": "9888", "ATLAS_FINLYNQ_PORT": "9889"}
    override_start = run_script("start.sh", "--check", env=override)
    override_stop = run_script("stop.sh", "--check", env=override)

    for result in (default_start, default_stop, override_start, override_stop):
        assert result.returncode == 0, result.stderr
    assert all(port in default_start.stdout + default_stop.stdout for port in ("3333", "8888", "8889"))
    assert all(port in override_start.stdout + override_stop.stdout for port in ("4333", "9888", "9889"))


def test_lifecycle_scripts_are_atlas_branded_and_valid_bash() -> None:
    for script in ("start.sh", "stop.sh"):
        source = (ROOT / script).read_text()
        assert "Atlas AI CFO" in source
        subprocess.run(["bash", "-n", str(ROOT / script)], check=True)


def test_e2e_harness_provisions_the_live_service_dependencies() -> None:
    """The canonical browser runner must not rely on developer processes."""
    source = (ROOT / "scripts/test-e2e.sh").read_text()
    canonical_runner = (ROOT / "scripts/test.sh").read_text()

    assert 'bash "$SCRIPT_DIR/test-e2e.sh"' in canonical_runner
    assert "FINLYNQ_VENV_PY" in source
    assert "uvicorn app.main:app --host 0.0.0.0 --port 8001" in source
    assert "uvicorn app.main:app --host 0.0.0.0 --port 8000" in source
    assert "FINLYNQ_BASE_URL='http://localhost:8001'" in source
    assert source.index("start_finlynq") < source.index("start_rules")
    assert "STARTED_FINLYNQ" in source and "STARTED_RULES" in source
    assert "RULES_STARTUP_TIMEOUT_SECONDS=60" in source
    rules_start = source[source.index("start_rules()") : source.index("if curl", source.index("start_rules()"))]
    assert 'seq 1 "$RULES_STARTUP_TIMEOUT_SECONDS"' in rules_start
    assert "print_rules_log_tail" in source
    assert 'tail -n 80 "$RULES_LOG"' in source
    assert "[REDACTED]" in source
    assert 'mktemp "$E2E_TMP_DIR/atlas-ai-cfo-e2e-XXXXXX.db"' in source
    assert 'DATABASE_URL="$E2E_DATABASE_URL" "$RULES_VENV_PY" -m alembic -c alembic.ini upgrade head' in source
    assert source.index("prepare_e2e_database || exit 1") < source.index("start_finlynq()")
    assert source.count('DATABASE_URL="$E2E_DATABASE_URL"') == 3
    assert 'rm -f -- "$E2E_DB_PATH" "${E2E_DB_PATH}-wal" "${E2E_DB_PATH}-shm"' in source
    assert 'require_port_available 8001 "Finlynq" || exit 1' in source
    assert 'require_port_available 8000 "Rules Service" || exit 1' in source
    assert "lsof -nP -iTCP:" in source
    assert "command -v lsof" in source
    assert "will reuse" not in source


def _make_hermetic_atlas_root(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "atlas"
    root.mkdir()
    for script in ("start.sh", "stop.sh"):
        target = root / script
        target.write_text((ROOT / script).read_text())
        target.chmod(0o755)
    log = tmp_path / "launch.log"
    for relative, label in ((".venv-finlynq/bin/python", "finlynq"), (".venv-rules/bin/python", "rules"), ("ui/node_modules/.bin/next", "ui")):
        executable = root / relative
        executable.parent.mkdir(parents=True, exist_ok=True)
        executable.write_text(f"#!/bin/sh\nprintf '%s|%s|%s\\n' '{label}' \"$*\" \"$NEXT_PUBLIC_API_BASE_URL,$FINLYNQ_BASE_URL\" >> '{log}'\n")
        executable.chmod(0o755)
    (root / "services/rules-service").mkdir(parents=True)
    (root / "services/finlynq").mkdir(parents=True)
    return root, log


def test_start_launches_resolved_ports_and_dependent_urls_with_fake_services(tmp_path: Path) -> None:
    root, log = _make_hermetic_atlas_root(tmp_path)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "curl").write_text("#!/bin/sh\nprintf 200\n")
    (fake_bin / "lsof").write_text("#!/bin/sh\nexit 0\n")
    for command in ("curl", "lsof"):
        (fake_bin / command).chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "ATLAS_UI_PORT": "4333", "ATLAS_RULES_PORT": "9888", "ATLAS_FINLYNQ_PORT": "9889"}

    result = subprocess.run(["bash", str(root / "start.sh")], cwd=root, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    launches = log.read_text()
    assert "finlynq|" in launches and "--port 9889" in launches
    assert "rules|" in launches and "--port 9888" in launches
    assert "ui|dev -p 4333 -H 127.0.0.1" in launches
    assert "http://127.0.0.1:9889" in launches
    assert "http://127.0.0.1:9888" in launches
    assert "http://127.0.0.1:4333" in result.stdout
    assert "rules env:" in result.stdout
    start_source = (root / "start.sh").read_text().lower()
    assert "-m alembic" not in start_source
    assert "upgrade head" not in start_source


def test_unrelated_listener_and_pidfile_are_never_signaled(tmp_path: Path) -> None:
    """A generic process on an Atlas port cannot become eligible by name alone."""
    root, _ = _make_hermetic_atlas_root(tmp_path)
    (root / ".run").mkdir()
    for pidfile in ("fq.pid", "be.pid", "fe.pid"):
        (root / ".run" / pidfile).write_text("424242")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    (fake_bin / "lsof").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in *'-d cwd'*) printf 'p424242\\nfcwd\\nn/unrelated-project\\n';; *) printf '424242\\n';; esac\n"
    )
    (fake_bin / "lsof").chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "STOP_GRACE_SECONDS": "0"}
    result = subprocess.run(["bash", str(root / "stop.sh")], cwd=root, env=env, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr
    assert "refusing to signal" in result.stdout
    assert "unrelated listener" in result.stdout


def test_only_verified_atlas_pid_tree_is_signaled_with_fake_process_commands(tmp_path: Path) -> None:
    """Snapshotting signals Atlas child-before-parent and excludes unrelated PIDs."""
    root, _ = _make_hermetic_atlas_root(tmp_path)
    (root / ".run").mkdir()
    (root / ".run" / "fq.pid").write_text("100")
    (root / ".run" / "be.pid").write_text("")
    (root / ".run" / "fe.pid").write_text("200")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    signal_log = tmp_path / "signals.log"
    trace_log = tmp_path / "trace.log"
    (fake_bin / "lsof").write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = -a ]; then\n"
        "  case \"$3\" in\n"
        "    100|101) printf 'p%s\\nfcwd\\nn%s/services/rules-service\\n' \"$3\" \"$ATLAS_TEST_ROOT\";;\n"
        "    *) printf 'p%s\\nfcwd\\nn/unrelated-project\\n' \"$3\";;\n"
        "  esac\n"
        "else case \"$*\" in *8889*) printf '100\\n';; *3333*) printf '200\\n';; esac; fi\n"
    )
    (fake_bin / "pgrep").write_text(
        "#!/bin/sh\nprintf 'pgrep %s\\n' \"$*\" >> \"$ATLAS_TEST_TRACE\"\n"
        "[ \"$2\" = 100 ] && printf '101 201\\n'\n"
    )
    (fake_bin / "kill").write_text(
        "#!/bin/sh\n"
        "[ \"$1\" = -0 ] && exit 0\n"
        "printf '%s\\n' \"$*\" >> \"$ATLAS_TEST_SIGNALS\"\n"
        "printf 'signal %s\\n' \"$*\" >> \"$ATLAS_TEST_TRACE\"\n"
    )
    # The lifecycle implementation does not need ps, but this fake ensures
    # the process model is hermetic if a future ownership check uses it.
    (fake_bin / "ps").write_text("#!/bin/sh\nexit 0\n")
    bash_env = tmp_path / "bash_env"
    bash_env.write_text('kill() { "$ATLAS_TEST_FAKE_BIN/kill" "$@"; }\n')
    for command in ("lsof", "pgrep", "kill", "ps"):
        (fake_bin / command).chmod(0o755)

    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "BASH_ENV": str(bash_env),
        "ATLAS_TEST_FAKE_BIN": str(fake_bin),
        "ATLAS_TEST_ROOT": str(root),
        "ATLAS_TEST_SIGNALS": str(signal_log),
        "ATLAS_TEST_TRACE": str(trace_log),
        "STOP_GRACE_SECONDS": "0",
    }
    result = subprocess.run(["bash", str(root / "stop.sh")], cwd=root, env=env, text=True, capture_output=True, check=False)

    assert result.returncode == 0, result.stderr
    assert signal_log.exists(), f"stdout={result.stdout}\nstderr={result.stderr}\ntrace={trace_log.read_text() if trace_log.exists() else ''}"
    signals = signal_log.read_text().splitlines()
    assert signals == ["-TERM 101", "-TERM 100", "-KILL 101", "-KILL 100"]
    assert all(signal.split()[1] in {"100", "101"} for signal in signals)
    assert all("200" not in signal and "201" not in signal for signal in signals)
    trace = trace_log.read_text().splitlines()
    assert max(index for index, event in enumerate(trace) if event.startswith("pgrep")) < min(
        index for index, event in enumerate(trace) if event.startswith("signal")
    )


def test_ownership_is_working_directory_based_not_generic_process_name() -> None:
    source = (ROOT / "start.sh").read_text() + (ROOT / "stop.sh").read_text()
    assert "process_cwd" in source and "atlas_pid_owner" in source
    assert "finance-copilot" not in source.lower()
    assert "*uvicorn*" not in source and "*next-server*" not in source
    assert "kill -9 $pids" not in source
