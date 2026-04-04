from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from career_scout_ai.storage.dedup import (
    DedupResult,
    check_duplicate,
    compute_content_hash,
)
from career_scout_ai.storage.models import Base, JobListing


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


class TestComputeContentHash:
    def test_same_input_same_hash(self):
        h1 = compute_content_hash("Data Scientist", "Acme", "Build models")
        h2 = compute_content_hash("Data Scientist", "Acme", "Build models")
        assert h1 == h2

    def test_case_insensitive(self):
        h1 = compute_content_hash("Data Scientist", "ACME", "build models")
        h2 = compute_content_hash("data scientist", "acme", "Build Models")
        assert h1 == h2

    def test_strips_whitespace(self):
        h1 = compute_content_hash("Data Scientist", "Acme", "desc")
        h2 = compute_content_hash("  Data Scientist  ", "  Acme  ", "  desc  ")
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = compute_content_hash("Data Scientist", "Acme", "desc A")
        h2 = compute_content_hash("Data Engineer", "Acme", "desc A")
        assert h1 != h2

    def test_none_description(self):
        h1 = compute_content_hash("Title", "Company", None)
        h2 = compute_content_hash("Title", "Company", None)
        assert h1 == h2

    def test_none_vs_empty_description_same(self):
        h1 = compute_content_hash("Title", "Company", None)
        h2 = compute_content_hash("Title", "Company", "")
        assert h1 == h2


class TestCheckDuplicate:
    def test_new_when_empty_db(self):
        session = _make_session()
        result = check_duplicate(session, "https://example.com/job/1", "abc123")
        assert result == DedupResult.NEW

    def test_skip_url_when_url_exists(self):
        session = _make_session()
        session.add(
            JobListing(
                portal="test",
                url="https://example.com/job/1",
                title="DS",
                company="Acme",
                content_hash="hash1",
                is_duplicate=False,
            )
        )
        session.commit()

        result = check_duplicate(session, "https://example.com/job/1", "different_hash")
        assert result == DedupResult.SKIP_URL

    def test_skip_hash_when_hash_exists(self):
        session = _make_session()
        session.add(
            JobListing(
                portal="test",
                url="https://example.com/job/1",
                title="DS",
                company="Acme",
                content_hash="same_hash",
                is_duplicate=False,
            )
        )
        session.commit()

        result = check_duplicate(session, "https://example.com/job/2", "same_hash")
        assert result == DedupResult.SKIP_HASH

    def test_url_check_takes_priority_over_hash(self):
        session = _make_session()
        session.add(
            JobListing(
                portal="test",
                url="https://example.com/job/1",
                title="DS",
                company="Acme",
                content_hash="same_hash",
                is_duplicate=False,
            )
        )
        session.commit()

        result = check_duplicate(session, "https://example.com/job/1", "same_hash")
        assert result == DedupResult.SKIP_URL
