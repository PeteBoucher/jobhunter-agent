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
sam deploy --config-env default

# Prod (schedule enabled, runs every 6h)
sam deploy --config-env prod
```

### Stacks

| Stack | Region | S3 Bucket | Schedule |
|---|---|---|---|
| `jobhunter-dev` | eu-west-1 | `jobhunter-data-dev` | Disabled |
| `jobhunter-prod` | eu-west-1 | `jobhunter-data-prod` | Every 6h |

ECR: `624372908505.dkr.ecr.eu-west-1.amazonaws.com/jobhunter`

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

## Key Architecture Notes

- **Scrapers**: `BaseScraper` ABC in `src/job_scrapers/`. Registry in `src/job_scrapers/registry.py`. Default sources: greenhouse, lever, adzuna, themuse.
- **Lambda flow**: download DB from S3 → scrape new jobs → compute matches → upload DB to S3 → SNS notification if matches above threshold.
- **Lambda timeout**: 300s. Matching a large backlog of unmatched jobs (e.g. first run after new user profile) will time out. Run `job-agent match` locally and upload the DB manually in that case.
- **Lambda memory**: ~236MB used out of 256MB — bump to 512MB if OOM errors appear.
- **User profile**: stored in the `user` table. The prod profile is Peter Boucher — Senior / Remote / Innovation Lead / QA Analyst.
