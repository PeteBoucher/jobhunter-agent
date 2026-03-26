# Jobhunter

A hosted web app + CLI tool that scrapes job listings, scores them against your CV, and tracks your applications. Currently in private beta.

## Architecture

```
[Vercel — Next.js]  ←── REST + JWT ──→  [Render — FastAPI]
                                                 │
                                         SQLAlchemy (sync)
                                                 │
                                    [Neon — PostgreSQL]
                                                 ↑
                                    [AWS Lambda — scraper]
                                    (EventBridge schedule)
```

Jobs are scraped once into a shared pool. Each user has their own profile, match scores, and application tracking. The Lambda runs on a schedule (every 6h in prod), scrapes all sources, and writes directly to Neon.

## What's working

- **Google sign-in** — OAuth via next-auth; new users land on `/pending` waitlist
- **Job feed** — personalised match scores based on your CV and preferences
- **Job detail** — full description, score breakdown, apply button
- **CV upload** — markdown, PDF, or DOCX; skills auto-extracted via LLM and jobs re-scored
- **Preferences** — target titles, salary, remote preference, locations (city-level), countries to search (ISO2)
- **Applications kanban** — drag cards across Saved → Applied → Interview → Offer/Rejected
- **Shared scraping** — Lambda scrapes all sources every 6h concurrently; search terms and countries derived automatically from user preferences
- **Stale job expiry** — jobs not re-seen within 30 days are automatically marked inactive and hidden from the feed
- **CLI** — full local CLI still works for power users and debugging

### Scrapers

| Scraper | Source | Notes |
|---------|--------|-------|
| Greenhouse | Stripe, Cloudflare, Airbnb, Figma, Discord, Datadog, Adyen, and more | ATS API |
| Lever | Spotify, Palantir, Plaid, and more | ATS API |
| Ashby | Modern ATS used by many startups | ATS API |
| Adzuna | Indeed, Reed, Monster aggregate | API key in SSM; countries derived from user preferences |
| The Muse | Curated tech companies | No auth required |
| Reed | UK job board | API key required |
| LinkedIn | Guest search endpoint | Rate-limited; no auth; descriptions fetched via guest job detail API |
| Workday | Enterprise ATS | Configured per-company |
| Thoughtworks | Direct careers page | |
| GitHub Jobs | — | Deprecated, returns empty |
| Microsoft Careers | — | Deprecated, returns empty |

### Job matching algorithm

5-dimension scoring (100pts total):

| Dimension | Points | Method |
|-----------|--------|--------|
| Skills | 35 | Fraction of job requirements covered by CV skills |
| Title | 25 | Word-level Jaccard + character similarity against target titles |
| Experience | 15 | Seniority match between job level and user preference |
| Location/remote | 15 | Remote preference OR location substring match (OR relationship) |
| Salary | 10 | Gradient — job salary vs user minimum |

Score maxima are served from the API (`*_score_max` fields on every job response) so the frontend never needs its own copy of the weights.

## Project structure

```
jobhunter-agent/
├── src/                        # Core Python library
│   ├── cli.py
│   ├── models.py               # SQLAlchemy models
│   ├── database.py
│   ├── job_scrapers/           # BaseScraper + registry + implementations
│   ├── job_matcher.py
│   ├── job_searcher.py
│   ├── application_tracker.py
│   ├── lambda_handler.py       # Lambda entry point
│   └── user_profile.py
├── web/
│   ├── api/                    # FastAPI (deploys to Render)
│   │   ├── main.py
│   │   ├── auth.py
│   │   ├── dependencies.py
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── tests/
│   └── frontend/               # Next.js (deploys to Vercel)
│       ├── app/
│       ├── components/
│       └── lib/
├── tests/                      # CLI / scraper tests
├── template.yaml               # SAM template (Lambda + EventBridge + SNS)
├── samconfig.toml
├── requirements.txt
├── requirements-lambda.txt
└── pyproject.toml              # pytest, black, mypy config
```

## CLI quick start

For local use without the web app:

```bash
# Setup
python3.10 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Add your CV (markdown, PDF, or DOCX)
job-agent profile upload path/to/cv.md

# Scrape and match
job-agent scrape
job-agent match

# Search
job-agent jobs search --keywords "python" --min-score 30
job-agent jobs view 42

# Track applications
job-agent applications apply 42 --notes "Applied via website"
```

## Adding a new scraper

1. Create `src/job_scrapers/mycompany_scraper.py` inheriting `BaseScraper`:

```python
from src.job_scrapers.base_scraper import BaseScraper

class MyCompanyScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "mycompany"

    def _fetch_jobs(self, **kwargs):
        # Fetch from API, return list of raw dicts
        pass

    def _parse_job(self, raw_job):
        # Return standardised dict: source_job_id, title, company,
        # location, description, apply_url, …
        pass
```

2. Register in `src/job_scrapers/registry.py`:

```python
from src.job_scrapers.mycompany_scraper import MyCompanyScraper
SCRAPER_MAP["mycompany"] = MyCompanyScraper
```

### Adzuna API key

Sign up at [developer.adzuna.com](https://developer.adzuna.com). For local use:

```bash
export ADZUNA_APP_ID=your_app_id
export ADZUNA_APP_KEY=your_app_key
```

For Lambda, credentials are in AWS SSM (`/jobhunter/adzuna-app-id`, `/jobhunter/adzuna-app-key`).

## Testing

```bash
pytest -v                        # All tests (CLI + web API)
pytest tests/ -v                 # CLI/scraper tests only
pytest web/api/tests/ -v         # FastAPI router tests only
```

Web API tests use `TestClient` + in-memory SQLite — no Neon connection needed.

## Deployment

### Lambda (scraper)

```bash
sam build
sam deploy --config-env default   # Dev — schedule disabled
sam deploy --config-env prod      # Prod — 6h schedule
```

Lambda writes to Neon via `DATABASE_URL` from SSM (`/jobhunter/database-url`).

### Web app

Render (API) and Vercel (frontend) deploy automatically on `git push origin master`.

| Service | Config |
|---------|--------|
| Render | Root: `web/api`, start: `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Vercel | Root: `web/frontend`, env: `NEXT_PUBLIC_API_URL`, `NEXTAUTH_URL`, Google OAuth keys |
| Neon | Connection string in Render env vars + SSM `/jobhunter/database-url` |

### DB migrations

Schema changes are applied directly via Neon MCP or `psql`. `init_db()` (called at Lambda startup) handles new tables via `Base.metadata.create_all()`, but new columns on existing tables require an explicit `ALTER TABLE`.

## User management

New sign-ups land on `/pending`. To approve a user, run in the Neon console:

```sql
UPDATE "user" SET is_approved = true WHERE email = 'friend@example.com';
```

User signs out and back in to pick up the change.

## Documentation

- [WORKFLOW.md](WORKFLOW.md) — development workflow, feedback process, deploy checklist
- [DEPLOYMENT.md](DEPLOYMENT.md) — local deployment options (systemd, Docker)

## License

MIT
