"""Data export functionality for jobs and applications."""

import csv
import json
from typing import List

from sqlalchemy.orm import Session

from src.models import Application, Job


class DataExporter:
    """Export job and application data in multiple formats."""

    def __init__(self, session: Session):
        """Initialize data exporter.

        Args:
            session: SQLAlchemy database session
        """
        self.session = session

    def export_jobs_csv(self, jobs: List[Job], filepath: str) -> None:
        """Export jobs to CSV file.

        Args:
            jobs: List of jobs to export
            filepath: Path to write CSV file
        """
        if not jobs:
            raise ValueError("No jobs to export")

        fieldnames = [
            "id",
            "source",
            "title",
            "company",
            "location",
            "remote",
            "salary_min",
            "salary_max",
            "description",
            "apply_url",
            "posted_date",
            "match_score",
            "requirements",
            "company_industry",
            "company_size",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for job in jobs:
                writer.writerow(
                    {
                        "id": job.id,
                        "source": job.source,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "remote": job.remote or "",
                        "salary_min": job.salary_min or "",
                        "salary_max": job.salary_max or "",
                        "description": (job.description or "")[:500],  # Truncate
                        "apply_url": job.apply_url or "",
                        "posted_date": job.posted_date.isoformat()
                        if job.posted_date
                        else "",
                        "match_score": (
                            max((jm.match_score or 0) for jm in job.job_matches)
                            if getattr(job, "job_matches", None)
                            else 0
                        ),
                        "requirements": ",".join(job.requirements or []),
                        "company_industry": job.company_industry or "",
                        "company_size": job.company_size or "",
                    }
                )

    def export_jobs_json(self, jobs: List[Job], filepath: str) -> None:
        """Export jobs to JSON file.

        Args:
            jobs: List of jobs to export
            filepath: Path to write JSON file
        """
        if not jobs:
            raise ValueError("No jobs to export")

        data = []
        for job in jobs:
            data.append(
                {
                    "id": job.id,
                    "source": job.source,
                    "title": job.title,
                    "company": job.company,
                    "location": job.location,
                    "remote": job.remote,
                    "salary_min": job.salary_min,
                    "salary_max": job.salary_max,
                    "description": job.description,
                    "apply_url": job.apply_url,
                    "posted_date": job.posted_date.isoformat()
                    if job.posted_date
                    else None,
                    "match_score": (
                        max((jm.match_score or 0) for jm in job.job_matches)
                        if getattr(job, "job_matches", None)
                        else None
                    ),
                    "requirements": job.requirements or [],
                    "nice_to_haves": job.nice_to_haves or [],
                    "company_industry": job.company_industry,
                    "company_size": job.company_size,
                    "source_type": job.source_type,
                    "source_job_id": job.source_job_id,
                }
            )

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def export_applications_csv(
        self, applications: List[Application], filepath: str
    ) -> None:
        """Export applications to CSV file.

        Args:
            applications: List of applications to export
            filepath: Path to write CSV file
        """
        if not applications:
            raise ValueError("No applications to export")

        fieldnames = [
            "job_id",
            "job_title",
            "company",
            "status",
            "application_date",
            "interview_date",
            "rejection_reason",
            "notes",
            "created_at",
            "updated_at",
        ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for app in applications:
                writer.writerow(
                    {
                        "job_id": app.job_id,
                        "job_title": app.job.title if app.job else "",
                        "company": app.job.company if app.job else "",
                        "status": app.status,
                        "application_date": app.application_date.isoformat()
                        if app.application_date
                        else "",
                        "interview_date": app.interview_date.isoformat()
                        if getattr(app, "interview_date", None)
                        else "",
                        "rejection_reason": getattr(app, "rejection_reason", "") or "",
                        "notes": app.notes or "",
                        "created_at": app.created_at.isoformat(),
                        "updated_at": app.updated_at.isoformat(),
                    }
                )

    def export_applications_json(
        self, applications: List[Application], filepath: str
    ) -> None:
        """Export applications to JSON file.

        Args:
            applications: List of applications to export
            filepath: Path to write JSON file
        """
        if not applications:
            raise ValueError("No applications to export")

        data = []
        for app in applications:
            data.append(
                {
                    "job_id": app.job_id,
                    "job_title": app.job.title if app.job else None,
                    "company": app.job.company if app.job else None,
                    "status": app.status,
                    "application_date": app.application_date.isoformat()
                    if app.application_date
                    else None,
                    "interview_date": app.interview_date.isoformat()
                    if getattr(app, "interview_date", None)
                    else None,
                    "rejection_reason": getattr(app, "rejection_reason", None),
                    "notes": app.notes,
                    "created_at": app.created_at.isoformat(),
                    "updated_at": app.updated_at.isoformat(),
                }
            )

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)

    def export_to_file(
        self,
        data: List,
        filepath: str,
        data_type: str = "jobs",
        format: str = "json",
    ) -> None:
        """Export data to file with auto-format detection.

        Args:
            data: List of data objects to export
            filepath: Path to write file
            data_type: Type of data ('jobs' or 'applications')
            format: Export format ('json' or 'csv')

        Raises:
            ValueError: If format or data_type is invalid
        """
        if format == "json":
            if data_type == "jobs":
                self.export_jobs_json(data, filepath)
            elif data_type == "applications":
                self.export_applications_json(data, filepath)
            else:
                raise ValueError(f"Unknown data type: {data_type}")
        elif format == "csv":
            if data_type == "jobs":
                self.export_jobs_csv(data, filepath)
            elif data_type == "applications":
                self.export_applications_csv(data, filepath)
            else:
                raise ValueError(f"Unknown data type: {data_type}")
        else:
            raise ValueError(f"Unknown format: {format}")
