#!/usr/bin/env python3
"""Backfill CV skill extraction for users who have cv_text but no skills.

Run this after adding ANTHROPIC_API_KEY to Render (or locally against Neon):

    DATABASE_URL=<neon-url> ANTHROPIC_API_KEY=<key> python scripts/backfill_cv_skills.py

Dry-run (parse but don't save):

    DATABASE_URL=<neon-url> ANTHROPIC_API_KEY=<key> \
        python scripts/backfill_cv_skills.py --dry-run
"""

import argparse
import logging
import sys
from pathlib import Path

# Make src.* and web/api/* importable from the repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web" / "api"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("backfill")


def main(dry_run: bool = False) -> None:
    from sqlalchemy.orm import sessionmaker

    from src.database import create_engine_instance
    from src.models import User, UserPreferences
    from src.user_profile import UserProfile

    engine = create_engine_instance()
    Session = sessionmaker(bind=engine)
    db = Session()

    try:
        # Users with cv_text but no skills
        users_with_cv = (
            db.query(User).filter(User.cv_text.isnot(None), User.cv_text != "").all()
        )

        candidates = [u for u in users_with_cv if len(u.skills) == 0]
        logger.info(
            "Found %d users with CV text, %d have no skills",
            len(users_with_cv),
            len(candidates),
        )

        if not candidates:
            logger.info("Nothing to do.")
            return

        from cv_parser_llm import parse_cv_with_llm

        from src.cv_parser import CVParser

        for user in candidates:
            logger.info("Processing user_id=%d email=%s", user.id, user.email)

            # Try regex parser first
            parsed = CVParser(user.cv_text).parse()

            _info = parsed.get("personal_info", {})
            _skills = parsed.get("skills", {})
            _total = sum(len(v) for v in _skills.values() if isinstance(v, list))
            _poor = (
                not _info.get("name")
                or not _info.get("title")
                or not _info.get("location")
                or _total < 3
            )

            if _poor:
                logger.info("  regex gave %d skills + poor parse, trying LLM…", _total)
                llm_result = parse_cv_with_llm(user.cv_text)
                if llm_result:
                    parsed = llm_result
                    new_total = sum(
                        len(v)
                        for v in parsed.get("skills", {}).values()
                        if isinstance(v, list)
                    )
                    logger.info("  LLM extracted %d skills", new_total)
                else:
                    logger.warning("  LLM also failed, skipping user")
                    continue
            else:
                logger.info("  regex extracted %d skills", _total)

            skills_data = parsed.get("skills", {})
            if not any(skills_data.values()):
                logger.warning("  no skills in parsed result, skipping")
                continue

            if dry_run:
                names = [
                    name
                    for lst in skills_data.values()
                    if isinstance(lst, list)
                    for name in lst
                ]
                logger.info("  [dry-run] would add: %s", names[:10])
                continue

            # Update personal info if we got better data
            personal = parsed.get("personal_info", {})
            if personal.get("title") and not user.title:
                user.title = personal["title"]
            if personal.get("location") and not user.location:
                user.location = personal["location"]
            user.cv_parsed_json = parsed

            # Ensure preferences row exists
            prefs = db.query(UserPreferences).filter_by(user_id=user.id).first()
            if not prefs:
                prefs = UserPreferences(user_id=user.id)
                db.add(prefs)
                db.flush()

            profile_manager = UserProfile(db)
            profile_manager._sync_skills_from_cv(user, skills_data)
            profile_manager._auto_populate_preferences(prefs, parsed)
            db.commit()

            skill_count = len(user.skills)
            logger.info("  saved %d skills for %s", skill_count, user.email)

        logger.info("Done.")

    except Exception:
        logger.exception("Backfill failed")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse CVs but don't write to the database",
    )
    args = parser.parse_args()
    main(dry_run=args.dry_run)
