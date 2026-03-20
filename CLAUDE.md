# Jobhunter Agent - Claude Context

## Project Vision

An automated job search and application tracking agent that eliminates the manual grind of job hunting. The system continuously discovers relevant opportunities across multiple platforms, scores them against the user's CV and preferences, and tracks the full lifecycle from discovery through to offer.

**Goal**: Automate the entire job search workflow — from scraping and matching to application tracking and interview prep.

**Roadmap** (see `PROJECT_PLAN.md` for full detail):

1. **Done** — Core CLI, CV parsing, job scrapers (Greenhouse, Lever, Adzuna, The Muse), matching engine, application tracker, AWS Lambda + S3 deployment, SNS notifications
2. **Next** — Improve match quality (tune scoring weights, expand scraper targets), Google Sheets integration for tracking
3. **Future** — Auto-apply workflow, cover letter generation, interview prep, email digest, web dashboard

**Matching formula** (score 0–100):
```
score = (skill_match × 0.35) + (title_match × 0.25) + (experience_match × 0.15)
      + (location_or_remote_match × 0.15) + (salary_match × 0.10)
```
Location and remote have an OR relationship — a job qualifies if either the location matches *or* it's remote.

---

## Development Workflow

Every change should follow this cycle:

```
Problem → Plan → Approve → Execute → Test → Document → Commit → Deploy
```

### Steps

1. **Problem** — Clearly state what needs to change and why. Check the prod DB or logs if investigating a data/runtime issue.

2. **Plan** — Explore the codebase, identify affected files, and outline the approach before writing any code. For non-trivial changes, present the plan to the user for approval before proceeding.

3. **Approve** — User confirms the plan. Don't start coding until approved.

4. **Execute** — Implement the change. One concern at a time; don't refactor unrelated code.

5. **Test** — Always run the full test suite after changes:
   ```bash
   .venv/bin/python -m pytest
   ```
   Fix any failures before proceeding. Add or update tests for new behaviour.

6. **Document** — Update `CLAUDE.md` if new patterns, gotchas, or architectural decisions were introduced. Update `README.md` if user-facing behaviour changed.

7. **Commit** — Stage only the relevant files and commit with a clear message. Pre-commit hooks run black, isort, flake8, mypy — re-stage if black reformats files.

8. **Deploy** — Any code change that affects Lambda behaviour must be built and deployed to prod:
   ```bash
   DOCKER_HOST=unix:///Users/pete/.docker/run/docker.sock sam build
   sam deploy --config-env prod --no-confirm-changeset
   ```
   Config-only changes (SSM values, samconfig.toml) do not require a rebuild.

---

## Python / CLI

Always use the project virtualenv, not system Python:

```bash
.venv/bin/job-agent <command>
.venv/bin/python -m pytest
.venv/bin/python -m src.cli <command>
```

Run tests:

```bash
.venv/bin/python -m pytest
```

## Database

The CLI uses a local SQLite file, controlled by `DATABASE_URL`:

```bash
# Default (local dev)
DATABASE_URL="sqlite:///./data/jobs.db"

# Point at a downloaded prod DB
DATABASE_URL="sqlite:////tmp/jobs-prod.db" .venv/bin/job-agent <command>
```

To work against the prod database:

```bash
aws s3 cp s3://jobhunter-data-prod/jobhunter/jobs.db /tmp/jobs-prod.db --region eu-west-1
DATABASE_URL="sqlite:////tmp/jobs-prod.db" .venv/bin/job-agent <command>
aws s3 cp /tmp/jobs-prod.db s3://jobhunter-data-prod/jobhunter/jobs.db --region eu-west-1
```

## AWS / SAM Deployment

### Build

Docker Desktop must be running. Use the Docker Desktop socket:

```bash
DOCKER_HOST=unix:///Users/pete/.docker/run/docker.sock sam build
```

### Deploy

```bash
# Dev (schedule disabled)
sam deploy --config-env default --no-confirm-changeset

# Prod (schedule enabled, runs every 6h)
sam deploy --config-env prod --no-confirm-changeset
```

### Stacks

| Stack | Region | S3 Bucket | Schedule |
|---|---|---|---|
| `jobhunter-dev` | eu-west-1 | `jobhunter-data-dev` | Disabled |
| `jobhunter-prod` | eu-west-1 | `jobhunter-data-prod` | Every 6h |

ECR: `624372908505.dkr.ecr.eu-west-1.amazonaws.com/jobhunter`

## Service Regions

All services are intentionally co-located in Europe to minimise latency:

| Service | Region | Notes |
|---|---|---|
| Neon (PostgreSQL) | `aws-eu-west-2` (London) | Primary database |
| AWS Lambda | `eu-west-1` (Ireland) | ~10ms from Neon |
| Render (FastAPI) | `eu-central` (Frankfurt) | ~20ms from Neon |
| Vercel Functions | `lhr1` (London) | Pinned in `web/frontend/vercel.json` |

Vercel defaults to `east-us-1` (Virginia) — the `regions` override in `vercel.json` is intentional. Do not remove it.

### Invoke Lambda manually

```bash
# Async (recommended — Lambda takes ~3-5 min)
aws lambda invoke --function-name jobhunter-prod --region eu-west-1 \
  --invocation-type Event --payload '{}' /dev/null

# Watch logs
aws logs tail /aws/lambda/jobhunter-prod --region eu-west-1 --follow
```

## SSM Parameters

Adzuna API credentials are stored in SSM (eu-west-1), not in code or config:

- `/jobhunter/adzuna-app-id` — String
- `/jobhunter/adzuna-app-key` — String

Referenced in `template.yaml` via `{{resolve:ssm:/jobhunter/adzuna-app-id}}`.
Do **not** use `{{resolve:ssm-secure:...}}` — Lambda environment variables don't support SecureString.

## Pre-commit Hooks

black, isort, flake8, and mypy all run on commit. If black reformats a file, re-stage and commit again.

## Observability

### Grafana Cloud

Lambda logs → Grafana via CloudWatch data source. Dashboard at `grafana/lambda-dashboard.json` — import manually via Grafana UI when updated.

FastAPI (Render) logs → Grafana via Loki push. Env vars required on the Render service:
- `LOKI_URL` = `https://logs-prod-012.grafana.net`
- `LOKI_USER` = `1518410`
- `LOKI_TOKEN` = Grafana Cloud API token with `logs:write` scope

Loki data source in Grafana: `grafanacloud-jobhunter-logs`.

### SNS alerts

Lambda scraper sends SNS alerts on match threshold. Topic: `jobhunter-alerts` (eu-west-1). Email subscription confirmed.

---

## Key Architecture Notes

- **Scrapers**: `BaseScraper` ABC in `src/job_scrapers/`. Registry in `src/job_scrapers/registry.py`. Default sources: ashby, greenhouse, lever, adzuna, themuse, reed, linkedin.
- **Lambda flow**: scrape new jobs → compute matches → SNS notification if matches above threshold. Writes directly to Neon (no S3 SQLite).
- **Lambda timeout**: 600s. Matching is capped at `MAX_MATCH_PER_RUN` (default 500) per invocation so it won't time out; the backlog drains across subsequent 6h runs. To run matching locally against the full backlog: `DATABASE_URL="..." .venv/bin/job-agent match`.
- **Lambda memory**: 512MB.
- **Multi-user**: multiple users supported. Each user has their own `JobMatch` rows. Prod users managed via `is_approved` flag in the `user` table.
- **Neon idle SSL timeout**: Neon closes idle connections after ~5 min. `create_engine_instance()` sets TCP keepalives (`keepalives_idle=60`) and `pool_pre_ping=True`. `BaseScraper.scrape()` calls `session.invalidate()` after `_fetch_jobs()` so the connection is dropped cleanly before the DB write phase — `session.close()` would fail because it tries to rollback on a dead SSL link. Do not bypass `create_engine_instance()` with a bare `create_engine()` call.
- **Mobile layout**: `(app)/layout.tsx` uses `h-screen overflow-hidden` + flex column. Sidebar is `hidden md:flex`. Mobile gets a top bar (logo + avatar) and a bottom nav bar (`shrink-0`, not `fixed`). The `<main>` is `flex-1 overflow-auto` — content scrolls inside, nav stays pinned. Do not use `position: fixed` for the bottom nav — `overflow-x-auto` on child pages breaks fixed positioning.
