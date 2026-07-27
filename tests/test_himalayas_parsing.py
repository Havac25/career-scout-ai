from datetime import UTC, datetime

from career_scout_ai.scraper.portals.himalayas import (
    _format_location,
    _format_salary,
    _parse_datetime,
    _parse_offer,
    _strip_html,
)

SAMPLE_JOB = {
    "title": "Machine Learning Engineer",
    "companyName": "Mistral Ai",
    "companySlug": "mistral-ai",
    "employmentType": "Full Time",
    "minSalary": 55000,
    "maxSalary": 80000,
    "salaryPeriod": "annual",
    "currency": "EUR",
    "seniority": ["Senior"],
    "locationRestrictions": ["France", "Germany"],
    "timezoneRestrictions": [-1, 0, 1],
    "description": "<p>Build <strong>ML</strong> systems.</p>",
    "pubDate": 1785163996,
    "expiryDate": 1790347995,
    "applicationLink": "https://himalayas.app/companies/mistral-ai/jobs/ml-engineer",
    "guid": "https://himalayas.app/companies/mistral-ai/jobs/ml-engineer",
}


class TestFormatSalary:
    def test_range(self):
        job = {
            "minSalary": 55000,
            "maxSalary": 80000,
            "currency": "EUR",
            "salaryPeriod": "annual",
        }
        assert _format_salary(job) == "55000-80000 EUR/annual"

    def test_min_only(self):
        job = {
            "minSalary": 55000,
            "maxSalary": None,
            "currency": "EUR",
            "salaryPeriod": "annual",
        }
        assert _format_salary(job) == "55000+ EUR/annual"

    def test_max_only(self):
        job = {
            "minSalary": None,
            "maxSalary": 80000,
            "currency": "EUR",
            "salaryPeriod": "annual",
        }
        assert _format_salary(job) == "up to 80000 EUR/annual"

    def test_no_salary(self):
        job = {"minSalary": None, "maxSalary": None}
        assert _format_salary(job) is None

    def test_no_currency(self):
        job = {
            "minSalary": 55000,
            "maxSalary": 80000,
            "currency": None,
            "salaryPeriod": "annual",
        }
        assert _format_salary(job) is None


class TestFormatLocation:
    def test_multiple_locations(self):
        job = {"locationRestrictions": ["France", "Germany"]}
        assert _format_location(job) == "France, Germany"

    def test_deduplicates(self):
        job = {"locationRestrictions": ["France", "France"]}
        assert _format_location(job) == "France"

    def test_no_location(self):
        job: dict = {"locationRestrictions": []}
        assert _format_location(job) is None

    def test_missing_key(self):
        assert _format_location({}) is None


class TestParseDatetime:
    def test_valid_timestamp(self):
        result = _parse_datetime(1785163996)
        assert result == datetime.fromtimestamp(1785163996, tz=UTC)

    def test_none(self):
        assert _parse_datetime(None) is None


class TestStripHtml:
    def test_removes_tags(self):
        assert _strip_html("<p>Hello <strong>World</strong></p>") == "Hello World"

    def test_unescapes_entities(self):
        assert _strip_html("<p>R&amp;D team</p>") == "R&D team"

    def test_none(self):
        assert _strip_html(None) is None

    def test_empty_string(self):
        assert _strip_html("") is None

    def test_collapses_whitespace(self):
        assert _strip_html("<p>Line one</p>\n<p>Line two</p>") == "Line one Line two"


class TestParseOffer:
    def test_maps_all_fields(self):
        parsed = _parse_offer(SAMPLE_JOB)
        assert parsed["portal"] == "himalayas"
        assert parsed["url"] == (
            "https://himalayas.app/companies/mistral-ai/jobs/ml-engineer"
        )
        assert parsed["title"] == "Machine Learning Engineer"
        assert parsed["company"] == "Mistral Ai"
        assert parsed["location_raw"] == "France, Germany"
        assert parsed["workplace_type"] == "remote"
        assert parsed["contract_types"] == "Full Time"
        assert parsed["salary_raw"] == "55000-80000 EUR/annual"
        assert parsed["description_raw"] == "Build ML systems."
        assert parsed["posted_at"] is not None
        assert len(parsed["content_hash"]) == 64

    def test_missing_optional_fields(self):
        minimal = {
            "title": "X",
            "companyName": "Y",
            "guid": "https://himalayas.app/companies/y/jobs/x",
        }
        parsed = _parse_offer(minimal)
        assert parsed["location_raw"] is None
        assert parsed["salary_raw"] is None
        assert parsed["contract_types"] is None
        assert parsed["description_raw"] is None
        assert parsed["workplace_type"] == "remote"

    def test_url_falls_back_to_application_link(self):
        job = {
            "title": "X",
            "companyName": "Y",
            "applicationLink": "https://himalayas.app/companies/y/jobs/x",
        }
        parsed = _parse_offer(job)
        assert parsed["url"] == "https://himalayas.app/companies/y/jobs/x"
