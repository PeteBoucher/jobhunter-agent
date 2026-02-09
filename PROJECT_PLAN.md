# Job Application Tracking Agent - Project Plan

## Project Overview
A comprehensive Python-based CLI tool that automates job searching, CV profile building, job matching, and application tracking across multiple job platforms (LinkedIn, Glassdoor, GitHub Jobs, Stack Overflow).

**Goal**: Automate the entire job search workflow, from discovering relevant opportunities to tracking applications.

---

## Phase 1: Foundation & Setup

### 1.1 Project Structure
```
jobhunter-agent/
├── src/
│   ├── __init__.py
│   ├── main.py                 # CLI entry point
│   ├── config.py               # Configuration and constants
│   ├── database.py             # SQLite database layer
│   ├── cv_parser.py            # CV/Resume parsing
│   ├── user_profile.py         # User profile management
│   ├── job_scrapers/
│   │   ├── __init__.py
│   │   ├── base_scraper.py     # Abstract base scraper
│   │   ├── linkedin_scraper.py
│   │   ├── glassdoor_scraper.py
│   │   ├── github_scraper.py
│   │   ├── stackoverflow_scraper.py
│   │   └── company_scrapers/
│   │       ├── __init__.py
│   │       ├── microsoft_scraper.py
│   │       ├── google_scraper.py
│   │       ├── vodafone_scraper.py
│   │       ├── apple_scraper.py
│   │       ├── meta_scraper.py
│   │       ├── amazon_scraper.py
│   │       └── company_scraper_registry.py  # Dynamic company scraper loader
│   ├── job_matcher.py          # ML-based job matching
│   ├── application_tracker.py  # Track applications
│   └── automation.py           # Automation workflows
├── data/
│   ├── cv_template.md          # User uploads CV here
│   ├── jobs.db                 # SQLite database
│   └── applications.json       # Application history
├── tests/
│   ├── __init__.py
│   ├── test_cv_parser.py
│   ├── test_scrapers.py
│   └── test_matcher.py
├── requirements.txt            # Python dependencies
├── .env.example                # Environment variables template
├── README.md                   # Project documentation
├── PROJECT_PLAN.md            # This file
└── .gitignore
```

### 1.2 Dependencies
```
Core CLI:
- click          # CLI framework
- rich           # Beautiful terminal output
- python-dotenv  # Environment variable management

Data & Database:
- sqlite3        # Built-in database
- pandas         # Data manipulation
- sqlalchemy     # ORM for database

API Integration:
- requests       # HTTP requests
- linkedin-api   # LinkedIn scraping (unofficial)
- playwright     # Browser automation for complex scraping
- beautifulsoup4 # HTML parsing

NLP & ML:
- spacy          # NLP for CV parsing
- scikit-learn   # ML for job matching
- fuzzywuzzy     # Fuzzy string matching

Application Automation:
- selenium       # Browser automation for job applications
- python-pptx    # Resume generation (optional)

Testing & Quality:
- pytest         # Testing framework
- pytest-cov     # Test coverage
```

---

## Phase 2: Core Features

### 2.1 CV Parser Module (`cv_parser.py`)
**Objective**: Extract structured data from user's CV

**Features**:
- Parse CV from markdown file uploaded by user
- Extract:
  - Personal info (name, email, phone, location)
  - Professional summary
  - Work experience (company, title, dates, responsibilities)
  - Education (school, degree, field, graduation date)
  - Skills (technical, soft skills, languages)
  - Certifications
  - Projects
  - Links (GitHub, Portfolio, LinkedIn)
- Store structured data in database
- Support multiple formats (PDF extraction via pdfplumber)

**Output**: Structured JSON/database records

---

### 2.2 User Profile Management (`user_profile.py`)
**Objective**: Manage and update user profile

**Features**:
- Create profile from parsed CV
- User preferences:
  - Target job titles/roles
  - Desired industries
  - Preferred locations/remote status
  - Salary expectations
  - Experience level (Junior, Mid, Senior, Lead)
  - Willing to relocate (yes/no)
  - Contract type preferences (Full-time, Part-time, Contract, Freelance)
- Skills inventory with proficiency levels
- Employment history timeline
- Education summary
- Interactive CLI to add/update preferences
- Export profile as JSON

---

### 2.3 Job Scrapers (`job_scrapers/`)
**Objective**: Aggregate jobs from multiple platforms

**Base Scraper Pattern**:
```python
class BaseScraper:
    def search(self, query, filters)
    def get_job_details(self, job_id)
    def scrape_jobs(self) -> List[Job]
```

**Platform-Specific Scrapers**:

#### LinkedIn (`linkedin_scraper.py`)
- Use LinkedIn API (official or unofficial)
- Search parameters: keyword, location, experience level, company
- Extract: title, company, location, salary, description, date posted
- Authentication required

#### Glassdoor (`glassdoor_scraper.py`)
- Web scraping with Playwright
- Search parameters: keyword, location, salary range, company rating
- Extract: title, company, location, salary, benefits, rating, reviews
- Extract company info (size, industry, founded year)

#### GitHub Jobs (`github_scraper.py`)
- Use GitHub Jobs API (if available) or scrape
- Search parameters: keyword, location, full-time/remote
- Extract: title, company, location, description, apply URL

#### Stack Overflow (`stackoverflow_scraper.py`)
- API-based scraping
- Search parameters: tag, location, remote options
- Extract: title, company, location, tech stack requirements

#### Company Career Portals (`company_scrapers/`)
**Objective**: Direct scraping of specific company career pages for real-time job listings

**Target Companies** (Configurable):
- Microsoft (`microsoft_scraper.py`): careers.microsoft.com
- Google (`google_scraper.py`): google.com/careers
- Vodafone (`vodafone_scraper.py`): vodafone.com/careers
- Apple (`apple_scraper.py`): apple.com/jobs
- Meta (`meta_scraper.py`): metacareers.com
- Amazon (`amazon_scraper.py`): amazon.jobs
- And more (user-configurable in settings)

**Features**:
- Each company scraper handles unique career portal HTML/API structure
- Extract: title, department, location, salary, apply_url
- Parse job descriptions and requirements from company-specific formats
- Monitor posting dates to detect new listings
- Handle authentication where required (e.g., LinkedIn sign-in)
- Graceful fallback to web scraping if APIs unavailable
- Rate limiting to respect company servers

**Benefits**:
- Access to exclusive job listings not posted on aggregator sites
- Real-time updates directly from company sources
- Higher quality leads for target companies
- Opportunity to track specific company hiring trends
- Can identify roles before they appear on LinkedIn

**Common Job Object Schema**:
```python
{
  "id": "unique_id",
  "source": "linkedin|glassdoor|github|stackoverflow|microsoft|google|vodafone|apple|meta|amazon|<other_company>",
  "title": str,
  "company": str,
  "department": str,
  "location": str,
  "remote": "onsite|hybrid|remote",
  "salary_min": float,
  "salary_max": float,
  "description": str,
  "requirements": [str],
  "nice_to_haves": [str],
  "apply_url": str,
  "posted_date": datetime,
  "scrape_date": datetime,
  "company_industry": str,
  "company_size": str,
  "source_type": "aggregator|company_portal"
}
```

---

### 2.4 Job Matching Engine (`job_matcher.py`)
**Objective**: Score jobs against user profile

**Matching Algorithm**:
- Skill match: Compare user skills with job requirements (weighted scoring)
- Title match: Job title similarity to user's target roles (fuzzy matching)
- Location & Remote match: User location preferences vs job location **OR** user remote preference vs job type (either location match OR remote match satisfies this criterion)
- Experience match: User experience level vs job level requirement
- Salary match: Job salary vs user expectations
- Company match: User industry/company preferences

**Output**: Match score (0-100) + breakdown of scores per category

**Scoring Formula**:
```
# Location and Remote have OR relationship (either can satisfy the requirement)
location_or_remote_match = MAX(location_match, remote_match)

Final Score = (
  (skill_match * 0.35) +
  (title_match * 0.25) +
  (experience_match * 0.15) +
  (location_or_remote_match * 0.15) +
  (salary_match * 0.10)
)
```

**Location/Remote Scoring Logic**:
```
- If user prefers remote: remote_match = 100 if job is remote/hybrid, else 0
- If user specifies location(s): location_match = fuzzy match score of job location vs preferred locations
- Combined: location_or_remote_match = MAX(location_match, remote_match)
  - This means: Job qualifies if EITHER location matches OR it's a remote opportunity
  - If job is remote AND location matches = highest score
  - If job is remote OR location matches = good score
  - If neither = low/zero score
```

**Features**:
- Filter jobs by minimum match score threshold
- Rank jobs by score
- Explain why a job matches/doesn't match (e.g., "Remote option satisfies location preference")
- Learn from user feedback (if job was applied to or rejected)

---

### 2.5 Application Tracker (`application_tracker.py`)
**Objective**: Track application status and history

**Features**:
- Record each job application:
  - Job ID, title, company
  - Application date
  - Application method (auto-applied, manual, tailored)
  - Status: "applied", "reviewing", "interview", "rejected", "offer", "withdrawn"
  - Notes field
  - Interview dates/links
  - Offer details
  - Salary negotiation
  - Decision (accepted/rejected)
- Timeline view of applications
- Statistics dashboard:
  - Total applications
  - Response rate
  - Interview rate
  - Offer rate
  - Time to first response
- Export applications to CSV

---

### 2.6 Automation Module (`automation.py`)
**Objective**: Automate repetitive tasks

**Workflows**:

1. **Daily Job Fetch**:
   - Scheduled job to pull jobs from all scrapers
   - Run on timer (e.g., 6 AM daily)
   - Store new jobs in database

2. **Auto-Match & Rank**:
   - Score all new jobs against user profile
   - Identify top matches (>threshold)
   - Generate daily digest report

3. **Auto-Apply Workflow**:
   - Identify high-match jobs (configurable threshold, e.g., >75)
   - Auto-fill applications using Selenium:
     - Pull user info from profile
     - Fill form fields automatically
     - Submit application
     - Log application with timestamp
   - Human-in-the-loop review before actual submission (optional)

4. **Interview Prep**:
   - Extract company info from job description
   - Generate interview questions based on role/tech stack
   - Research company (Glassdoor reviews, website, news)
   - Create prep document

5. **Follow-up Reminder**:
   - Track applications without response
   - Generate follow-up email templates
   - Remind user to follow up after X days

---

## Phase 3: Database Schema

### Tables:

#### `users`
- id (PK)
- name, email, phone, location
- cv_text, cv_parsed_json
- created_at, updated_at

#### `user_preferences`
- id (PK)
- user_id (FK)
- target_titles (JSON)
- target_industries (JSON)
- preferred_locations (JSON)
- salary_min, salary_max
- experience_level
- remote_preference
- contract_types (JSON)

#### `skills`
- id (PK)
- user_id (FK)
- skill_name
- proficiency (1-5)
- category (technical, soft, language)

#### `jobs`
- id (PK)
- source, source_job_id
- title, company, location
- salary_min, salary_max
- remote_type
- description
- requirements (JSON)
- apply_url
- posted_date
- scraped_at
- UNIQUE(source, source_job_id)

#### `job_matches`
- id (PK)
- job_id (FK)
- user_id (FK)
- match_score (0-100)
- skill_score, title_score, etc. (detailed breakdown)
- calculated_at

#### `applications`
- id (PK)
- user_id (FK)
- job_id (FK)
- status (applied, reviewing, interview, rejected, offer, withdrawn)
- application_date
- application_method (auto, manual, tailored)
- notes
- created_at, updated_at

#### `interviews`
- id (PK)
- application_id (FK)
- interview_date
- interview_type (phone, video, in-person)
- interviewer_name
- notes
- result (pending, pass, fail)

#### `offers`
- id (PK)
- application_id (FK)
- salary
- benefits (JSON)
- start_date
- expiration_date
- accepted (boolean)
- notes

---

## Phase 4: CLI Interface

### Commands Structure:

```bash
job-agent --help

# Profile Management
job-agent profile upload CV.md           # Parse CV and create profile
job-agent profile view                   # Display user profile
job-agent profile edit                   # Interactive profile editor
job-agent preferences set                # Set job preferences
job-agent preferences view               # View current preferences

# Job Searching
job-agent jobs search --title "Software Engineer" --location "NYC"
job-agent jobs list --filter "match_score>75" --sort "score"
job-agent jobs view <job_id>             # View job details and match breakdown
job-agent jobs export --format csv       # Export jobs to file

# Applications
job-agent apply <job_id>                 # Apply to a job (interactive)
job-agent apply auto --threshold 75      # Auto-apply to top matches
job-agent applications list              # View application history
job-agent applications status <app_id>   # Check application status
job-agent applications update <app_id> --status interview --notes "..."

# Tracking & Analytics
job-agent stats                          # Show application statistics
job-agent interviews list                # View upcoming interviews
job-agent interviews schedule <app_id> --date "2026-02-20 10:00"

# Automation
job-agent schedule --fetch "0 6 * * *"   # Cron-style schedule for job fetch
job-agent schedule --match "0 7 * * *"   # Schedule job matching
job-agent schedule --list                # View scheduled tasks

# Utilities
job-agent sync                           # Sync all platforms
job-agent config                         # Manage API keys/settings
job-agent export --format json           # Export all data
job-agent clear-cache                    # Clear cached data
```

---

## Phase 5: Workflow

### User Journey:

1. **Initial Setup** (First time):
   - User provides CV file (markdown)
   - System parses CV → extracts skills, experience
   - User sets job preferences (targets, locations, salary)
   - Configure API keys for platforms (LinkedIn, etc.)

2. **Daily Workflow**:
   - System fetches new jobs from all platforms (automated)
   - Jobs are scored against user profile
   - User reviews top matches
   - User can apply manually or approve auto-applications
   - System tracks application status

3. **Interview & Offer Stage**:
   - User logs interview details
   - System tracks follow-ups
   - User receives offer → logs details
   - System helps with negotiation/decision tracking

4. **Analytics**:
   - Regular reports on application success rate
   - Insights on best-matching companies/roles
   - Feedback loop to refine profile

---

## Phase 6: API & Authentication

### Required API Keys/Credentials:
- **LinkedIn**: Official API credentials (or unofficial API)
- **Glassdoor**: API key or web scraping auth
- **GitHub**: GitHub API token (free)
- **Stack Overflow**: API key (free)
- **Additional**: Email credentials for application notifications

### Environment Variables (`.env`):
```
LINKEDIN_API_KEY=xxxxx
LINKEDIN_API_SECRET=xxxxx
GLASSDOOR_API_KEY=xxxxx
GITHUB_TOKEN=xxxxx
STACKOVERFLOW_API_KEY=xxxxx
EMAIL_ADDRESS=user@example.com
EMAIL_PASSWORD=xxxxx (or OAuth token)
DATABASE_PATH=./data/jobs.db
```

---

## Phase 7: Testing Strategy

### Unit Tests:
- CV parser (test with sample CVs)
- User profile creation
- Job scoring algorithm
- Database operations

### Integration Tests:
- End-to-end scraping (mock API calls)
- Job matching pipeline
- Application workflow
- Database transactions

### Mock Data:
- Sample CVs in different formats
- Sample job listings from each platform
- Test user profiles

---

## Implementation Order (Accelerated MVP - Cloud-Ready in 2 Weeks)

### **PHASE 1A: MVP Foundation (Week 1 - Days 1-5)**
Goal: Get core system working locally, ready for AWS deployment

1. **Day 1**: 
   - Setup project structure & dependencies
   - Create local SQLite database schema
   - Implement CV parser (process your CV markdown file)

2. **Day 2**: 
   - User profile management from parsed CV
   - User preferences CLI setup

3. **Day 3**: 
   - Job scraper base class
   - Implement ONE platform scraper (GitHub Jobs - simplest API)
   - Implement ONE company scraper (Microsoft careers.microsoft.com)

4. **Day 4**: 
   - Job matching engine with scoring algorithm
   - Basic application tracker

5. **Day 5**: 
   - Minimal CLI interface (profile upload, jobs search, job view)
   - Local testing with sample data

### **PHASE 1B: AWS Deployment (Week 1 - Days 6-7)**
Goal: Deploy working system to AWS with daily scheduled job fetch

6. **Day 6**:
   - Containerize application (Docker)
   - Create AWS RDS PostgreSQL instance
   - Migrate schema from SQLite to PostgreSQL
   - Setup AWS IAM roles and permissions

7. **Day 7**:
   - Deploy Lambda function for `job_fetch_handler`
   - Deploy Lambda function for `job_match_handler`
   - Create EventBridge rules (daily schedule at 6 AM & 7 AM)
   - Setup CloudWatch monitoring and logs
   - Test end-to-end deployment

### **✅ MVP COMPLETE - Day 7 EOD**
**Running in production with**:
- ✅ Your CV parsed and profiled
- ✅ GitHub Jobs + Microsoft jobs fetched daily
- ✅ Jobs automatically scored and ranked
- ✅ Results stored in cloud database
- ✅ CloudWatch dashboard showing metrics

---

### **PHASE 2: Expand Job Sources (Week 2)**
Goal: Add more job sources while MVP runs in production

1. **Day 8-9**: 
   - Add Glassdoor scraper
   - Add Stack Overflow scraper
   - Add 3 more company portal scrapers (Google, Vodafone, Apple)

2. **Day 10**: 
   - Deploy updated scrapers to AWS Lambda
   - Update EventBridge job fetch handler

3. **Day 11**: 
   - Add CLI commands: `job list --filter`, `job view <id>`, `job export`
   - Add basic application logging (`job-agent apply <job_id>`)

---

### **PHASE 3: Enhanced Features (Weeks 3-4)**
Goal: Add automation and tracking features

1. **Week 3**:
   - Auto-apply workflow (with manual review requirement)
   - Application status tracker
   - Interview scheduling

2. **Week 4**:
   - Email notifications via SES
   - Weekly digest reports
   - Analytics dashboard
   - CLI stats command

---

### **PHASE 4: Polish & Optimization (Week 5)**
Goal: Performance, reliability, advanced features

1. **Duplicate job detection** across multiple sources
2. **Company research integration** (Glassdoor info lookup)
3. **Resume/Cover letter generation** (AI-assisted)
4. **Improved matching algorithm** based on feedback

---

## Fast-Track Checklist (2-Week MVP)

```
WEEK 1 - LOCAL DEVELOPMENT
─────────────────────────
Day 1:
  ☐ Project structure & dependencies
  ☐ SQLite database schema
  ☐ CV parser (parse data/cv.md)
  
Day 2:
  ☐ User profile creation from CV
  ☐ User preferences interactive setup
  
Day 3:
  ☐ Base scraper abstract class
  ☐ GitHub Jobs scraper
  ☐ Microsoft careers scraper
  
Day 4:
  ☐ Job matching engine
  ☐ Application tracker module
  ☐ Unit tests for core modules
  
Day 5:
  ☐ Basic CLI commands (profile, jobs search, jobs view)
  ☐ Local integration testing

WEEK 1 - AWS DEPLOYMENT
──────────────────────
Day 6:
  ☐ Docker image creation & testing
  ☐ AWS RDS PostgreSQL setup
  ☐ Database schema migration (SQLite → PostgreSQL)
  ☐ IAM roles and Secrets Manager setup
  
Day 7:
  ☐ Create job_fetch_handler Lambda function
  ☐ Create job_match_handler Lambda function
  ☐ EventBridge rules (6 AM & 7 AM daily)
  ☐ CloudWatch monitoring setup
  ☐ End-to-end testing in AWS

WEEK 2 - EXPAND & ENHANCE
─────────────────────────
Days 8-9:
  ☐ Glassdoor scraper
  ☐ Stack Overflow scraper
  ☐ Google careers scraper
  ☐ Vodafone careers scraper
  ☐ Apple careers scraper
  
Day 10:
  ☐ Deploy updated Lambda functions
  ☐ Test multi-source aggregation
  
Day 11:
  ☐ Enhanced CLI commands
  ☐ Application logging system
  ☐ Manual review workflow for applications
```

---

## MVP Success Criteria

**By end of Week 1, Day 7**:
- ✅ System running 24/7 on AWS Lambda
- ✅ Daily automated job fetch at 6 AM UTC
- ✅ Daily automated job matching at 7 AM UTC
- ✅ Minimum 2 job sources (GitHub Jobs, Microsoft)
- ✅ 1 company scraper working (Microsoft)
- ✅ CloudWatch logs showing successful runs
- ✅ RDS database populated with jobs
- ✅ Can manually query and review matched jobs

**By end of Week 2, Day 11**:
- ✅ 4+ platform scrapers (GitHub, Glassdoor, Stack Overflow, LinkedIn)
- ✅ 5+ company portal scrapers
- ✅ Daily email digest of top-10 matching jobs
- ✅ CLI to view and apply to jobs
- ✅ Application tracker functional
- ✅ Basic analytics (jobs fetched, matches found, etc.)

---

## Key Shortcuts for Speed

1. **Start with easiest scrapers**: GitHub Jobs has clean API, Microsoft has simple HTML structure
2. **Use Playwright for complex sites**: Rather than building custom scraper, use Playwright for quick HTML parsing
3. **Minimal CLI initially**: Just need to see results, fancy UI comes later
4. **RDS over managed database**: PostgreSQL RDS is easiest to setup and migrate to later
5. **Lambda for everything**: No EC2 to manage, auto-scaling, pay-per-use
6. **Use AWS Secrets Manager**: No need to manage .env files in production
7. **CloudFormation template**: Use IaC from day 1, makes redeployment instant

---

## Development Environment Setup (Day 1)

```bash
# 1. Create local environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Create .env for development
cp .env.example .env
# Fill in test API keys (can use dummy values initially)

# 3. Initialize SQLite for local development
python3 -c "from src.database import init_db; init_db()"

# 4. Parse your CV
python3 -c "from src.cv_parser import parse_cv; parse_cv('data/cv.md')"

# 5. Start building scrapers iteratively
# Each day, add one scraper and test it immediately
```

---

## AWS Deployment (Day 6-7)

```bash
# 1. Create requirements-aws.txt (adds boto3, psycopg2)
pip install -r requirements-aws.txt

# 2. Create Dockerfile
# 3. Build and test locally
docker build -t job-agent:latest .
docker run -e DATABASE_URL=postgresql://... job-agent:latest

# 4. Deploy to AWS
# - Create RDS: 5 minutes
# - Create IAM role: 5 minutes
# - Push to ECR: 2 minutes
# - Create Lambda function: 2 minutes
# - Setup EventBridge: 3 minutes
# - Test: 5 minutes
# TOTAL: ~20 minutes

# 5. Verify running
aws logs tail /aws/lambda/job-fetch-handler --follow
```

---

## Why This Fast Path Works

1. **Parallel Development**: While AWS infra is being provisioned (Day 6), finalize local code
2. **Minimal MVP**: Only 2 job sources initially, add more in Week 2
3. **Database Agnostic Code**: Write queries that work on SQLite and PostgreSQL
4. **Simple Scrapers First**: GitHub Jobs and company portals are easy targets
5. **Lambda Perfect for Batch Jobs**: No need for always-on server
6. **No UI Initially**: Just query results from CLI or cloud logs
7. **Iterate in Production**: Bug fixes deploy in minutes, not hours

---

## After MVP (Weeks 3-5)

Once you have jobs fetching and matching daily, expand with:
- More job sources
- Auto-apply workflow
- Email digests
- Interview tracking
- Resume generation
- Advanced analytics

But the core system will already be **live, automated, and running in the cloud**.

---

## Phase 8: AWS Deployment Strategy

### Architecture Overview
```
┌─────────────────────────────────────────────────┐
│         AWS Cloud Infrastructure               │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │     EventBridge (Scheduled Rules)        │  │
│  │  - Daily job fetch @ 6 AM                │  │
│  │  - Job matching @ 7 AM                   │  │
│  │  - Weekly reports                        │  │
│  └──────────────────────────────────────────┘  │
│           │                                     │
│           ▼                                     │
│  ┌──────────────────────────────────────────┐  │
│  │    AWS Lambda (Job Agent Functions)      │  │
│  │  - job_fetch_handler                     │  │
│  │  - job_match_handler                     │  │
│  │  - auto_apply_handler                    │  │
│  │  - notification_handler                  │  │
│  └──────────────────────────────────────────┘  │
│           │                                     │
│           ├─────────────────┬──────────────────┤
│           │                 │                  │
│           ▼                 ▼                  ▼
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐
│  │ RDS Aurora   │  │   S3 Bucket  │  │  SES/SNS  │
│  │ PostgreSQL   │  │  - CV files  │  │  - Email  │
│  │ - Jobs DB    │  │  - Reports   │  │ Notif.    │
│  │ - Apps DB    │  │  - Logs      │  └───────────┘
│  │ - User DB    │  └──────────────┘
│  └──────────────┘
│
│  ┌──────────────────────────────────────────┐
│  │    CloudWatch (Monitoring & Logs)        │
│  │  - Lambda execution metrics               │
│  │  - Error tracking & alerts                │
│  │  - Cost monitoring                        │
│  └──────────────────────────────────────────┘
│
└─────────────────────────────────────────────────┘
```

### AWS Services Used

#### **AWS Lambda** (Compute)
- Run job scrapers, matching, and automation on serverless functions
- Pay only for execution time (very cost-effective)
- Auto-scaling built-in
- Separate Lambda functions for:
  - `job_fetch_lambda`: Calls all scrapers, stores jobs in RDS
  - `job_match_lambda`: Scores jobs, creates application recommendations
  - `auto_apply_lambda`: Auto-submits applications to high-match jobs
  - `notification_lambda`: Sends email/SMS alerts

#### **AWS RDS (Relational Database)**
- Managed PostgreSQL for production database
- Multi-AZ for high availability
- Automated backups and point-in-time recovery
- Replaces local SQLite with cloud-native database
- Tables: users, user_preferences, skills, jobs, job_matches, applications, interviews, offers

#### **Amazon S3 (Storage)**
- Store CV files (uploaded by users)
- Store exported reports and analytics
- Store application logs and backups
- Lifecycle policies to archive old logs

#### **EventBridge (Scheduling)**
- Replace local cron with AWS EventBridge rules
- Trigger Lambda functions on schedule:
  - `cron(0 6 * * ? *)` → Daily job fetch at 6 AM UTC
  - `cron(0 7 * * ? *)` → Daily job matching at 7 AM UTC
  - `cron(0 9 ? * MON *)` → Weekly summary report every Monday at 9 AM

#### **Amazon SES/SNS (Notifications)**
- **SES**: Send email notifications (new high-match jobs, interview reminders)
- **SNS**: SMS alerts for urgent opportunities
- Both have free tier for initial deployments

#### **CloudWatch (Monitoring)**
- Monitor Lambda execution metrics
- Track errors and failures
- Cost monitoring and budgets
- Create custom dashboards
- Set alarms for failures

#### **IAM (Security)**
- Create roles for Lambda functions with minimal permissions
- Secure API key storage in AWS Secrets Manager
- Manage access to RDS, S3, and other services

### Deployment Options

#### **Option 1: AWS Lambda + RDS (Recommended - Serverless)**
**Pros**:
- No servers to manage
- Auto-scaling
- Pay-per-use pricing (~$1-10/month for light usage)
- EventBridge handles scheduling

**Cons**:
- Lambda has 15-minute timeout (adjust code for long operations)
- Cold start latency (first call slower)

**Cost Estimate**: $2-8/month for typical job search usage

#### **Option 2: EC2 + RDS (Traditional)**
**Pros**:
- Full control over environment
- Better for long-running processes
- Supports all automation features

**Cons**:
- Must manage servers
- Minimum cost ~$15-20/month even if unused
- Higher operational overhead

**Cost Estimate**: $15-30/month

#### **Option 3: ECS (Containerized)**
**Pros**:
- Container-based deployment
- Fargate for serverless containers
- Better than EC2 for scaling

**Cons**:
- More complex setup than Lambda
- Cost varies with usage

**Cost Estimate**: $5-20/month depending on usage

### Deployment Steps (Lambda + RDS)

1. **Prepare Application**:
   ```bash
   # Create Dockerfile for local testing
   # Update code to work with RDS instead of SQLite
   # Add AWS SDK (boto3) to requirements
   ```

2. **Setup AWS Infrastructure**:
   ```bash
   # Create RDS instance (PostgreSQL)
   # Create S3 bucket for files/logs
   # Create Lambda execution role with appropriate permissions
   # Create EventBridge rules for scheduling
   ```

3. **Containerize & Deploy**:
   ```bash
   # Build Docker image
   docker build -t job-agent:latest .
   
   # Push to AWS ECR (Elastic Container Registry)
   aws ecr create-repository --repository-name job-agent
   docker tag job-agent:latest <account>.dkr.ecr.<region>.amazonaws.com/job-agent:latest
   docker push <account>.dkr.ecr.<region>.amazonaws.com/job-agent:latest
   
   # Deploy Lambda function from container image
   ```

4. **Configure Environment**:
   ```bash
   # Store secrets in AWS Secrets Manager
   aws secretsmanager create-secret --name job-agent/api-keys
   
   # Set Lambda environment variables
   # - DATABASE_URL (RDS connection string)
   # - AWS_REGION
   # - LOG_LEVEL
   ```

5. **Setup Monitoring**:
   ```bash
   # Create CloudWatch alarms
   # Create dashboard for job metrics
   # Setup log groups for debugging
   ```

6. **Test & Validate**:
   ```bash
   # Invoke Lambda manually to test
   aws lambda invoke --function-name job-fetch-handler output.json
   
   # Check RDS for job data
   # Verify EventBridge rules are triggering
   ```

### Configuration for AWS Deployment

**Updated .env for AWS**:
```
# AWS Configuration
AWS_REGION=eu-west-1
AWS_ACCOUNT_ID=your-account-id

# RDS Configuration
DATABASE_URL=postgresql://user:password@job-agent-db.xxxxx.eu-west-1.rds.amazonaws.com:5432/job_agent
DATABASE_POOL_SIZE=5

# S3 Configuration
S3_BUCKET_NAME=job-agent-files-{account-id}
S3_REGION=eu-west-1

# API Keys (stored in Secrets Manager)
SECRETS_MANAGER_SECRET_ID=job-agent/api-keys

# Email Configuration (via SES)
SES_SENDER_EMAIL=noreply@job-agent.example.com
SES_REGION=eu-west-1

# Logging
LOG_LEVEL=INFO
CLOUDWATCH_LOG_GROUP=/aws/lambda/job-agent
```

### Infrastructure as Code (IaC)

Use AWS CloudFormation or Terraform for reproducible deployments:

```yaml
# CloudFormation template (job-agent-stack.yaml)
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  JobAgentLambdaRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: JobAgentPolicy
          PolicyDocument:
            Statement:
              - Effect: Allow
                Action:
                  - rds:DescribeDBInstances
                  - s3:GetObject
                  - s3:PutObject
                  - secretsmanager:GetSecretValue
                  - ses:SendEmail
                Resource: '*'
  
  JobAgentDatabase:
    Type: AWS::RDS::DBInstance
    Properties:
      AllocatedStorage: 20
      Engine: postgres
      EngineVersion: 14.6
      DBInstanceClass: db.t3.micro
      MasterUsername: job_agent
      MasterUserPassword: !Sub '{{resolve:secretsmanager:job-agent/db-password:SecretString:password}}'
      StorageEncrypted: true
      MultiAZ: false
      PubliclyAccessible: false
```

### Monitoring & Costs

**CloudWatch Metrics to Track**:
- Lambda execution duration
- Number of jobs fetched per run
- Job matching success rate
- Auto-application success rate
- Error rates and types

**Cost Optimization Tips**:
- Use Lambda for event-driven tasks (most cost-effective)
- Use RDS t3.micro for low traffic (free tier or ~$0.017/hour)
- Enable RDS auto-scaling for storage
- Archive old logs to S3 Glacier
- Set CloudWatch alarms to catch runaway costs

**Typical Monthly Costs**:
- Lambda: $0.20 (1M requests/month free tier)
- RDS t3.micro: $0-15 (free tier available)
- S3: $0.02-0.05 (minimal storage)
- SES: $0.10 (1,000 emails free/month)
- **Total**: $0-20/month depending on usage

---

## Future Enhancements

- **Web Dashboard**: Flask/Django web UI alongside CLI
- **Dynamic Company Portal Management**: Add/remove company portals without code changes via configuration file
- **Company Research Integration**: Pull Glassdoor reviews, company news, salary data for target companies
- **Resume Generation**: Auto-create tailored resumes per job
- **Cover Letter Generation**: AI-powered personalized cover letters
- **Interview Questions**: AI-generated interview prep based on job + tech stack
- **Salary Negotiation**: Provide negotiation insights based on market data and company location
- **Machine Learning**: Improve matching based on user feedback over time
- **Email Integration**: Gmail API for automatic follow-up emails
- **Notification System**: Desktop/email notifications for new opportunities (priority notifications for company portal jobs)
- **Browser Extension**: Quick job saving from any job board
- **Company-Specific Application Tracking**: Monitor application status within company internal systems
- **Insider Referral Tracking**: Track which companies you have internal referrals for

---

## Success Metrics

- ✅ Successfully parse and extract data from user CV
- ✅ Aggregate jobs from 4+ platforms
- ✅ Match jobs with >80% accuracy
- ✅ Auto-apply to high-match jobs
- ✅ Track applications and provide analytics
- ✅ Reduce time spent on job search by 80%
- ✅ Increase application rate by 5x
- ✅ Improve interview-to-apply ratio

---

## Questions for User Review

Before implementing, please confirm:

1. **CV Format**: Should we accept Markdown, PDF, or both initially?
2. **Job Board Priority**: Which platform should we build first? (Suggested: GitHub Jobs for simplicity, then LinkedIn)
3. **Auto-Apply Threshold**: What match score would you like to auto-apply? (Suggested: 75%)
4. **API Keys**: Do you have access to official APIs for the platforms, or should we plan for web scraping?
5. **Interview Tracking**: Any specific interview prep tools you'd like integrated?
6. **Notification Preferences**: Email notifications for new opportunities? (Yes/No)
7. **Resume Customization**: Should we generate tailored resumes/cover letters per job? (Yes/No)

---

**Ready to proceed with Phase 1 setup once you review and approve this plan!**
