from datetime import datetime

from career_scout_ai.scoring.prompts import (
    SYSTEM_PROMPT_PREFIX,
    _format_offer,
    build_system_prompt,
    build_user_prompt,
)
from career_scout_ai.storage.models import JobListing


def _make_offer(**kwargs) -> JobListing:
    """Create a minimal JobListing for testing."""
    defaults = {
        "id": 1,
        "portal": "justjoinit",
        "url": "https://example.com/job/1",
        "title": "Senior ML Engineer",
        "company": "AcmeCorp",
        "location_raw": "Warsaw, Poland",
        "workplace_type": "remote",
        "contract_types": "b2b, permanent",
        "salary_raw": "25000-35000 PLN",
        "description_raw": "We are looking for a Senior ML Engineer...",
        "posted_at": datetime(2026, 6, 1),
        "scraped_at": datetime(2026, 6, 10),
        "content_hash": "abc123",
        "is_duplicate": False,
    }
    defaults.update(kwargs)
    offer = JobListing()
    for k, v in defaults.items():
        setattr(offer, k, v)
    return offer


class TestBuildSystemPrompt:
    def test_includes_prefix(self):
        prompt = build_system_prompt("Score AI offers highly.")
        assert prompt.startswith(SYSTEM_PROMPT_PREFIX)

    def test_includes_agent_content(self):
        agent_content = "Focus on PyTorch and Transformers roles."
        prompt = build_system_prompt(agent_content)
        assert agent_content in prompt


class TestBuildUserPrompt:
    def test_includes_profile(self):
        profile = "I am a Senior Data Scientist with 8 years of experience."
        offer = _make_offer()
        prompt = build_user_prompt(profile, offer)
        assert profile in prompt

    def test_includes_offer_title(self):
        offer = _make_offer(title="Lead AI Researcher")
        prompt = build_user_prompt("profile text", offer)
        assert "Lead AI Researcher" in prompt

    def test_includes_offer_company(self):
        offer = _make_offer(company="OpenAI")
        prompt = build_user_prompt("profile text", offer)
        assert "OpenAI" in prompt

    def test_includes_salary(self):
        offer = _make_offer(salary_raw="30000-45000 PLN")
        prompt = build_user_prompt("profile text", offer)
        assert "30000-45000 PLN" in prompt

    def test_includes_description(self):
        offer = _make_offer(description_raw="Build cutting-edge LLMs")
        prompt = build_user_prompt("profile text", offer)
        assert "Build cutting-edge LLMs" in prompt

    def test_includes_workplace_type(self):
        offer = _make_offer(workplace_type="hybrid")
        prompt = build_user_prompt("profile text", offer)
        assert "hybrid" in prompt

    def test_handles_none_optional_fields(self):
        offer = _make_offer(
            location_raw=None,
            workplace_type=None,
            contract_types=None,
            salary_raw=None,
            posted_at=None,
            description_raw=None,
        )
        prompt = build_user_prompt("profile text", offer)
        # Should not crash, should still have title and company
        assert "Senior ML Engineer" in prompt
        assert "AcmeCorp" in prompt


class TestFormatOffer:
    def test_all_fields_present(self):
        offer = _make_offer()
        formatted = _format_offer(offer)
        assert "**Title:** Senior ML Engineer" in formatted
        assert "**Company:** AcmeCorp" in formatted
        assert "**Location:** Warsaw, Poland" in formatted
        assert "**Workplace type:** remote" in formatted
        assert "**Contract types:** b2b, permanent" in formatted
        assert "**Salary:** 25000-35000 PLN" in formatted
        assert "**Posted:** 2026-06-01" in formatted
        assert "We are looking for a Senior ML Engineer..." in formatted
