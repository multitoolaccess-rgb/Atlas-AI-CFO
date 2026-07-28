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

## Run Atlas beside Finance Copilot

Atlas has a separate loopback-only local port profile, so it can run beside a
legacy Finance Copilot checkout without replacing or stopping it.

| Application | UI | Rules Service | Finlynq |
| --- | --- | --- | --- |
| Legacy Finance Copilot | http://localhost:3000 | http://localhost:8000 | http://localhost:8001 |
| Atlas | http://localhost:3333 | http://localhost:8888 | http://localhost:8889 |

From the Atlas repository root, start and stop the Atlas profile with:

```bash
bash start.sh
bash stop.sh
```

The profile is controlled by `ATLAS_UI_PORT`, `ATLAS_RULES_PORT`, and
`ATLAS_FINLYNQ_PORT`. All must be distinct non-privileged TCP ports. For an
isolated alternate Atlas session, override all three consistently:

```bash
ATLAS_UI_PORT=4333 ATLAS_RULES_PORT=9888 ATLAS_FINLYNQ_PORT=9889 bash start.sh
ATLAS_UI_PORT=4333 ATLAS_RULES_PORT=9888 ATLAS_FINLYNQ_PORT=9889 bash stop.sh
```

`start.sh` passes `FINLYNQ_BASE_URL=http://127.0.0.1:$ATLAS_FINLYNQ_PORT` to
Rules Service and `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:$ATLAS_RULES_PORT`
to Next.js. It only reaps listeners owned by this Atlas checkout on the
configured ports; it does not touch the legacy profile's default ports.

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
