# Development Workflow

This document outlines the standard development workflow and conventions for Jobhunter.

## Project Overview

Jobhunter is a hosted web app + CLI tool:

| Layer | Tech | Hosting |
|-------|------|---------|
| Scraper | AWS Lambda + EventBridge | AWS |
| Database | PostgreSQL (SQLAlchemy) | Neon (free tier) |
| Backend API | FastAPI | Render (free tier) |
| Frontend | Next.js 14 (App Router, TypeScript, Tailwind) | Vercel |
| Auth | next-auth (Google OAuth) + JWT | Vercel / Render |
| CLI | Click + Rich | Local |

## Project Structure

```
jobhunter-agent/
├── src/                        # Core Python library (shared by CLI + Lambda)
│   ├── cli.py                  # Click CLI commands
│   ├── models.py               # SQLAlchemy models (User, Job, JobMatch, Application, …)
│   ├── database.py             # Engine + session factory
│   ├── job_scrapers/           # Scraper registry + implementations
│   ├── job_matcher.py          # 5-dimension scoring engine
│   ├── job_searcher.py         # Query/filter/sort layer
│   ├── application_tracker.py  # Application CRUD with user isolation
│   ├── lambda_handler.py       # AWS Lambda entry point
│   └── user_profile.py        # CV parsing + preferences
├── web/
│   ├── api/                    # FastAPI backend (runs on Render)
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── dependencies.py
│   │   ├── routers/            # auth, jobs, profile, applications, preferences
│   │   ├── schemas/            # Pydantic models (UserOut, JobOut, …)
│   │   └── tests/              # FastAPI router tests (pytest + TestClient)
│   └── frontend/               # Next.js app (runs on Vercel)
│       ├── app/
│       │   ├── page.tsx                    # Landing / sign-in
│       │   ├── pending/page.tsx            # Waitlist holding page
│       │   ├── (app)/                      # Protected route group
│       │   │   ├── layout.tsx              # Sidebar + auth guard
│       │   │   ├── feed/page.tsx           # Job feed
│       │   │   ├── jobs/[id]/page.tsx      # Job detail
│       │   │   ├── profile/                # Profile + CV + preferences
│       │   │   └── applications/page.tsx   # Kanban board
│       │   └── api/auth/[...nextauth]/     # next-auth handler
│       ├── components/
│       └── lib/                # api.ts, auth.ts, types.ts
├── alembic/                    # DB migrations
│   └── versions/
├── tests/                      # CLI / scraper tests
├── template.yaml               # SAM template (Lambda + EventBridge + SNS)
├── samconfig.toml              # SAM deploy configs (default/prod)
├── requirements.txt
├── requirements-lambda.txt
├── pyproject.toml              # pytest config, black, mypy, isort
└── WORKFLOW.md                 # This file
```

## Daily Development Cycle

### 1. Feature Development

- Write code in the relevant layer (`src/`, `web/api/`, `web/frontend/`)
- Add or update tests in the matching test directory
- Run tests locally before committing (see Testing section below)

### 2. Pre-Commit Quality Checks

All Python code automatically goes through pre-commit hooks:

- **Black** — auto-formats code
- **isort** — organises imports
- **Flake8** — PEP 8 and common errors
- **Mypy** — static type checking

**Important**: Hooks may reformat files. After `git commit`:
1. If hooks fail or modify files, stage the changes: `git add <modified-files>`
2. Re-run the commit

### 3. Common Linting Issues

| Error | Fix |
|-------|-----|
| E501 line too long | Split across lines (max 88 chars) |
| F401 unused import | Remove it |
| F541 f-string no placeholders | Remove the `f` prefix |
| E741 ambiguous variable name | Use a descriptive name instead of `l`, `O`, `I` |
| var-annotated (mypy) | Add type hint: `result: list[str] = []` |
| E402 import not at top | Add `# noqa: E402` if import must follow path manipulation |

### 4. Committing Code

```bash
git add <file1> <file2> ...

git commit -m "$(cat <<'EOF'
feat: brief description

- Detail point 1
- Detail point 2

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"

git push origin master
```

### 5. Testing

All tests run with a single command (both `tests/` and `web/api/tests/` are in `testpaths`):

```bash
pytest -v                                    # All tests
pytest tests/ -v                             # CLI/scraper tests only
pytest web/api/tests/ -v                     # FastAPI router tests only
pytest web/api/tests/test_jobs.py -v         # Single file
pytest -k "test_create_application" -v       # Single test
```

Web API tests use FastAPI `TestClient` + in-memory SQLite with `StaticPool`. The `DATABASE_URL` and `JWT_SECRET` env vars are set in `conftest.py` before any app imports to prevent the module-level engine from connecting to Neon.

#### Test standards

- Use fixtures for repeated setup (`db_session`, `test_user`, `client`)
- Name tests `test_<what_it_does>` (not `test_<function_name>`)
- Assert specific values, not just "is not None"
- Test isolation: each test gets a fresh in-memory DB via `db_session` fixture rollback/teardown

### 6. Lambda Deployment

```bash
export DOCKER_HOST=unix:///Users/pete/.docker/run/docker.sock  # Required on Mac
sam build
sam deploy --config-env default --no-confirm-changeset  # Dev (12h schedule)
sam deploy --config-env prod --no-confirm-changeset     # Prod (6h schedule)
```

Lambda writes directly to Neon PostgreSQL via `DATABASE_URL` from SSM (`/jobhunter/database-url`).

### 7. Web App Deployment

The API (Render) and frontend (Vercel) deploy automatically on `git push origin master`.

Check deploy status at the Render and Vercel dashboards.

---

## User Feedback & Feature Requests

### Receiving feedback

Beta users give feedback via:
- Direct messages (WhatsApp, email, etc.)
- GitHub Issues (preferred for tracking — ask users to open one)

### Triaging

For each piece of feedback, decide:

| Category | Action |
|----------|--------|
| Bug (broken behaviour) | Fix promptly; hotfix commit if production-blocking |
| UX friction | Log as issue; batch with related changes |
| Feature request | Note the user need, not just the requested solution |
| Out of scope | Acknowledge and close |

### Turning feedback into work

1. Open a GitHub Issue with the user need described (not just the solution)
2. Label it: `bug`, `enhancement`, `ux`, or `question`
3. Implement on `master` (project is small enough to skip feature branches)
4. Reference the issue in the commit message: `fixes #12`

### Approving new users

When a new user signs up they land on `/pending`. Approve them in the Neon console:

```sql
UPDATE "user" SET is_approved = true WHERE email = 'friend@example.com';
```

Tell the user to sign out and back in.

---

## End-of-Day Checklist

- [ ] `pytest -v` — all tests pass
- [ ] `pre-commit run --all-files` — no lint issues
- [ ] Commit message is descriptive and references any issue number
- [ ] Pushed to GitHub: `git push origin master`
- [ ] Render/Vercel auto-deploy succeeded (check dashboards if touching API/frontend)

---

## Key Tools & Configuration

| Tool | Purpose |
|------|---------|
| pytest | Test runner (config in `pyproject.toml`) |
| black | Code formatter (88 char line length) |
| isort | Import sorter |
| flake8 | Linter |
| mypy | Static type checker |
| pre-commit | Runs black/isort/flake8/mypy on commit |
| alembic | DB schema migrations |
| SAM CLI | Lambda build + deploy |
| gh | GitHub CLI for issues and PRs |

### Venv / pip

```bash
source .venv/bin/activate
pip install -r requirements.txt        # CLI + Lambda deps
pip install -r web/api/requirements.txt  # FastAPI deps
```
