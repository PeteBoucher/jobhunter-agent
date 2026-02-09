# Job Application Tracking Agent

An intelligent CLI tool that automates job searching, CV profile building, job matching, and application tracking across multiple job platforms.

## Features

- 🔍 **Multi-Platform Job Aggregation**: Search jobs from LinkedIn, Glassdoor, GitHub Jobs, Stack Overflow
- 📄 **CV Parsing**: Automatically extract skills, experience, and education from your CV
- 🎯 **Smart Job Matching**: ML-based job scoring against your profile
- 🤖 **Automation**: Auto-apply to matching jobs, schedule searches, track applications
- 📊 **Analytics**: Track application status, interview rates, and success metrics
- 💾 **Local Database**: SQLite-based storage for jobs, applications, and history

## Quick Start

### Installation

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env with your API keys
```

### First Run

```bash
# Upload and parse your CV
job-agent profile upload your_cv.md

# Set your job preferences
job-agent preferences set

# Fetch and match jobs
job-agent jobs search --location "New York"

# View top matches
job-agent jobs list --filter "match_score>75"
```

## Project Structure

See `PROJECT_PLAN.md` for detailed architecture and implementation roadmap.

## Documentation

- [PROJECT_PLAN.md](PROJECT_PLAN.md) - Comprehensive project plan and design
- [API Documentation](#) - API usage guide
- [CLI Commands](#) - Complete command reference

## Contributing

This project is under active development. See PROJECT_PLAN.md for the implementation roadmap.

## License

MIT
