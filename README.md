# Jobhunter

A hosted web app + CLI tool that scrapes job listings, scores them against your CV, and tracks your applications. Free to use — sign in with Google to get started.

## Architecture

```text
[Vercel — Next.js]  ←── REST + JWT ──→  [Render — FastAPI]
                                                 │
                                         SQLAlchemy (sync)
                                                 │
                                    [Neon — PostgreSQL]
                                                 ↑
                                    [AWS Lambda — scraper]
                                    (EventBridge every 6h)
```

Jobs are scraped once into a shared pool. Each user has their own profile, match scores, and application tracking. The Lambda runs on a schedule (every 6h in prod), scrapes all sources concurrently, and writes directly to Neon.

## What's working

- **Google sign-in** — OAuth via next-auth; instant access, no approval needed
- **Job feed** — personalised match scores based on your CV and preferences
- **Job detail** — full description, score breakdown, apply button
- **AI tools** — generate a tailored cover letter, rewritten CV, or LinkedIn recruiter message for any job (powered by Claude Haiku via the `jobhunter-ai` private package)
- **CV upload** — markdown, PDF, or DOCX; skills auto-extracted via LLM and jobs re-scored
- **Preferences** — target titles, salary, remote preference, locations (city-level), countries to search (ISO2)
- **Applications kanban** — drag cards across Saved → Applied → Interview → Offer/Rejected
- **Shared scraping** — Lambda scrapes all sources every 6h concurrently; search terms and countries derived automatically from user preferences
- **Stale job expiry** — jobs not re-seen within 30 days are automatically marked inactive and hidden from the feed
- **Location-filtered notifications** — SNS alerts only fire for jobs in your preferred countries (fully remote jobs bypass the filter)
- **CLI** — full local CLI still works for power users and debugging

## Scrapers

### ATS platforms (multi-company)

| Scraper | Companies covered | Notes |
| --- | --- | --- |
| **Greenhouse** | Cloudflare, Airbnb, Figma, Discord, Adyen, Ebury, Lottoland, Kambi, Rush Street Interactive, Genius Sports, Fanatics, Cabify, and ~20 more | `boards-api.greenhouse.io` |
| **Lever** | Spotify, Palantir, Plaid, and more | `jobs.lever.co` |
| **Ashby** | OpenAI, Notion, Deel, ElevenLabs, Synthesia, Cursor, Perplexity, Mollie, Paddle, and ~30 more | `api.ashbyhq.com` |
| **Workday** | Accenture, Airbus, GSK, Adobe, Netflix, AstraZeneca, Maersk, BP, Unilever, Shell, Betway, Flutter Entertainment, Solera Holdings | Per-portal cap; large portals (Accenture, GSK…) scrape up to 500 jobs/run |
| **SmartRecruiters** | Bet365, Playtech, Evolution, Sportradar, EPAM Systems, Ciklum | `api.smartrecruiters.com` |
| **BambooHR** | Various | `api.bamboohr.com` |
| **Teamtailor** | The Workshop | `/jobs.json` JSON Feed; Schema.org location data |

### Job boards / aggregators

| Scraper | Source | Notes |
| --- | --- | --- |
| **Adzuna** | 13+ countries | API key in SSM; countries derived from user preferences |
| **The Muse** | Curated tech companies | No auth required |
| **Reed** | UK job board | API key required |

### Direct company scrapers

| Scraper | Company | Notes |
| --- | --- | --- |
| **Thoughtworks** | Thoughtworks | Direct careers page |
| **BCG** | Boston Consulting Group | |
| **Coinbase** | Coinbase | |
| **Revolut** | Revolut | |
| **Coderland** | Coderland | Manatal ATS proxied via Next.js; single request returns all listings |

### Not active

| Scraper | Reason |
| --- | --- |
| LinkedIn | Guest endpoint blocks Lambda IPs; violates ToS |
| GitHub Jobs | Deprecated — always returns empty |
| Microsoft Careers | Returns empty |

## Job matching algorithm

5-dimension scoring (100 pts total):

| Dimension | Points | Method |
| --- | --- | --- |
| Skills | 35 | Fraction of job requirements covered by CV skills |
| Title | 25 | Word-level Jaccard + character similarity against target titles |
| Experience | 15 | Seniority match between job level and user preference |
| Location/remote | 15 | Remote preference OR location substring match (OR relationship) |
| Salary | 10 | Gradient — job salary vs user minimum |

Score maxima are served from the API (`*_score_max` fields on every job response) so the frontend never hardcodes the weights.

## Project structure

```
jobhunter-agent/
├── src/
│   ├── cli.py
│   ├── models.py               # SQLAlchemy models
│   ├── database.py
│   ├── job_scrapers/
│   │   ├── base_scraper.py     # BaseScraper ABC
│   │   ├── registry.py         # SCRAPER_MAP + DEFAULT_SOURCES
│   │   └── *.py                # One file per scraper
│   ├── job_matcher.py
│   ├── job_searcher.py
│   ├── application_tracker.py
│   ├── lambda_handler.py       # Lambda entry point (scrape + match phases)
│   └── user_profile.py
├── web/
│   ├── api/                    # FastAPI (Render)
│   │   ├── main.py
│   │   ├── routers/
│   │   └── tests/
│   └── frontend/               # Next.js (Vercel)
│       ├── app/
│       ├── components/
│       └── lib/
├── tests/                      # CLI / scraper tests
├── .github/workflows/ci.yml    # CI: lint → test → deploy Lambda + Render + Vercel
├── template.yaml               # SAM template (Lambda + EventBridge + SNS)
├── samconfig.toml
├── Dockerfile.lambda
├── requirements.txt
├── requirements-lambda.txt
└── pyproject.toml
```

## CLI quick start

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
        # location, country, description, apply_url, …
        pass
```

2. Register in `src/job_scrapers/registry.py` (SCRAPER_MAP + DEFAULT_SOURCES).

**ATS quick-add patterns:**
- **Greenhouse** — add board token to `DEFAULT_BOARD_TOKENS` in `greenhouse_scraper.py`
- **Workday** — add a `WorkdayPortal` dataclass entry to `WORKDAY_PORTALS` in `workday_scraper.py`; set `max_jobs` proportional to listing volume
- **SmartRecruiters** — add `"CompanyId": "Display Name"` to `DEFAULT_COMPANIES` in `smartrecruiters_scraper.py`
- **Teamtailor** — add a `TeamtailorBoard` entry to `DEFAULT_BOARDS` in `teamtailor_scraper.py`

## Testing

```bash
pytest -v                        # All tests (CLI + web API)
pytest tests/ -v                 # CLI/scraper tests only
pytest web/api/tests/ -v         # FastAPI router tests only
```

Web API tests use `TestClient` + in-memory SQLite — no Neon connection needed.

## Deployment

### CI/CD (automatic on push to master)

`.github/workflows/ci.yml` runs on every push:

1. Python lint + tests (black, isort, flake8, mypy, bandit, pytest)
2. Frontend Vitest tests
3. **Deploy Lambda** — `sam build` (QEMU arm64 on amd64 runner) + `sam deploy --config-env prod`
4. **Deploy API** — Render deploy hook
5. **Deploy frontend** — Vercel CLI

Required GitHub secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `RENDER_DEPLOY_HOOK_URL`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.

### Lambda (manual)

```bash
export DOCKER_HOST=unix:///Users/pete/.docker/run/docker.sock
sam build
sam deploy --config-env prod --no-confirm-changeset
```

Lambda runs in two phases, each with a full 600s budget:

1. **Scrape** (`{}`) — scrapes all sources concurrently via `ThreadPoolExecutor`, expires stale listings (>30 days), then invokes itself async with `{"action":"match"}`.
2. **Match** (`{"action":"match"}`) — computes per-user scores, sends SNS notifications for matches ≥ 70% in the user's preferred countries.

```bash
# Trigger scrape + match cycle
aws lambda invoke --function-name jobhunter-prod --region eu-west-1 \
  --invocation-type Event --payload "$(echo '{}' | base64)" /dev/null

# Trigger match only
aws lambda invoke --function-name jobhunter-prod --region eu-west-1 \
  --invocation-type Event --payload "$(echo '{"action":"match"}' | base64)" /dev/null

# Watch logs
aws logs tail /aws/lambda/jobhunter-prod --region eu-west-1 --follow
```

### Web app

| Service | Config |
| --- | --- |
| Render | Root: `web/api`; build installs `jobhunter-ai` private package via `GITHUB_TOKEN` |
| Vercel | Root: `web/frontend`; pinned to `lhr1` (London) in `vercel.json` |
| Neon | Connection string in Render env vars + SSM `/jobhunter/database-url` |

### DB migrations

Schema changes are applied directly via Neon MCP or `psql`. `init_db()` handles new tables via `create_all()`, but new columns on existing tables require an explicit `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.

## User management

Sign-up is open — all new users get immediate access. The `is_approved` column is retained in the DB but not enforced.

Match score email notifications fire when a new job scores ≥ 70% against a user's profile (configurable via `MinMatchScoreNotify` in `samconfig.toml` — no Lambda rebuild needed).

## Documentation

- [CLAUDE.md](CLAUDE.md) — development conventions, architecture decisions, gotchas
- [WORKFLOW.md](WORKFLOW.md) — development workflow and deploy checklist
- [DEPLOYMENT.md](DEPLOYMENT.md) — local deployment options (systemd, Docker)
- [PROJECT_PLAN.md](PROJECT_PLAN.md) — current state, roadmap, and future features

## License

MIT
