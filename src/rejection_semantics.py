"""Reason-driven rejection penalty ("semantic rerank").

A user's "not interested" reason is embedded and compared with every active
job, so that jobs matching the reason score lower for that user only:

* Each distinct reason uses one channel. If the rejected job's location is
  closer to the reason than its title is, it's a location reason ("India
  based") and is compared with job locations; otherwise it's compared with job
  titles ("Internship", "C++").
* Location reasons hit jobs at similarity >= LOCATION_THRESHOLD.
* Title reasons hit only the closest (100 - TITLE_PERCENTILE)% of active jobs,
  and never below TITLE_FLOOR — a short generic reason ("Support Engineer")
  would otherwise hit thousands of jobs.
* Target guard: a title hit is dropped when the job title is at least as close
  to one of the user's own target titles as it is to the reason.

Isolation: job text vectors (titles, locations) are a shared cache because they
describe jobs, not users. A reason vector lives only on its own
``RejectedJob`` row and target-title vectors only on the user's own
``UserPreferences`` row; hits are computed from one user's rows at a time.

Embeddings are *created* only by ``ensure_embeddings()`` (Lambda match phase /
CLI — needs OPENAI_API_KEY). Scoring reads stored vectors only, so it also runs
on the Render API. Anything not yet embedded falls back to the old title
word-overlap penalty, and the user is flagged for a refresh.
"""

import hashlib
import logging
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

import numpy as np
from sqlalchemy.orm import Session

from src import embeddings
from src.embeddings import EMBEDDING_MODEL, from_bytes, to_bytes
from src.models import Job, RejectedJob, TextEmbedding, User, UserPreferences

logger = logging.getLogger("jobhunter.rejection_semantics")

TITLE_FLOOR = 0.60
TITLE_PERCENTILE = 99.5
LOCATION_THRESHOLD = 0.55

_INDEX_KEY = "job_text_index"
_INSERT_CHUNK = 1000

Embedder = Callable[[List[str]], np.ndarray]


def text_hash(text: str) -> str:
    # cache key only, not security
    return hashlib.sha1(text.strip().encode("utf-8"), usedforsecurity=False).hexdigest()


def _clean(text: Optional[str]) -> str:
    return (text or "").strip()


# ---------------------------------------------------------------------------
# Embedding maintenance — Lambda / CLI only
# ---------------------------------------------------------------------------


def ensure_embeddings(
    session: Session, embed: Optional[Embedder] = None
) -> Dict[str, int]:
    """Embed anything scoring needs that isn't stored yet.

    Job titles/locations of active jobs and of rejected jobs go into the shared
    ``text_embeddings`` cache; rejection reasons and target titles are stored on
    their own user's rows. Users whose reason or target vectors change are
    flagged for a penalty refresh.
    """
    embed = embed or embeddings.embed_texts
    counts = {"job_texts": 0, "reasons": 0, "targets": 0}

    # 1. job text (shared cache)
    texts: Set[str] = set()
    active = session.query(Job.title, Job.location).filter(Job.is_active.is_(True))
    rejected = session.query(Job.title, Job.location).join(
        RejectedJob, RejectedJob.job_id == Job.id
    )
    for title, location in list(active) + list(rejected):
        for t in (_clean(title), _clean(location)):
            if t:
                texts.add(t)
    have = {
        h
        for (h,) in session.query(TextEmbedding.text_hash).filter(
            TextEmbedding.model == EMBEDDING_MODEL
        )
    }
    missing = sorted(t for t in texts if text_hash(t) not in have)
    for start in range(0, len(missing), _INSERT_CHUNK):
        chunk = missing[start : start + _INSERT_CHUNK]
        vectors = embed(chunk)
        session.add_all(
            TextEmbedding(
                model=EMBEDDING_MODEL,
                text_hash=text_hash(t),
                text=t,
                vector=to_bytes(v),
            )
            for t, v in zip(chunk, vectors)
        )
        session.commit()
        counts["job_texts"] += len(chunk)

    # 2. rejection reasons (per row)
    pending = [
        r
        for r in session.query(RejectedJob).filter(RejectedJob.reason_vec.is_(None))
        if _clean(r.reason)
    ]
    if pending:
        vectors = embed([_clean(r.reason) for r in pending])
        for row, vec in zip(pending, vectors):
            row.reason_vec = to_bytes(vec)
        _flag_users(session, {r.user_id for r in pending})
        session.commit()
        counts["reasons"] = len(pending)

    # 3. target titles (per user), only for users with a reasoned rejection
    reasoned_users = {
        uid
        for (uid,) in session.query(RejectedJob.user_id)
        .filter(RejectedJob.reason.isnot(None), RejectedJob.reason != "")
        .distinct()
    }
    changed: Set[int] = set()
    if reasoned_users:
        for prefs in session.query(UserPreferences).filter(
            UserPreferences.user_id.in_(reasoned_users)
        ):
            targets = _targets(prefs)
            if prefs.target_titles_vec_source == targets and (
                prefs.target_titles_vec is not None or not targets
            ):
                continue
            prefs.target_titles_vec = (
                to_bytes(np.asarray(embed(targets)).reshape(-1)) if targets else None
            )
            prefs.target_titles_vec_source = targets
            changed.add(prefs.user_id)
    if changed:
        _flag_users(session, changed)
        session.commit()
        counts["targets"] = len(changed)

    if any(counts.values()):
        logger.info("embeddings_updated %s", counts)
    return counts


def _targets(prefs: Optional[UserPreferences]) -> List[str]:
    if not prefs or not prefs.target_titles:
        return []
    return [t for t in (_clean(x) for x in prefs.target_titles) if t]


def _flag_users(session: Session, user_ids: Iterable[int]) -> None:
    ids = list(user_ids)
    if ids:
        session.query(User).filter(User.id.in_(ids)).update(
            {"rejections_updated_at": datetime.utcnow()}, synchronize_session=False
        )


# ---------------------------------------------------------------------------
# Scoring — reads stored vectors only
# ---------------------------------------------------------------------------


class JobTextIndex:
    """Title/location vectors for every active job (job text only)."""

    def __init__(
        self, job_ids: List[int], titles: List[str], locations: List[str], vectors
    ):
        self.vectors: Dict[str, np.ndarray] = vectors
        dim = next(iter(vectors.values())).shape[0] if vectors else 1
        self.job_ids = np.array(job_ids, dtype=np.int64)
        self.row_of = {jid: i for i, jid in enumerate(job_ids)}
        self.title_mat, self.has_title = self._matrix(titles, dim)
        self.loc_mat, self.has_loc = self._matrix(locations, dim)

    def _matrix(self, texts: List[str], dim: int) -> Tuple[np.ndarray, np.ndarray]:
        mat = np.zeros((len(texts), dim), dtype=np.float32)
        has = np.zeros(len(texts), dtype=bool)
        for i, t in enumerate(texts):
            vec = self.vector(t)
            if vec is not None:
                mat[i] = vec
                has[i] = True
        return mat, has

    def vector(self, text: Optional[str]) -> Optional[np.ndarray]:
        t = _clean(text)
        return self.vectors.get(text_hash(t)) if t else None

    @classmethod
    def load(cls, session: Session) -> "JobTextIndex":
        vectors = {
            h: from_bytes(v)
            for h, v in session.query(
                TextEmbedding.text_hash, TextEmbedding.vector
            ).filter(TextEmbedding.model == EMBEDDING_MODEL)
        }
        rows = (
            session.query(Job.id, Job.title, Job.location)
            .filter(Job.is_active.is_(True))
            .order_by(Job.id)
            .all()
        )
        return cls(
            [r.id for r in rows],
            [_clean(r.title) for r in rows],
            [_clean(r.location) for r in rows],
            vectors,
        )


def get_index(session: Session) -> JobTextIndex:
    """Load once per session — every call site scores many users in one session."""
    index = session.info.get(_INDEX_KEY)
    if index is None:
        index = JobTextIndex.load(session)
        session.info[_INDEX_KEY] = index
    return index


def semantic_hits(
    session: Session, user_id: int, index: JobTextIndex
) -> Tuple[Dict[int, List[str]], Set[int], bool]:
    """Jobs this user's reasons hit.

    Returns ``(hits, fallback_ids, degraded)``: ``hits`` maps job id -> matching
    reasons; ``fallback_ids`` are this user's reasoned rejections that couldn't
    be used (no vectors yet) and should use title word overlap instead;
    ``degraded`` is True when anything had to fall back.
    """
    rows = (
        session.query(
            RejectedJob.id,
            RejectedJob.reason,
            RejectedJob.reason_vec,
            Job.title,
            Job.location,
        )
        .join(Job, Job.id == RejectedJob.job_id)
        .filter(RejectedJob.user_id == user_id)
        .all()
    )
    reasoned = [r for r in rows if _clean(r.reason)]
    if not reasoned:
        return {}, set(), False

    prefs = (
        session.query(UserPreferences)
        .filter(UserPreferences.user_id == user_id)
        .first()
    )
    targets = _targets(prefs)
    target_mat = None
    if targets:
        if prefs.target_titles_vec is None or prefs.target_titles_vec_source != targets:
            # Guard can't be applied correctly yet — don't penalise semantically.
            return {}, {r.id for r in reasoned}, True
        target_mat = from_bytes(prefs.target_titles_vec).reshape(len(targets), -1)

    by_reason: Dict[str, list] = {}
    fallback: Set[int] = set()
    for r in reasoned:
        if r.reason_vec is None or index.vector(r.title) is None:
            fallback.add(r.id)
            continue
        by_reason.setdefault(_clean(r.reason), []).append(r)

    hits: Dict[int, List[str]] = {}
    if not by_reason or not len(index.job_ids):
        return hits, fallback, bool(fallback)

    target_sim = (
        (index.title_mat @ target_mat.T).max(axis=1) if target_mat is not None else None
    )
    for reason, group in sorted(by_reason.items()):
        vec = from_bytes(group[0].reason_vec)
        title_sims = [float(vec @ index.vector(r.title)) for r in group]
        loc_vecs = [index.vector(r.location) for r in group]
        loc_sims = [float(vec @ v) for v in loc_vecs if v is not None]
        if loc_sims and max(loc_sims) > max(title_sims):
            sims = index.loc_mat @ vec
            hit = index.has_loc & (sims >= LOCATION_THRESHOLD)
        else:
            sims = index.title_mat @ vec
            valid = index.has_title
            if not valid.any():
                continue
            cutoff = max(
                TITLE_FLOOR, float(np.percentile(sims[valid], TITLE_PERCENTILE))
            )
            hit = valid & (sims >= cutoff)
            if target_sim is not None:
                hit &= target_sim < sims
        for job_id in index.job_ids[hit]:
            hits.setdefault(int(job_id), []).append(reason)
    return hits, fallback, bool(fallback)


__all__ = [
    "JobTextIndex",
    "ensure_embeddings",
    "get_index",
    "semantic_hits",
    "text_hash",
]
