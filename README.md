# Job Application Tracking Agent

An intelligent CLI tool that automates job searching, CV profile building, job matching, and application tracking across multiple job platforms.

## Current Status

The project is **fully functional** with the following core features implemented:

- ✅ User profile management and CV parsing
- ✅ Job scraper framework with retry/backoff logic
- ✅ Intelligent job matching engine with scoring algorithm
- ✅ Background worker for periodic scraping and matching
- ✅ Metrics collection and Prometheus exporter
- ✅ Structured JSON logging
- ✅ Full test coverage (67 tests)
- ✅ Deployment configurations (systemd, Docker)

### Note on Job Data Sources

Currently, the GitHub Jobs and Microsoft Careers scrapers return empty results due to:
- **GitHub Jobs API**: Deprecated and shut down (jobs.github.com no longer available)
- **Microsoft Careers API**: Endpoint changed (HTTP 404)

The scrapers are designed to gracefully handle these API changes and are ready to be integrated with production job APIs (LinkedIn, Indeed, GitHub API, etc.). See [Integration Guide](#production-job-api-integration) below.

## Features

- 📄 **CV Parsing**: Extract skills, experience, education, and languages from CV files
- 🎯 **Smart Job Matching**: Scoring algorithm matches jobs against user profile
- 🤖 **Background Worker**: APScheduler-based periodic scraping and job matching
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
# Upload and parse your CV
job-agent profile upload path/to/cv.pdf

# View your profile
job-agent profile show

# Scrape jobs (currently returns 0 jobs due to API deprecation)
job-agent scrape

# Match jobs to your profile
job-agent match

# Start background worker
job-agent worker start

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
│   │   ├── base_scraper.py   # Abstract base scraper
│   │   ├── github_scraper.py
│   │   └── microsoft_scraper.py
│   ├── job_matcher.py         # Job matching engine
│   ├── models.py              # SQLAlchemy models
│   ├── database.py            # Database initialization
│   ├── worker.py              # Background worker with APScheduler
│   ├── metrics.py             # Metrics persistence and querying
│   ├── prometheus_exporter.py # Prometheus metrics export
│   ├── logging_config.py      # JSON logging setup
│   ├── incremental.py         # Incremental scraping + notifications
│   └── user_profile.py        # CV parsing and profile management
├── tests/                      # Comprehensive test suite (67 tests)
├── requirements.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── deployment.md              # Deployment guide
└── README.md (this file)
```

## Documentation

- [DEPLOYMENT.md](DEPLOYMENT.md) - Production deployment guide with systemd and Docker
- [PROJECT_PLAN.md](PROJECT_PLAN.md) - Comprehensive project plan and roadmap

## Production Job API Integration

To enable real job data in production, replace the empty returns in the scrapers with actual API integrations:

### Option 1: Use Job Aggregation APIs
- **LinkedIn Jobs API**: Official job data (requires business access)
- **Indeed API**: Job aggregator with broad coverage
- **Glassdoor API**: Career and job information
- **Stack Overflow Jobs API**: Tech-focused positions

### Option 2: Implement New Scrapers
Create new scraper classes in `src/job_scrapers/` following the `BaseScraper` pattern:

```python
class LinkedInScraper(BaseScraper):
    def _fetch_jobs(self, keywords, location, **kwargs):
        # Implement LinkedIn API integration
        pass

    def _parse_job(self, raw_job):
        # Parse API response into standardized format
        pass
```

### Option 3: Web Scraping
Implement web scraping using BeautifulSoup (already available) to extract job listings from job boards.

## Testing

Run the full test suite:

```bash
pytest -v          # All tests
pytest tests/test_scrapers.py  # Scraper tests
pytest tests/test_job_matcher.py  # Matcher tests
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed deployment instructions including:
- systemd service setup
- Docker containerization
- docker-compose for multi-service deployment
- Prometheus metrics collection

## Architecture Highlights

### Job Matching Algorithm
- Skill-based scoring (exact, partial, and fuzzy matches)
- Location preference matching
- Salary range validation
- Experience level alignment
- Company size and industry preferences

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
