## Code Quality Guidelines

This document explains the automated and human guardrails for the Jobhunter Agent project.

Automated checks (run on push / pull request via CI and pre-commit):

- Formatting: `black` (configured in `pyproject.toml`)
- Import ordering: `isort`
- Static typing: `mypy` (basic checks in CI; more strict locally optional)
- Linting: `flake8` for style and common errors
- Unit tests: `pytest` with coverage reporting
- Security: Secrets must never be committed — use `AWS Secrets Manager` or `.env` ignored by git

Pre-commit hooks (developers should install locally):

- `black` (format on commit)
- `isort` (sort imports)
- `flake8` (basic linting)
- `mypy` (quick type checks)
- `end-of-file-fixer` and `trailing-whitespace`

CI (GitHub Actions):

- Run `black --check`, `isort --check-only`, `flake8`, `mypy`, and `pytest` on PRs and pushes.

Developer workflow:

1. Install and activate the virtual environment.
2. Install dev dependencies: `pip install -r requirements.txt` (dev extras included).
3. Install pre-commit: `pre-commit install`.
4. Run `pre-commit run --all-files` before opening a PR.

Notes:

- Keep guardrail configs at repo root so CI and local tools share the same rules.
- Update this file if rules change or we add new linters or checks.
