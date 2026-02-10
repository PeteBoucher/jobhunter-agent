# Job Hunter Agent - Deployment Guide

## Systemd Service (Linux)

### Prerequisites
- Python 3.10+
- Virtual environment set up at `/opt/jobhunter-agent/.venv`
- Non-root user `jobhunter` with permissions to `/opt/jobhunter-agent`

### Installation

1. Copy service files to systemd:
```bash
sudo cp systemd/jobhunter-worker.service /etc/systemd/system/
sudo cp systemd/jobhunter-prometheus.service /etc/systemd/system/
sudo systemctl daemon-reload
```

2. Enable and start services:
```bash
sudo systemctl enable jobhunter-worker.service
sudo systemctl enable jobhunter-prometheus.service
sudo systemctl start jobhunter-worker.service
sudo systemctl start jobhunter-prometheus.service
```

3. Check status:
```bash
sudo systemctl status jobhunter-worker.service
sudo systemctl status jobhunter-prometheus.service
```

4. View logs:
```bash
sudo journalctl -u jobhunter-worker.service -f
sudo journalctl -u jobhunter-prometheus.service -f
```

## Docker Compose

### Prerequisites
- Docker & Docker Compose installed

### Quick Start

1. Build and start services:
```bash
docker-compose up -d
```

2. Verify services are running:
```bash
docker-compose ps
```

3. Check logs:
```bash
docker-compose logs -f worker
docker-compose logs -f prometheus-exporter
```

4. Access Prometheus UI:
   - http://localhost:9091

5. Access job-agent metrics:
   - http://localhost:9090/metrics

### Configuration

Edit `docker-compose.yml` to customize:
- Database credentials
- Scraping schedules (via `--scrape-cron` and `--match-cron`)
- Port mappings
- Resource limits

### PostgreSQL Database

By default, Docker Compose uses PostgreSQL. To use SQLite instead:
```bash
# Edit docker-compose.yml and change DATABASE_URL to:
# DATABASE_URL: sqlite:////data/jobs.db
# Mount a volume for /data/
```

## Manual Deployment

### Option 1: Direct Python Execution

```bash
cd /path/to/jobhunter-agent
source .venv/bin/activate

# Run worker in background
python -m src.cli worker &

# Run Prometheus exporter in background
python -m src.cli prometheus --port 9090 &
```

### Option 2: Supervisor

Create `/etc/supervisor/conf.d/jobhunter.conf`:
```ini
[program:jobhunter-worker]
directory=/opt/jobhunter-agent
command=/opt/jobhunter-agent/.venv/bin/python -m src.cli worker
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/jobhunter-worker.log

[program:jobhunter-prometheus]
directory=/opt/jobhunter-agent
command=/opt/jobhunter-agent/.venv/bin/python -m src.cli prometheus --port 9090
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/jobhunter-prometheus.log
```

Then:
```bash
sudo supervisorctl reread
sudo supervisorctl update
sudo supervisorctl start jobhunter-worker
sudo supervisorctl start jobhunter-prometheus
```

## Prometheus Integration

### Add job-agent metrics to Prometheus config (`prometheus.yml`):

```yaml
global:
  scrape_interval: 30s
  evaluation_interval: 30s

scrape_configs:
  - job_name: jobhunter-metrics
    static_configs:
      - targets: ['localhost:9090']
```

### Common Prometheus Queries

```promql
# Total scraper events
jobhunter_scraper_events_total

# GitHub scraper success rate
increase(jobhunter_scraper_events_total{source="github",action="fetch_success"}[1h])

# Jobs added per source
increase(jobhunter_scraper_events_total{action="jobs_added"}[1h]) by (source)
```

## Health Checks

### Worker Health

```bash
# Check if worker is running
job-agent metrics --hours 1

# Should show recent fetch_attempt, jobs_parsed, and jobs_added events
```

### Prometheus Exporter Health

```bash
curl http://localhost:9090/metrics

# Should return Prometheus-formatted metrics
```

## Troubleshooting

### Worker not scraping
- Check DATABASE_URL environment variable is set correctly
- Check permissions on database file
- Review worker logs: `journalctl -u jobhunter-worker.service -n 50`

### Prometheus exporter not responding
- Check port 9090 is available
- Verify database connection: `sqlite:///./data/jobs.db` or PostgreSQL URL
- Check firewall rules if remote access needed

### High CPU/Memory
- Reduce scraping frequency (increase `--scrape-cron` interval)
- Limit job retention with database cleanup job
- Monitor metrics at http://localhost:9090/metrics

## Database Backup

For production deployments using PostgreSQL:
```bash
# Backup
pg_dump -U jobhunter -d jobhunter > backup.sql

# Restore
psql -U jobhunter -d jobhunter < backup.sql
```

## Updates

To deploy a new version:
```bash
# Systemd
sudo systemctl stop jobhunter-worker.service
sudo systemctl stop jobhunter-prometheus.service
# Update code
sudo systemctl start jobhunter-worker.service
sudo systemctl start jobhunter-prometheus.service

# Docker Compose
docker-compose down
# Update code
docker-compose up -d
```
