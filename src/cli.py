"""CLI interface for job hunting agent."""

from datetime import datetime, timedelta
from typing import List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.database import get_session, init_db
from src.job_matcher import compute_match_for_user
from src.job_scrapers.github_scraper import GitHubJobsScraper
from src.job_scrapers.microsoft_scraper import MicrosoftScraper
from src.metrics import get_metrics_summary
from src.models import Job, User
from src.prometheus_exporter import create_exporter
from src.user_profile import UserProfile
from src.worker import setup_signal_handlers, start_worker

console = Console()


@click.group()
def cli() -> None:
    """Job Hunting Agent - Automated job search and application tracker."""
    pass


@cli.command()
def init() -> None:
    """Initialize the database."""
    try:
        init_db()
        console.print("[green]✓[/green] Database initialized successfully")
    except Exception as e:
        console.print(f"[red]✗[/red] Error initializing database: {e}")
        raise


@cli.group()
def profile() -> None:
    """Manage user profile and preferences."""
    pass


@profile.command()
@click.argument("cv_file", type=click.Path(exists=True))
@click.option(
    "--titles",
    multiple=True,
    prompt=False,
    help="Target job titles (comma-separated)",
)
@click.option(
    "--industries",
    multiple=True,
    prompt=False,
    help="Target industries (comma-separated)",
)
@click.option(
    "--locations",
    multiple=True,
    prompt=False,
    help="Preferred job locations (comma-separated)",
)
@click.option(
    "--salary-min",
    type=float,
    default=None,
    help="Minimum desired salary",
)
@click.option(
    "--salary-max",
    type=float,
    default=None,
    help="Maximum desired salary",
)
@click.option(
    "--experience",
    type=click.Choice(["Junior", "Mid", "Senior", "Lead"], case_sensitive=False),
    default=None,
    help="Experience level",
)
@click.option(
    "--remote",
    type=click.Choice(["onsite", "hybrid", "remote"], case_sensitive=False),
    default=None,
    help="Remote preference",
)
@click.option(
    "--contracts",
    multiple=True,
    prompt=False,
    help="Contract types (comma-separated)",
)
@click.option(
    "--interactive",
    is_flag=True,
    default=False,
    help="Use interactive mode for preferences",
)
def upload(
    cv_file: str,
    titles: tuple,
    industries: tuple,
    locations: tuple,
    salary_min: Optional[float],
    salary_max: Optional[float],
    experience: Optional[str],
    remote: Optional[str],
    contracts: tuple,
    interactive: bool,
) -> None:
    """Upload and parse CV file.

    Example:
        job-agent profile upload data/cv.md --titles "Software Engineer"
    """
    session = get_session()
    profile_manager = UserProfile(session)

    try:
        # Use interactive mode if requested
        if interactive:
            (
                titles,
                industries,
                locations,
                salary_min,
                salary_max,
                (
                    experience,
                    remote,
                    contracts,
                ),
            ) = _prompt_preferences()

        # Convert tuples to lists and handle comma-separated values
        target_titles = _parse_list_input(titles)
        target_industries = _parse_list_input(industries)
        preferred_locations = _parse_list_input(locations)
        contract_types = _parse_list_input(contracts)

        # Create profile
        user = profile_manager.create_profile_from_cv(
            cv_file_path=cv_file,
            target_titles=target_titles if target_titles else None,
            target_industries=target_industries if target_industries else None,
            preferred_locations=(preferred_locations if preferred_locations else None),
            salary_min=salary_min,
            salary_max=salary_max,
            experience_level=experience,
            remote_preference=remote,
            contract_types=contract_types if contract_types else None,
        )

        # Display success message with user info
        console.print(Panel("[green]✓ Profile Created[/green]", title="Success"))
        console.print(f"  Name: {user.name}")
        console.print(f"  Title: {user.title}")
        console.print(f"  Location: {user.location}")

        if target_titles:
            console.print(f"  Target Titles: {', '.join(target_titles)}")
        if target_industries:
            console.print(f"  Industries: {', '.join(target_industries)}")
        if preferred_locations:
            console.print(f"  Locations: {', '.join(preferred_locations)}")
        if salary_min or salary_max:
            salary_range = f"${salary_min:,.0f}" if salary_min else "?"
            salary_range += f" - ${salary_max:,.0f}" if salary_max else ""
            console.print(f"  Salary Range: {salary_range}")
        if experience:
            console.print(f"  Experience Level: {experience}")
        if remote:
            console.print(f"  Remote: {remote}")

    except FileNotFoundError as e:
        console.print(f"[red]✗[/red] File not found: {e}")
        raise
    except ValueError as e:
        console.print(f"[red]✗[/red] Invalid input: {e}")
        raise
    except Exception as e:
        console.print(f"[red]✗[/red] Error uploading profile: {e}")
        raise
    finally:
        session.close()


@profile.command()
@click.option(
    "--user-id",
    type=int,
    default=None,
    help="User ID (defaults to first user)",
)
def show(user_id: Optional[int]) -> None:
    """Show user profile and preferences."""
    session = get_session()
    profile_manager = UserProfile(session)

    try:
        # Get user
        if user_id:
            user = profile_manager.get_user(user_id)
        else:
            users = profile_manager.list_users()
            user = users[0] if users else None

        if not user:
            console.print("[red]✗[/red] No user profile found")
            return

        # Display user info
        console.print(Panel(f"[bold]{user.name}[/bold]", title="User Profile"))
        console.print(f"  ID: {user.id}")
        console.print(f"  Title: {user.title}")
        console.print(f"  Location: {user.location}")
        console.print(f"  Created: {user.created_at}")

        # Display preferences
        prefs = profile_manager.get_user_preferences(user.id)
        if prefs:
            console.print("\n[bold]Preferences:[/bold]")
            if prefs["target_titles"]:
                console.print(f"  Target Titles: {', '.join(prefs['target_titles'])}")
            if prefs["target_industries"]:
                console.print(f"  Industries: {', '.join(prefs['target_industries'])}")
            if prefs["preferred_locations"]:
                console.print(f"  Locations: {', '.join(prefs['preferred_locations'])}")
            if prefs["salary_min"] or prefs["salary_max"]:
                salary_range = (
                    f"${prefs['salary_min']:,.0f}" if prefs["salary_min"] else "?"
                )
                salary_range += (
                    f" - ${prefs['salary_max']:,.0f}" if prefs["salary_max"] else ""
                )
                console.print(f"  Salary Range: {salary_range}")
            if prefs["experience_level"]:
                console.print(f"  Experience Level: {prefs['experience_level']}")
            if prefs["remote_preference"]:
                console.print(f"  Remote: {prefs['remote_preference']}")
            if prefs["contract_types"]:
                console.print(f"  Contracts: {', '.join(prefs['contract_types'])}")

    except Exception as e:
        console.print(f"[red]✗[/red] Error retrieving profile: {e}")
        raise
    finally:
        session.close()


@profile.command(name="list")
def list_users_cmd() -> None:
    """List all user profiles."""
    session = get_session()
    profile_manager = UserProfile(session)

    try:
        users = profile_manager.list_users()
        if not users:
            console.print("[yellow]No user profiles found[/yellow]")
            return

        # Create table
        table = Table(title="User Profiles")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="magenta")
        table.add_column("Title", style="green")
        table.add_column("Location")

        for user in users:
            table.add_row(
                str(user.id), user.name, user.title or "N/A", user.location or "N/A"
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] Error listing profiles: {e}")
        raise
    finally:
        session.close()


def _prompt_preferences() -> tuple:
    """Prompt user for preferences interactively.

    Returns:
        Tuple of (titles, industries, locations, salary_min, salary_max,
                 (experience, remote, contracts))
    """
    console.print("\n[bold]Enter your job preferences:[/bold]")

    # Target titles
    titles_input = console.input(
        "[yellow]Target job titles[/yellow] (comma-separated): "
    )
    titles = tuple(t.strip() for t in titles_input.split(",") if t.strip())

    # Industries
    industries_input = console.input(
        "[yellow]Target industries[/yellow] (comma-separated): "
    )
    industries = tuple(i.strip() for i in industries_input.split(",") if i.strip())

    # Locations
    locations_input = console.input(
        "[yellow]Preferred locations[/yellow] (comma-separated): "
    )
    locations = tuple(
        location.strip() for location in locations_input.split(",") if location.strip()
    )

    # Salary
    salary_min_str = console.input(
        "[yellow]Minimum salary[/yellow] (leave blank to skip): "
    )
    salary_min = float(salary_min_str) if salary_min_str else None

    salary_max_str = console.input(
        "[yellow]Maximum salary[/yellow] (leave blank to skip): "
    )
    salary_max = float(salary_max_str) if salary_max_str else None

    # Experience level
    experience = console.input(
        "[yellow]Experience level[/yellow] (Junior/Mid/Senior/Lead): "
    )

    # Remote preference
    remote = console.input(
        "[yellow]Remote preference[/yellow] (onsite/hybrid/remote): "
    )

    # Contract types
    contracts_input = console.input(
        "[yellow]Contract types[/yellow] (comma-separated): "
    )
    contracts = tuple(c.strip() for c in contracts_input.split(",") if c.strip())

    return (
        titles,
        industries,
        locations,
        salary_min,
        salary_max,
        (
            experience or None,
            remote or None,
            contracts,
        ),
    )


def _parse_list_input(items: tuple) -> List[str]:
    """Parse list input from CLI, handling comma-separated values.

    Args:
        items: Tuple of input items

    Returns:
        List of parsed items
    """
    result: List[str] = []
    for item in items:
        # Handle comma-separated values
        parts = item.split(",")
        result.extend(p.strip() for p in parts if p.strip())
    return result


@cli.command()
@click.option(
    "--user-id",
    type=int,
    default=None,
    help="User ID to run matches for (defaults to all users)",
)
@click.option(
    "--min-score",
    type=float,
    default=0.0,
    help="Only report matches with score >= MIN_SCORE",
)
def match(user_id: Optional[int], min_score: float) -> None:
    """Compute job match scores for users against available jobs."""
    session = get_session()

    try:
        # Load users and optionally filter
        if user_id:
            users = session.query(User).filter(User.id == user_id).all()
        else:
            users = session.query(User).all()

        if not users:
            console.print("[yellow]No users found to match[/yellow]")
            return

        jobs = session.query(Job).all()
        if not jobs:
            console.print("[yellow]No jobs available to match[/yellow]")
            return

        processed = 0
        accepted = 0
        for user in users:
            for job in jobs:
                jm = compute_match_for_user(session, job, user)
                processed += 1
                if jm.match_score >= min_score:
                    accepted += 1

        console.print(
            f"[green]✓[/green] Matches processed: {processed}; accepted: {accepted}"
        )

    except Exception as e:
        console.print(f"[red]✗[/red] Error running matches: {e}")
        raise
    finally:
        session.close()


@cli.command()
@click.option(
    "--sources",
    multiple=True,
    default=("github", "microsoft"),
    help="Sources to scrape (defaults to github,microsoft)",
)
@click.option(
    "--keywords",
    multiple=True,
    help="Keywords to search for when supported by the scraper",
)
@click.option("--max-retries", type=int, default=3, help="Max fetch retries")
@click.option("--backoff", type=float, default=1.0, help="Backoff factor seconds")
def scrape(sources: tuple, keywords: tuple, max_retries: int, backoff: float) -> None:
    """Run scrapers for configured sources and persist new jobs."""
    session = get_session()

    try:
        source_map = {
            "github": GitHubJobsScraper,
            "microsoft": MicrosoftScraper,
        }

        selected = [s.lower() for s in sources]
        total_new = 0

        for src_name in selected:
            cls = source_map.get(src_name)
            if not cls:
                console.print(f"[yellow]Skipping unknown source: {src_name}[/yellow]")
                continue

            scraper = cls(session)

            # If scraper supports scrape_by_keywords and keywords were provided, use it.
            try:
                if keywords and hasattr(scraper, "scrape_by_keywords"):
                    count = scraper.scrape_by_keywords(list(keywords))
                    total_new += count
                else:
                    jobs = scraper.scrape(
                        max_retries=max_retries, backoff_factor=backoff
                    )
                    total_new += len(jobs)

                console.print(
                    f"[green]✓[/green] {src_name}: new jobs added: {total_new}"
                )

            except Exception as e:
                console.print(f"[red]✗[/red] Error scraping {src_name}: {e}")

        console.print(
            f"[green]✓[/green] Scraping completed. Total new jobs: {total_new}"
        )

    finally:
        session.close()


@cli.command()
@click.option(
    "--scrape-cron",
    default="0 */6 * * *",
    help="Cron expression for scraping (default every 6 hours)",
)
@click.option(
    "--match-cron",
    default="0 */12 * * *",
    help="Cron expression for matching (default every 12 hours)",
)
def worker(scrape_cron: str, match_cron: str) -> None:
    """Start the background job worker for periodic scraping and matching.

    Example:
        job-agent worker --scrape-cron "*/30 * * * *" --match-cron "0 2 * * *"
    """
    try:
        console.print(
            f"[cyan]Starting job-agent worker...[/cyan]\n"
            f"  Scrape schedule: {scrape_cron}\n"
            f"  Match schedule: {match_cron}"
        )

        scheduler = start_worker(
            scrape_cron=scrape_cron,
            match_cron=match_cron,
            daemonize=True,
        )
        del scheduler  # Scheduler is managed in background
        setup_signal_handlers()

        console.print("\n[green]✓[/green] Worker started. Press Ctrl+C to stop.\n")

        # Block forever
        import time

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        console.print("[yellow]Worker stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]✗[/red] Error starting worker: {e}")
        raise


@cli.command()
@click.option("--source", type=str, default=None, help="Filter metrics by source name")
@click.option(
    "--hours", type=int, default=24, help="Lookback window in hours (default 24)"
)
def metrics(source: Optional[str], hours: int) -> None:
    """Show summarized scraper metrics.

    Examples:
        job-agent metrics
        job-agent metrics --source github --hours 48
    """
    session = get_session()
    try:
        since = datetime.utcnow() - timedelta(hours=hours) if hours else None
        rows = get_metrics_summary(session, since=since, source=source)

        if not rows:
            console.print("[yellow]No metrics found for given filters[/yellow]")
            return

        table = Table(title="Scraper Metrics")
        table.add_column("Source", style="cyan")
        table.add_column("Action", style="magenta")
        table.add_column("Rows", justify="right")
        table.add_column("Value", justify="right")

        for src, action, cnt, val in rows:
            table.add_row(str(src), str(action), str(cnt), str(val))

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] Error querying metrics: {e}")
        raise
    finally:
        session.close()


@cli.command()
@click.option(
    "--port", type=int, default=8000, help="Port for Prometheus exporter (default 8000)"
)
def prometheus(port: int) -> None:
    """Start Prometheus metrics exporter server.

    Exposes scraper metrics on http://localhost:PORT/metrics

    Example:
        job-agent prometheus --port 9090
    """
    try:
        from prometheus_client import start_http_server

        # Create and register collector
        create_exporter()

        # Start HTTP server
        start_http_server(port)
        console.print(f"[green]✓[/green] Prometheus exporter started on port {port}")
        console.print(f"  Metrics URL: http://localhost:{port}/metrics")
        console.print("\n[yellow]Press Ctrl+C to stop[/yellow]\n")

        # Block forever
        import time

        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        console.print("[yellow]Exporter stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]✗[/red] Error starting Prometheus exporter: {e}")
        raise


if __name__ == "__main__":
    cli()
