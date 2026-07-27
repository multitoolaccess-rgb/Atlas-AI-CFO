# Local Python Environments

Atlas requires Python 3.12 and two isolated local virtual environments:

| Service or suite | Interpreter |
| --- | --- |
| Rules Service, Alembic, Rules tests, project cross-service tests, E2E backend | `.venv-rules/bin/python` |
| Finlynq and Finlynq tests | `.venv-finlynq/bin/python` |

## Why two environments

The services intentionally have incompatible framework pins. Rules Service
pins FastAPI 0.104.1; Finlynq pins FastAPI 0.111.0. Never install both
requirement manifests into one environment and do not change pins merely to
make a shared environment possible.

## Bootstrap

From the repository root, with Python 3.12 available:

```bash
bash scripts/bootstrap.sh
```

The script creates both environments and installs each service's declared
manifest into its own environment. To validate creation and installation
without running service tests, use:

```bash
RUN_SERVICE_TESTS=0 bash scripts/bootstrap.sh
```

The bootstrap script preserves its installed `pip`, `wheel`, and `setuptools`
versions by default so it also works in an offline development environment. To
upgrade only those packaging tools inside both Atlas environments, use
`UPGRADE_PACKAGING_TOOLS=1 bash scripts/bootstrap.sh`. Application dependency
upgrades remain separate reviewed work.

## Everyday commands

```bash
# Rules Service
(cd services/rules-service && ../../.venv-rules/bin/python -m pytest -q)

# Finlynq
(cd services/finlynq && ../../.venv-finlynq/bin/python -m pytest -q)

# Cross-service tests use Rules Service's environment
(cd services && ../.venv-rules/bin/python -m pytest tests -q)

# Launch the local stack
bash start.sh
```

`start.sh`, `scripts/test.sh`, `scripts/test-all.sh`, and
`scripts/test-e2e.sh` choose the appropriate interpreter automatically and
identify a missing environment with the exact bootstrap command.

## Troubleshooting and policy

- Do not use the old Finance Copilot `.venv`; it is not part of Atlas.
- Do not commit either virtual environment. `.gitignore` excludes `.venv/`,
  `.venv-*/`, and nested `.venv/` directories.
- If an Atlas environment has the wrong Python version, recreate only that
  known local environment with Python 3.12, then rerun bootstrap.
- Windows shell behavior has not been rewritten in this hardening task; use
  the existing Docker workflow or an equivalent Python 3.12 environment until
  a bounded Windows setup task is approved.
- Dependency upgrades and pin changes are separate reviewed work.
