"""SQLAlchemy models for Jobhunter Agent database."""
# mypy: ignore-errors

from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class User(Base):
    """User profile with CV data."""

    __tablename__ = "user"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    location = Column(String(255))
    title = Column(String(255))
    cv_text = Column(String)  # Raw CV text
    cv_parsed_json = Column(JSON)  # Parsed structured data
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    preferences = relationship("UserPreferences", uselist=False, back_populates="user")
    skills = relationship("Skill", back_populates="user", cascade="all, delete-orphan")
    jobs_applied = relationship("Application", back_populates="user")


class UserPreferences(Base):
    """User job preferences."""

    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), unique=True)
    target_titles = Column(JSON)  # List of target job titles
    target_industries = Column(JSON)  # List of industries
    preferred_locations = Column(JSON)  # List of locations
    salary_min = Column(Float)
    salary_max = Column(Float)
    experience_level = Column(String(50))  # Junior, Mid, Senior, Lead
    remote_preference = Column(String(20))  # onsite, hybrid, remote
    contract_types = Column(JSON)  # Full-time, Part-time, Contract
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="preferences")


class Skill(Base):
    """User skills with proficiency levels."""

    __tablename__ = "skills"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    skill_name = Column(String(255))
    proficiency = Column(Integer)  # 1-5 scale
    category = Column(String(50))  # technical, soft, language

    user = relationship("User", back_populates="skills")


class Job(Base):
    """Job listing from any source."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True)
    source = Column(String(50))  # linkedin, glassdoor, github, stackoverflow, etc.
    source_job_id = Column(String(255))  # External job ID
    title = Column(String(255))
    company = Column(String(255))
    department = Column(String(255))
    location = Column(String(255))
    remote = Column(String(20))  # onsite, hybrid, remote
    salary_min = Column(Float)
    salary_max = Column(Float)
    description = Column(String)
    requirements = Column(JSON)  # List of requirements
    nice_to_haves = Column(JSON)
    apply_url = Column(String(500))
    posted_date = Column(DateTime)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    company_industry = Column(String(255))
    company_size = Column(String(50))
    source_type = Column(String(20), default="aggregator")  # aggregator, company_portal

    job_matches = relationship(
        "JobMatch", back_populates="job", cascade="all, delete-orphan"
    )
    applications = relationship("Application", back_populates="job")


class JobMatch(Base):
    """Job match scoring against user profile."""

    __tablename__ = "job_matches"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    user_id = Column(Integer, ForeignKey("user.id"))
    match_score = Column(Float)  # 0-100
    skill_score = Column(Float)
    title_score = Column(Float)
    experience_score = Column(Float)
    location_or_remote_score = Column(Float)
    salary_score = Column(Float)
    calculated_at = Column(DateTime, default=datetime.utcnow)

    job = relationship("Job", back_populates="job_matches")


class Application(Base):
    """Job application tracking."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"))
    job_id = Column(Integer, ForeignKey("jobs.id"))
    status = Column(
        String(50)
    )  # applied, reviewing, interview, rejected, offer, withdrawn
    application_date = Column(DateTime)
    application_method = Column(String(50))  # auto, manual, tailored
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="jobs_applied")
    job = relationship("Job", back_populates="applications")
    interviews = relationship("Interview", back_populates="application")
    offers = relationship("Offer", back_populates="application")


class Interview(Base):
    """Interview tracking."""

    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    interview_date = Column(DateTime)
    interview_type = Column(String(50))  # phone, video, in-person
    interviewer_name = Column(String(255))
    notes = Column(String)
    result = Column(String(50))  # pending, pass, fail

    application = relationship("Application", back_populates="interviews")


class Offer(Base):
    """Job offer tracking."""

    __tablename__ = "offers"

    id = Column(Integer, primary_key=True)
    application_id = Column(Integer, ForeignKey("applications.id"))
    salary = Column(Float)
    benefits = Column(JSON)
    start_date = Column(DateTime)
    expiration_date = Column(DateTime)
    accepted = Column(Integer, default=0)  # 0 = pending, 1 = accepted, -1 = rejected
    notes = Column(String)

    application = relationship("Application", back_populates="offers")
