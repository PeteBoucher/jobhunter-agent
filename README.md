# Job Application Tracking Agent

An intelligent CLI tool that automates job searching, CV profile building, job matching, and application tracking across multiple job platforms.

## Current Status

The project is **fully functional** with working job scrapers fetching real listings:

- ✅ **Greenhouse scraper** - fetches jobs from 15 top tech companies (Stripe, Cloudflare, Airbnb, Figma, Discord, Datadog, etc.)
- ✅ **Lever scraper** - fetches jobs from Spotify, Palantir, Plaid
- ✅ **Adzuna scraper** - aggregates jobs from Indeed, Reed, Monster via free API (UK/US/EU)
- ✅ **The Muse scraper** - curated jobs from well-known tech companies (no auth required)
- ✅ **LinkedIn scraper** - guest endpoint with rate-limit handling and user-agent rotation
- ✅ **Smart CV parsing** - extracts skills, experience, and auto-populates matching preferences
- ✅ **Job matching engine** - 5-dimension scoring (title, skills, experience, location, salary)
- ✅ Background worker for periodic scraping and matching
- ✅ Centralized scraper registry for easy extension
- ✅ Metrics collection and Prometheus exporter
- ✅ Structured JSON logging
- ✅ Full test coverage (142+ tests)
- ✅ **AWS Lambda + EventBridge** deployment via SAM (S3-backed SQLite, SNS notifications)
- ✅ Deployment configurations (systemd, Docker, AWS SAM)

### Legacy Scrapers

The GitHub Jobs and Microsoft Careers scrapers remain in the codebase but return empty results due to deprecated APIs. They are still available via `--sources github` or `--sources microsoft` if the APIs are restored.

## Features

- 📄 **CV Parsing**: Extract skills, experience, and preferences from CV markdown files
- 🔍 **Real Job Data**: Greenhouse, Lever, Adzuna, and The Muse APIs fetch thousands of live listings
- 🎯 **Smart Job Matching**: 5-dimension scoring (title 30pts, skills 40pts, experience 10pts, location 10pts, salary 10pts)
- 🤖 **Background Worker**: APScheduler-based periodic scraping and job matching
- ☁️ **Serverless Deployment**: AWS Lambda + EventBridge with S3-backed SQLite and SNS notifications
- 📊 **Metrics & Monitoring**: Prometheus exporter with custom scrapers and job counts
- 📝 **Structured Logging**: JSON-formatted logs for production observability
- 💾 **SQLite Database**: Local development storage with PostgreSQL support for production
- 🔧 **CLI Interface**: Rich terminal UI with Click framework

## Quick Start

### Installation

```bash
# Clone and setup
git clone <repo>
cd jobhunter-agent

# Create virtual environment
python3.10 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
job-agent init
```

### Basic Usage

```bash
# Upload and parse your CV (auto-extracts skills + preferences)
job-agent profile upload path/to/cv.md

# View your profile
job-agent profile show

# Re-extract skills/preferences after CV parser improvements
job-agent profile refresh

# Scrape jobs from all default sources (Greenhouse + Lever + Adzuna + The Muse)
job-agent scrape

# Scrape specific sources
job-agent scrape --sources greenhouse
job-agent scrape --sources lever
job-agent scrape --sources adzuna
job-agent scrape --sources themuse

# Scrape with keyword filtering
job-agent scrape --keywords "python" --keywords "backend"

# Match jobs to your profile
job-agent match

# Search stored jobs (shows match scores when available)
job-agent jobs search --keywords "engineer"
job-agent jobs search --keywords "python" --remote remote
job-agent jobs search --keywords "software" --min-score 30
job-agent jobs search --remote remote --location spain --sort score

# View job details
job-agent jobs view 42

# Record an application
job-agent applications apply 42 --notes "Applied via company website"

# Start background worker (scrapes every 6h, matches every 12h)
job-agent worker

# View scraping metrics
job-agent metrics

# Export Prometheus metrics
job-agent prometheus
```

## Project Structure

```
jobhunter-agent/
├── src/
│   ├── cli.py                 # Click CLI commands
│   ├── job_scrapers/          # Job scraper implementations
│   │   ├── base_scraper.py    # Abstract base scraper with retry/backoff
│   │   ├── registry.py        # Centralized scraper registration
│   │   ├── greenhouse_scraper.py  # Greenhouse ATS API (15 companies)
│   │   ├── lever_scraper.py   # Lever ATS API (3 companies)
│   │   ├── adzuna_scraper.py  # Adzuna aggregator API (UK/US/EU)
│   │   ├── themuse_scraper.py # The Muse curated jobs API
│   │   ├── linkedin_scraper.py # LinkedIn guest endpoint
│   │   ├── github_scraper.py  # GitHub Jobs (deprecated)
│   │   └── microsoft_scraper.py # Microsoft Careers (deprecated)
│   ├── job_matcher.py         # Job matching engine
│   ├── models.py              # SQLAlchemy models
│   ├── database.py            # Database initialization
│   ├── worker.py              # Background worker with APScheduler
│   ├── lambda_handler.py      # AWS Lambda entry point
│   ├── metrics.py             # Metrics persistence and querying
│   ├── prometheus_exporter.py # Prometheus metrics export
│   ├── logging_config.py      # JSON logging setup
│   ├── incremental.py         # Incremental scraping + notifications
│   └── user_profile.py        # CV parsing and profile management
├── tests/                      # Comprehensive test suite (142+ tests)
├── requirements.txt
├── requirements-lambda.txt     # Minimal deps for Lambda
├── .env.example
├── Dockerfile                  # Local development container
├── Dockerfile.lambda           # AWS Lambda container (arm64)
├── template.yaml               # SAM template (Lambda + EventBridge + S3 + SNS)
├── samconfig.toml              # SAM deploy config (dev/prod)
├── docker-compose.yml
├── DEPLOYMENT.md              # Deployment guide
└── README.md (this file)
```

## Adding New Job Sources

All scrapers are registered in `src/job_scrapers/registry.py`. To add a new scraper:

1. Create a new scraper class inheriting from `BaseScraper`:

```python
from src.job_scrapers.base_scraper import BaseScraper

class MyCompanyScraper(BaseScraper):
    def _get_source_name(self) -> str:
        return "mycompany"

    def _fetch_jobs(self, **kwargs):
        # Fetch from API and return list of raw dicts
        pass

    def _parse_job(self, raw_job):
        # Convert to standardized format with fields:
        # source_job_id, title, company, location, description, apply_url, etc.
        pass
```

2. Register it in `src/job_scrapers/registry.py`:

```python
from src.job_scrapers.mycompany_scraper import MyCompanyScraper

SCRAPER_MAP["mycompany"] = MyCompanyScraper
```

### Adzuna API Setup

Adzuna requires a free API key. Sign up at [developer.adzuna.com](https://developer.adzuna.com).

For local use, set environment variables:
```bash
export ADZUNA_APP_ID=your_app_id
export ADZUNA_APP_KEY=your_app_key
```

For Lambda deployment, credentials are stored in AWS SSM Parameter Store (`/jobhunter/adzuna-app-id` and `/jobhunter/adzuna-app-key`) and resolved at deploy time.

The Adzuna scraper gracefully returns empty results if credentials are not configured.

### Adding Companies to Existing Scrapers

To add more Greenhouse or Lever companies, pass custom board lists:

```python
# Greenhouse - use the company's board token (URL slug)
scraper = GreenhouseScraper(session, board_tokens=["stripe", "cloudflare", "mycompany"])

# Lever - use the company's Lever slug
scraper = LeverScraper(session, company_slugs=["spotify", "palantir"])
```

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide with systemd and Docker
- [PROJECT_PLAN.md](PROJECT_PLAN.md) - Comprehensive project plan and roadmap

## Testing

Run the full test suite:

```bash
pytest -v                              # All tests
pytest tests/test_greenhouse_scraper.py  # Greenhouse scraper tests
pytest tests/test_lever_scraper.py       # Lever scraper tests
pytest tests/test_adzuna_scraper.py      # Adzuna scraper tests
pytest tests/test_themuse_scraper.py     # The Muse scraper tests
pytest tests/test_scrapers.py            # Legacy scraper tests
pytest tests/test_job_matcher.py         # Matcher tests
```

## Deployment

### AWS Lambda (Recommended)

The app deploys to AWS Lambda with EventBridge for scheduled scraping via SAM:

```bash
# Build the Docker image
sam build

# Deploy dev (scrapes every 12 hours)
sam deploy --config-env default

# Deploy prod (scrapes every 6 hours)
sam deploy --config-env prod
```

Architecture: EventBridge triggers Lambda on schedule → Lambda downloads SQLite DB from S3 → runs scrapers + match computation → uploads DB back to S3 → sends SNS notifications for high-score matches.

### Local Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for local deployment options:
- systemd service setup
- Docker containerization
- docker-compose for multi-service deployment
- Prometheus metrics collection

## Architecture Highlights

### Job Matching Algorithm
- **Title matching** (30pts): SequenceMatcher similarity against target titles from CV
- **Skill matching** (40pts): User skills extracted from CV matched against job requirements
- **Experience level** (10pts): Inferred from work history length (senior if 3+ roles)
- **Location/remote** (10pts): Remote preference and location matching
- **Salary alignment** (10pts): Job salary meets user minimum
- Profile auto-populates from CV: skills, target titles, experience level, remote preference

### Background Worker
- APScheduler for periodic job scraping and matching
- Configurable scheduling intervals
- Automatic metrics collection
- SimpleNotifier for high-match job alerts

### Metrics System
- Scraper success/failure tracking
- Job count persistence
- Prometheus-compatible metrics export
- Custom collectors for database stats

## Contributing

This project is under active development. For planned features, see PROJECT_PLAN.md.

## License

MIT
