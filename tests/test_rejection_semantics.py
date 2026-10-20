"""Tests for the reason-driven rejection penalty (src/rejection_semantics.py)."""

import re
import tempfile
import zlib

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src import rejection_semantics as rs
from src.job_matcher import (
    _SEMANTIC_REJECTION_PENALTY,
    compute_match_for_user,
    refresh_rejection_penalties,
)
from src.job_rejections import reject_job, unreject_job
from src.models import (
    Base,
    Job,
    JobMatch,
    RejectedJob,
    TextEmbedding,
    User,
    UserPreferences,
)

DIM = 512


def fake_embed(texts):
    """Bag-of-words vectors: cosine similarity = word overlap, predictably."""
    out = np.zeros((len(texts), DIM), dtype=np.float32)
    for i, text in enumerate(texts):
        for word in re.findall(r"[a-z+]+", text.lower()):
            out[i, zlib.crc32(word.encode()) % DIM] += 1.0
    norms = np.linalg.norm(out, axis=1, keepdims=True)
    return out / np.where(norms == 0, 1.0, norms)


class CountingEmbed:
    def __init__(self):
        self.calls = []

    def __call__(self, texts):
        self.calls.append(list(texts))
        return fake_embed(texts)


@pytest.fixture
def session():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        engine = create_engine(f"sqlite:///{f.name}")
        Base.metadata.create_all(engine)
        s = sessionmaker(bind=engine)()
        yield s
        s.close()


@pytest.fixture(autouse=True)
def loose_title_cutoff(monkeypatch):
    """With a handful of test jobs the 99.5th percentile is ~the max sim, which
    would hide every behaviour but "exact match". Tests opt back in below."""
    monkeypatch.setattr(rs, "TITLE_PERCENTILE", 0.0)


def _user(session, name, targets=None):
    user = User(name=name)
    session.add(user)
    session.flush()
    if targets is not None:
        session.add(UserPreferences(user_id=user.id, target_titles=targets))
    session.commit()
    return user


def _job(session, title, location=None, company="Acme"):
    job = Job(title=title, location=location, company=company, source="test")
    session.add(job)
    session.commit()
    return job


def _score(session, user, job):
    return compute_match_for_user(session, job, user)


def _fresh(session):
    """Drop per-session/per-user caches, as a new Lambda run would."""
    session.info.pop("job_text_index", None)
    session.expire_all()
    for user in session.query(User):
        user.__dict__.pop("_rejection_signals", None)


# ---------------------------------------------------------------------------
# ensure_embeddings
# ---------------------------------------------------------------------------


def test_ensure_embeddings_stores_vectors_where_they_belong(session):
    alice = _user(session, "Alice", targets=["QA Automation"])
    rejected = _job(session, "Finance Internship", "Milan")
    _job(session, "Backend Engineer", "Madrid")
    reject_job(session, alice.id, rejected.id, reason="Internship")

    counts = rs.ensure_embeddings(session, embed=fake_embed)

    cached = {t.text for t in session.query(TextEmbedding)}
    assert cached == {"Finance Internship", "Milan", "Backend Engineer", "Madrid"}
    # user-entered text never lands in the shared cache
    assert "Internship" not in cached and "QA Automation" not in cached
    row = session.query(RejectedJob).one()
    assert row.reason_vec is not None
    prefs = session.query(UserPreferences).one()
    assert prefs.target_titles_vec_source == ["QA Automation"]
    assert counts == {"job_texts": 4, "reasons": 1, "targets": 1}


def test_ensure_embeddings_is_incremental(session):
    alice = _user(session, "Alice")
    rejected = _job(session, "Finance Internship")
    reject_job(session, alice.id, rejected.id, reason="Internship")
    rs.ensure_embeddings(session, embed=fake_embed)

    embed = CountingEmbed()
    rs.ensure_embeddings(session, embed=embed)
    assert embed.calls == []

    _job(session, "Data Engineer")
    rs.ensure_embeddings(session, embed=embed)
    assert embed.calls == [["Data Engineer"]]


def test_changing_a_reason_clears_its_vector_and_flags_the_user(session):
    alice = _user(session, "Alice")
    job = _job(session, "Finance Internship")
    reject_job(session, alice.id, job.id, reason="Internship")
    rs.ensure_embeddings(session, embed=fake_embed)
    alice.rejections_updated_at = None
    session.commit()

    reject_job(session, alice.id, job.id, reason="Student job")

    session.expire_all()
    assert session.query(RejectedJob).one().reason_vec is None
    assert session.get(User, alice.id).rejections_updated_at is not None


def test_unreject_flags_the_user(session):
    alice = _user(session, "Alice")
    job = _job(session, "Finance Internship")
    reject_job(session, alice.id, job.id)
    alice.rejections_updated_at = None
    session.commit()

    unreject_job(session, alice.id, job.id)

    session.expire_all()
    assert session.get(User, alice.id).rejections_updated_at is not None


# ---------------------------------------------------------------------------
# semantic hits
# ---------------------------------------------------------------------------


def test_title_reason_hits_matching_titles_only(session):
    alice = _user(session, "Alice")
    rejected = _job(session, "Consulting Intern Internship", "Milan")
    intern = _job(session, "Finance Internship", "Madrid")
    backend = _job(session, "Backend Engineer", "Madrid")
    reject_job(session, alice.id, rejected.id, reason="Internship")
    rs.ensure_embeddings(session, embed=fake_embed)

    hits, fallback, degraded = rs.semantic_hits(
        session, alice.id, rs.get_index(session)
    )

    assert intern.id in hits and hits[intern.id] == ["Internship"]
    assert backend.id not in hits
    assert not fallback and not degraded


def test_location_reason_compares_locations_not_titles(session):
    """'India based' must hit jobs in India, not jobs with the rejected title."""
    alice = _user(session, "Alice")
    rejected = _job(session, "Kotlin Backend Engineer", "India")
    in_india = _job(session, "Product Manager", "India")
    same_title = _job(session, "Kotlin Backend Engineer", "Madrid")
    reject_job(session, alice.id, rejected.id, reason="India based")
    rs.ensure_embeddings(session, embed=fake_embed)

    hits, _, _ = rs.semantic_hits(session, alice.id, rs.get_index(session))

    assert in_india.id in hits
    assert same_title.id not in hits


def test_target_titles_guard_wins_ties(session):
    alice = _user(session, "Alice", targets=["Test Engineer"])
    rejected = _job(session, "Support Engineer")
    plain = _job(session, "Support Engineer Desk")
    near_target = _job(session, "Test Support Engineer")
    reject_job(session, alice.id, rejected.id, reason="Support Engineer")
    rs.ensure_embeddings(session, embed=fake_embed)

    hits, _, _ = rs.semantic_hits(session, alice.id, rs.get_index(session))

    assert plain.id in hits
    assert near_target.id not in hits  # as close to her target as to the reason


def test_percentile_cap_limits_generic_reasons(session, monkeypatch):
    monkeypatch.setattr(rs, "TITLE_PERCENTILE", 75.0)
    alice = _user(session, "Alice")
    rejected = _job(session, "Support Engineer")
    exact = _job(session, "Support Engineer")
    for title in ("Software Engineer", "Data Engineer", "Platform Engineer"):
        _job(session, title)
    reject_job(session, alice.id, rejected.id, reason="Support Engineer")
    rs.ensure_embeddings(session, embed=fake_embed)

    hits, _, _ = rs.semantic_hits(session, alice.id, rs.get_index(session))

    # "Engineer" alone gives every title 0.5+ similarity; only the closest survive
    assert exact.id in hits
    assert all(session.get(Job, j).title == "Support Engineer" for j in hits)


def test_missing_vectors_fall_back_to_word_overlap(session):
    """Before the match phase has embedded a new reason, scoring degrades to
    today's title word overlap instead of ignoring the rejection."""
    alice = _user(session, "Alice")
    rejected = _job(session, "Senior Backend Engineer")
    similar = _job(session, "Senior Backend Engineer", company="Other")
    reject_job(session, alice.id, rejected.id, reason="Too senior")  # never embedded

    jm = _score(session, alice, similar)

    assert 0 < jm.rejection_penalty < _SEMANTIC_REJECTION_PENALTY
    assert alice._rejection_signals["degraded"] is True


def test_reasoned_rejection_drops_word_overlap(session):
    """A reason says *why*: 'Mexico based' mustn't hit that title elsewhere."""
    alice = _user(session, "Alice")
    rejected = _job(session, "Scrum Master", "Mexico")
    elsewhere = _job(session, "Scrum Master", "Madrid")
    reject_job(session, alice.id, rejected.id, reason="Mexico based")
    rs.ensure_embeddings(session, embed=fake_embed)

    assert _score(session, alice, elsewhere).rejection_penalty == 0


# ---------------------------------------------------------------------------
# isolation + refresh
# ---------------------------------------------------------------------------


def _scored_pair(session):
    alice = _user(session, "Alice")
    bob = _user(session, "Bob")
    rejected = _job(session, "Consulting Internship")
    intern = _job(session, "Finance Internship")
    other = _job(session, "Backend Engineer")
    for user in (alice, bob):
        for job in (intern, other):
            _score(session, user, job)
    return alice, bob, rejected, intern, other


def _scores(session, user):
    session.expire_all()
    return {
        m.job_id: (m.match_score, m.rejection_penalty)
        for m in session.query(JobMatch).filter(JobMatch.user_id == user.id)
    }


def test_one_users_reasons_never_change_another_users_scores(session):
    alice, bob, rejected, intern, other = _scored_pair(session)
    bob_before = _scores(session, bob)

    reject_job(session, alice.id, rejected.id, reason="Internship")
    rs.ensure_embeddings(session, embed=fake_embed)
    _fresh(session)
    refreshed = refresh_rejection_penalties(session)

    assert set(refreshed) == {alice.id}
    assert _scores(session, bob) == bob_before
    assert rs.semantic_hits(session, bob.id, rs.get_index(session))[0] == {}
    # and new scoring for Bob is unaffected too
    assert _score(session, session.get(User, bob.id), intern).rejection_penalty == 0


def test_refresh_rescores_existing_matches_once(session):
    alice, bob, rejected, intern, other = _scored_pair(session)
    before = _scores(session, alice)

    reject_job(session, alice.id, rejected.id, reason="Internship")
    rs.ensure_embeddings(session, embed=fake_embed)
    _fresh(session)
    assert refresh_rejection_penalties(session) == {alice.id: 1}

    after = _scores(session, alice)
    assert after[intern.id][1] == _SEMANTIC_REJECTION_PENALTY
    assert after[intern.id][0] == pytest.approx(
        max(0.0, before[intern.id][0] - _SEMANTIC_REJECTION_PENALTY)
    )
    assert after[other.id] == before[other.id]

    _fresh(session)
    assert refresh_rejection_penalties(session) == {}  # nothing changed since


def test_unreject_removes_the_penalty_on_refresh(session):
    alice, bob, rejected, intern, other = _scored_pair(session)
    reject_job(session, alice.id, rejected.id, reason="Internship")
    rs.ensure_embeddings(session, embed=fake_embed)
    _fresh(session)
    refresh_rejection_penalties(session)

    unreject_job(session, alice.id, rejected.id)
    _fresh(session)
    refresh_rejection_penalties(session)

    assert _scores(session, alice)[intern.id][1] == 0


def test_degraded_refresh_stays_flagged(session):
    alice, bob, rejected, intern, other = _scored_pair(session)
    reject_job(session, alice.id, rejected.id, reason="Internship")  # no vectors
    _fresh(session)

    refresh_rejection_penalties(session)

    session.expire_all()
    assert session.get(User, alice.id).rejection_penalty_refreshed_at is None
