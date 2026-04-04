import hashlib
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from career_scout_ai.storage.models import JobListing


class DedupResult(StrEnum):
    NEW = "new"
    SKIP_URL = "skip_url"
    SKIP_HASH = "skip_hash"


def compute_content_hash(
    title: str,
    company: str,
    description: str | None,
) -> str:
    parts = [
        title.strip().lower(),
        company.strip().lower(),
        (description or "").strip().lower(),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def check_duplicate(session: Session, url: str, content_hash: str) -> DedupResult:
    url_exists = session.scalar(
        select(JobListing.id).where(JobListing.url == url).limit(1)
    )
    if url_exists is not None:
        return DedupResult.SKIP_URL

    hash_exists = session.scalar(
        select(JobListing.id).where(JobListing.content_hash == content_hash).limit(1)
    )
    if hash_exists is not None:
        return DedupResult.SKIP_HASH

    return DedupResult.NEW
