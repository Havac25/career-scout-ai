from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from career_scout_ai.config import AppConfig
from career_scout_ai.llm import ScoringResult
from career_scout_ai.scoring.engine import ScoringEngine
from career_scout_ai.storage.models import AgentScore, Base, JobListing


@pytest.fixture
def db_session():
    """Create an in-memory SQLite database with tables."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    session = factory()
    yield session
    session.close()


@pytest.fixture
def sample_offers(db_session: Session) -> list[JobListing]:
    """Insert sample offers into the test DB."""
    offers = [
        JobListing(
            portal="justjoinit",
            url="https://justjoin.it/offers/1",
            title="Senior ML Engineer",
            company="AcmeCorp",
            location_raw="Warsaw",
            workplace_type="remote",
            contract_types="b2b",
            salary_raw="25000-35000 PLN",
            description_raw="Build ML models at scale.",
            content_hash="hash1",
            is_duplicate=False,
            scraped_at=datetime(2026, 6, 10),
        ),
        JobListing(
            portal="nofluffjobs",
            url="https://nofluffjobs.com/offers/2",
            title="Data Analyst",
            company="BigCo",
            location_raw="Kraków",
            workplace_type="office",
            contract_types="permanent",
            salary_raw="10000-15000 PLN",
            description_raw="SQL dashboards and reports.",
            content_hash="hash2",
            is_duplicate=False,
            scraped_at=datetime(2026, 6, 10),
        ),
        JobListing(
            portal="justjoinit",
            url="https://justjoin.it/offers/3",
            title="Duplicate Offer",
            company="DupCorp",
            location_raw="Warsaw",
            content_hash="hash3",
            is_duplicate=True,
            scraped_at=datetime(2026, 6, 10),
        ),
    ]
    db_session.add_all(offers)
    db_session.commit()
    return offers


@pytest.fixture
def config(tmp_path) -> AppConfig:
    """Create config with temp agents dir and profile."""
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "best_recommendations.md").write_text(
        "Score AI/ML offers highly. Reject junior roles."
    )

    profile_path = tmp_path / "profile.md"
    profile_path.write_text("Senior Data Scientist, 8 years experience in ML.")

    return AppConfig(
        agents_dir=agents_dir,
        profile_path=profile_path,
        openrouter_api_key="test-key",
        openrouter_model="google/gemini-2.5-flash-preview-05-20",
    )


class TestGetUnscoredOffers:
    def test_returns_non_duplicate_unscored(
        self, db_session: Session, sample_offers, config
    ):
        with patch.object(ScoringEngine, "__init__", lambda self, *a, **kw: None):
            engine = ScoringEngine.__new__(ScoringEngine)
            engine.config = config

        offers = engine._get_unscored_offers(db_session, "best_recommendations")
        # Should return 2 (non-duplicate), not the duplicate one
        assert len(offers) == 2
        titles = {o.title for o in offers}
        assert "Senior ML Engineer" in titles
        assert "Data Analyst" in titles
        assert "Duplicate Offer" not in titles

    def test_excludes_already_scored(self, db_session: Session, sample_offers, config):
        # Score the first offer
        score = AgentScore(
            job_listing_id=sample_offers[0].id,
            agent_name="best_recommendations",
            score=0.9,
            summary="Great fit",
            scored_at=datetime.now(),
            model_name="google/gemini-2.5-flash-preview-05-20",
        )
        db_session.add(score)
        db_session.commit()

        with patch.object(ScoringEngine, "__init__", lambda self, *a, **kw: None):
            engine = ScoringEngine.__new__(ScoringEngine)
            engine.config = config

        offers = engine._get_unscored_offers(db_session, "best_recommendations")
        assert len(offers) == 1
        assert offers[0].title == "Data Analyst"

    def test_different_agent_sees_all_unscored(
        self, db_session: Session, sample_offers, config
    ):
        # Score first offer for "best_recommendations" agent
        score = AgentScore(
            job_listing_id=sample_offers[0].id,
            agent_name="best_recommendations",
            score=0.9,
            summary="Great fit",
            scored_at=datetime.now(),
            model_name="google/gemini-2.5-flash-preview-05-20",
        )
        db_session.add(score)
        db_session.commit()

        with patch.object(ScoringEngine, "__init__", lambda self, *a, **kw: None):
            engine = ScoringEngine.__new__(ScoringEngine)
            engine.config = config

        # A different agent should still see the first offer as unscored
        offers = engine._get_unscored_offers(db_session, "another_agent")
        assert len(offers) == 2


class TestDiscoverAgents:
    def test_finds_agents(self, config):
        with (
            patch.object(ScoringEngine, "_load_profile", return_value="profile"),
            patch("career_scout_ai.scoring.engine.OpenRouterClient"),
        ):
            engine = ScoringEngine(config)

        assert len(engine.agents) == 1
        assert engine.agents[0].name == "best_recommendations"

    def test_empty_dir(self, tmp_path, config):
        empty_dir = tmp_path / "empty_agents"
        empty_dir.mkdir()
        config_copy = AppConfig(
            agents_dir=empty_dir,
            profile_path=config.profile_path,
        )

        with (
            patch.object(ScoringEngine, "_load_profile", return_value="profile"),
            patch("career_scout_ai.scoring.engine.OpenRouterClient"),
        ):
            engine = ScoringEngine(config_copy)

        assert len(engine.agents) == 0


class TestScoreNewOffers:
    def test_scores_offers_end_to_end(self, db_session: Session, sample_offers, config):
        mock_result = ScoringResult(score=0.85, summary="Strong ML fit")

        with (
            patch.object(ScoringEngine, "_load_profile", return_value="profile"),
            patch(
                "career_scout_ai.scoring.engine.OpenRouterClient"
            ) as mock_client_class,
        ):
            mock_client = mock_client_class.return_value
            mock_client.is_available.return_value = True
            mock_client.score_offer.return_value = mock_result
            engine = ScoringEngine(config)
            engine.client = mock_client

        results = engine.score_new_offers(db_session)

        assert len(results) == 1
        result = results[0]
        assert result.agent_name == "best_recommendations"
        assert result.scored == 2
        assert result.skipped == 0

        # Verify scores were stored in DB
        scores = db_session.query(AgentScore).all()
        assert len(scores) == 2
        assert all(s.score == 0.85 for s in scores)

    def test_skips_when_client_unavailable(
        self, db_session: Session, sample_offers, config
    ):
        with (
            patch.object(ScoringEngine, "_load_profile", return_value="profile"),
            patch(
                "career_scout_ai.scoring.engine.OpenRouterClient"
            ) as mock_client_class,
        ):
            mock_client = mock_client_class.return_value
            mock_client.is_available.return_value = False
            engine = ScoringEngine(config)
            engine.client = mock_client

        results = engine.score_new_offers(db_session)
        assert results == []

        # No scores stored
        scores = db_session.query(AgentScore).all()
        assert len(scores) == 0
