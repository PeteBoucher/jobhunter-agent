# Jobhunter — Project Plan

## What it is

An automated job search and application tracking system. It continuously scrapes relevant opportunities across 20+ company and ATS sources, scores them against a user's CV and preferences using a 5-dimension matching algorithm, and tracks the full lifecycle from discovery through to offer.

**Primary user**: a job-seeker who wants to eliminate the manual grind of monitoring multiple job boards.

---

## Current state (August 2026)

### Done

#### Infrastructure

- AWS Lambda scraper (EventBridge every 6h, prod) writing directly to Neon PostgreSQL
- Two-phase Lambda execution: scrape phase → async self-invoke → match phase, each with full 600s budget
- `ReservedConcurrentExecutions: 1` prevents overlap; `MaximumRetryAttempts: 0` stops spurious retries
- GitHub Actions CI/CD: lint → test → deploy Lambda (SAM) + Render (FastAPI) + Vercel (Next.js) on every push to master
- QEMU arm64 emulation on amd64 CI runners for cross-platform Lambda Docker build
- Multi-user support: each user gets their own `JobMatch` rows; matching budget split evenly across profiled users
- Stale job expiry: jobs not re-seen in 30 days marked `is_active=False` and hidden from feed
- SNS match notifications at ≥70% score, filtered by user's `preferred_countries` (remote jobs bypass filter)
- Grafana Cloud observability: Lambda logs via CloudWatch, FastAPI logs via Loki push

#### Web app

- Google OAuth sign-in (next-auth), open sign-up — no approval gate
- Job feed with personalised match scores; score breakdown per-dimension
- Applications kanban board (Saved → Applied → Interview → Offer / Rejected)
- CV upload (markdown, PDF, DOCX) with LLM skill extraction and automatic re-scoring
- Preferences: target titles, salary, remote preference, preferred countries, city-level locations
- AI content generation: cover letter, tailored CV, recruiter message (Claude Haiku via `jobhunter-ai`)
- Mobile layout: bottom nav, responsive feed
- Vercel frontend pinned to `lhr1` (London); Render API in Frankfurt; Neon in London

#### Scrapers (active in DEFAULT_SOURCES)

| Source | Type | Notable companies |
| --- | --- | --- |
| Greenhouse | ATS platform | Anthropic, Cloudflare, Airbnb, Figma, Adyen, Ebury, Lottoland, Kambi, Cabify, and ~20 more |
| Lever | ATS platform | Palantir, Spotify, and more |
| Ashby | ATS platform | OpenAI, Notion, Deel, ElevenLabs, Synthesia, Cursor, Perplexity, Mollie, and ~30 more |
| Workday | ATS platform | Accenture (500), GSK (500), Adobe (500), AstraZeneca (500), Airbus (500), Maersk (500), BP (400), Unilever (400), Shell (200), Solera (250), Betway, Flutter |
| SmartRecruiters | ATS platform | Bet365, Playtech, Evolution, Sportradar, EPAM, Ciklum |
| BambooHR | ATS platform | Various |
| Teamtailor | ATS platform | Oatly, Hedvig, Storytel, The Workshop (Málaga) |
| Recruitee | ATS platform | Zoi, bunq, Keolis, Pret A Manger, Livestorm, Van Cranenbroek, Woonzorg Flevoland, Betty Blocks, CM.com, Greenpeace CEE, Sircle Collection, Solutions 4 Delivery, Trusted Shops — career-site-builder product; some on custom domains (`meet.zoi.tech`, `careers.bunq.com`), most on `{company}.recruitee.com` |
| Workable | ATS platform | Rentokil Initial; public `apply.workable.com/{slug}` API, no auth |
| DeJobs | ATS/job-board platform | `{slug}.dejobs.org` microsites, shared Solr search API across tenants |
| Jobboardly | White-label job board | Multi-tenant, `{subdomain}.jobboardly.com`; jobs link out to each company's own ATS |
| Adzuna | Aggregator | 13 countries; terms and countries from user preferences |
| The Muse | Job board | Curated tech companies |
| Reed | Job board | UK; API key required |
| Thoughtworks | Direct | |
| BCG | Direct | Boston Consulting Group |
| Coinbase | Direct | |
| Revolut | Direct | |
| Coderland | Direct | Manatal ATS; LATAM staffing company |
| Indra Group | Direct | Spanish IT/defense; SAP SuccessFactors HTML scrape, no public API |
| Innova-IRV | Direct | Microelectronics research institute, Málaga |
| TKH Security | Direct | Netherlands; WordPress wombat-career plugin HTML scrape |
| Experis | Direct | ManpowerGroup IT staffing/consulting (Spain); confirmed live JSON API |

#### Matching algorithm

```text
score = (skill_match × 0.35) + (title_match × 0.25) + (experience_match × 0.15)
      + (location_or_remote_match × 0.15) + (salary_match × 0.10)
```

- **Skill match**: substring/token coverage of job requirements against CV skills
- **Title match**: Jaccard word overlap + SequenceMatcher ratio against each target title (best wins)
- **Experience match**: seniority level comparison
- **Location/remote**: OR relationship — remote preference match OR city substring match
- **Salary match**: gradient — job salary vs user minimum

Score maxima served from API; frontend never hardcodes weights.

---

## Roadmap

### Near-term (next few weeks)

- **More Teamtailor companies** — many European tech companies use Teamtailor; adding a new board is one line in `DEFAULT_BOARDS`
- **More Workday portals** — proven pattern; any company on Workday can be added with slug + portal name
- **More Ashby/Greenhouse boards** — low-effort additions; both APIs are public and auth-free
- **Score quality improvements** — the 31-application CSV review identified gaps in title and domain matching; more rounds of profile tuning will improve signal

### Medium-term

- **Email digest** — weekly summary of top matches instead of (or alongside) per-match SNS push
- **Match score explanations** — show users specifically which skills/titles drove the score
- **Saved searches** — let users save keyword + filter combos, re-run on schedule
- **Company watchlist** — notify when a watched company posts anything new, regardless of score

### Future / exploratory

- **Auto-apply workflow** — `jobhunter-ai` already has `apply_to_job` and `auto_apply_jobs`; needs `AUTO_APPLY_ENABLED=true` and platform-specific form automation
- **Interview prep** — generate company-specific prep notes from job description + company info
- **Application email parsing** — ingest Gmail to auto-update kanban status (rejection / interview invite)
- **Recruiter outreach tracking** — log LinkedIn messages and follow-ups in the kanban
- **Multi-language CV matching** — Spanish-language roles score poorly if CV is English-only

---

## Known limitations / tech debt

- **Adzuna circuit breaker**: after 3 consecutive non-200s for a country, remaining terms are skipped; some countries (Singapore, India) are flaky
- **LinkedIn excluded**: guest endpoint blocks Lambda IPs and scraping violates ToS
- **DEKRA / Keysight not scrapable**: SAP SuccessFactors requires OAuth; iCIMS is JS-rendered with no public API
- **Coderland low volume**: 16 jobs, LATAM-focused; useful for monitoring but unlikely to yield many matches
- **Local DB schema drift**: the local SQLite dev DB may be missing columns added via `ALTER TABLE` on Neon; always use `DATABASE_URL` pointing at prod or a recent dump for realistic testing
- **`MAX_MATCH_PER_RUN = 5000`**: as more users provision profiles, the per-user budget shrinks; revisit if matching lags start appearing in logs

---

## Service topology

| Service | Region | Notes |
| --- | --- | --- |
| Neon (PostgreSQL) | `aws-eu-west-2` (London) | Primary database |
| AWS Lambda | `eu-west-1` (Ireland) | ~10ms from Neon |
| Render (FastAPI) | `eu-central` (Frankfurt) | ~20ms from Neon |
| Vercel Functions | `lhr1` (London) | Pinned in `vercel.json` — do not remove |

ECR: `624372908505.dkr.ecr.eu-west-1.amazonaws.com/jobhunter`

Lambda stacks:

| Stack | S3 bucket | Schedule |
| --- | --- | --- |
| `jobhunter-dev` | `jobhunter-data-dev` | Disabled |
| `jobhunter-prod` | `jobhunter-data-prod` | Every 6h |
