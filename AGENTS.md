# Repository Guidelines

## Project Structure & Module Organization
- `agent/`: FastAPI runtime (`api.py` entrypoint, `telemetry.py` metrics, `jobs.py` scheduler, `store.py` persistence, `dashboard.py` monitoring UI, `discover.py` discovery helpers).
- `cece/`: Dynamic planning core (`dynamic_planner.py`, `self_healing_orchestrator.py`, `natural_memory.py`, `issue_creator.py` CLI entry).
- `templates/`: Markdown/HTML templates and examples; copy before editing to keep base templates intact.
- `Dockerfile`, `railway.toml`, and `pyproject.toml`: Container build, Railway deploy config, packaging and lint settings.

## Build, Test, and Development Commands
- Create venv: `python -m venv .venv && source .venv/bin/activate`; install: `pip install -e ".[dev]"` (or `pip install blackroad-agents` for consumers).
- Run API: `uvicorn agent.api:app --reload --host 0.0.0.0 --port 8000`; smoke check: `curl http://localhost:8000/health`.
- Planner CLI: `python -m cece.dynamic_planner "Deploy feature"` to validate CeCe flows.
- Lint/format/type-check: `black agent cece`, `ruff check agent cece`, `mypy agent cece`.
- Docker: `docker build -t blackroad-agents .` then `docker run -p 8000:8000 blackroad-agents`; Railway: `railway up` after `railway link`.

## Coding Style & Naming Conventions
- Black line length 100; PEP 8 with Ruff defaults; type hints expected and `mypy` must pass.
- Naming: `snake_case` for functions/vars, `PascalCase` classes, `UPPER_SNAKE` env/config keys; FastAPI routes under `/health`, `/agents/*`, `/jobs/*`, `/telemetry/*` with Pydantic models.

## Testing Guidelines
- Pytest (with `pytest-asyncio`) for runtime and planner; aim for coverage on new behavior: `pytest --maxfail=1 --disable-warnings --cov=agent --cov=cece`.
- Place tests under `tests/` mirroring modules (e.g., `tests/test_jobs.py`, `tests/test_dynamic_planner.py`); mock Redis/httpx and avoid hitting live services.

## Commit & Pull Request Guidelines
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `chore:`); keep scope meaningful.
- PRs include behavior summary, verification steps (curl examples or planner run), linked issue/ticket, and screenshots for dashboard/template changes; call out new env vars or migrations.

## Security & Configuration Tips
- Keep secrets out of git; supply via env or Railway variables (`REDIS_URL`, `API_HOST`, `API_PORT`, `TELEMETRY_*`).
- Validate incoming payloads at FastAPI layer and avoid logging sensitive job data; sanitize template edits.
- For telemetry or queue changes, run local smoke (`uvicorn ...`, `curl /health`, submit a sample job) before requesting review.
