from career_scout_ai.scraper.portals.welcometothejungle import (
    _format_location,
    _format_salary,
    _get_remote_type,
    _parse_offer,
)

SAMPLE_HIT = {
    "slug": "ml-engineer_paris",
    "name": "ML Engineer",
    "organization": {
        "name": "Mistral Ai",
        "slug": "mistral-ai",
    },
    "offices": [{"city": "Paris", "district": "Paris", "country": "France"}],
    "remote": "partial",
    "contract_type": "FULL_TIME",
    "salary_minimum": 55000,
    "salary_maximum": 80000,
    "salary_currency": "EUR",
    "salary_period": "yearly",
    "published_at": "2026-07-15T10:00:00.000+02:00",
    "objectID": "12345",
}


class TestFormatSalary:
    def test_range(self):
        hit = {
            "salary_minimum": 55000,
            "salary_maximum": 80000,
            "salary_currency": "EUR",
            "salary_period": "yearly",
        }
        assert _format_salary(hit) == "55000-80000 EUR/yearly"

    def test_min_only(self):
        hit = {
            "salary_minimum": 55000,
            "salary_maximum": None,
            "salary_currency": "EUR",
            "salary_period": "yearly",
        }
        assert _format_salary(hit) == "55000+ EUR/yearly"

    def test_max_only(self):
        hit = {
            "salary_minimum": None,
            "salary_maximum": 80000,
            "salary_currency": "EUR",
            "salary_period": "yearly",
        }
        assert _format_salary(hit) == "up to 80000 EUR/yearly"

    def test_no_salary(self):
        hit = {"salary_minimum": None, "salary_maximum": None}
        assert _format_salary(hit) is None

    def test_no_currency(self):
        hit = {
            "salary_minimum": 55000,
            "salary_maximum": 80000,
            "salary_currency": None,
            "salary_period": "yearly",
        }
        assert _format_salary(hit) is None

    def test_period_none(self):
        hit = {
            "salary_minimum": 55000,
            "salary_maximum": 80000,
            "salary_currency": "EUR",
            "salary_period": "none",
        }
        assert _format_salary(hit) is None


class TestFormatLocation:
    def test_offices_list(self):
        hit = {"offices": [{"city": "Paris"}, {"city": "Toulouse"}]}
        assert _format_location(hit) == "Paris, Toulouse"

    def test_deduplicates_cities(self):
        hit = {"offices": [{"city": "Paris"}, {"city": "Paris"}]}
        assert _format_location(hit) == "Paris"

    def test_fallback_to_office(self):
        hit = {"offices": [], "office": {"city": "Lyon"}}
        assert _format_location(hit) == "Lyon"

    def test_no_location(self):
        hit: dict = {"offices": []}
        assert _format_location(hit) is None


class TestGetRemoteType:
    def test_fulltime(self):
        assert _get_remote_type({"remote": "fulltime"}) == "remote"

    def test_partial(self):
        assert _get_remote_type({"remote": "partial"}) == "hybrid"

    def test_no(self):
        assert _get_remote_type({"remote": "no"}) == "office"

    def test_unknown(self):
        assert _get_remote_type({"remote": "unknown"}) is None


class TestParseOffer:
    def test_maps_all_fields(self):
        parsed = _parse_offer(SAMPLE_HIT, "<p>Job description</p>")
        assert parsed["portal"] == "welcometothejungle"
        assert parsed["url"] == (
            "https://www.welcometothejungle.com/fr/companies/mistral-ai/jobs/ml-engineer_paris"
        )
        assert parsed["title"] == "ML Engineer"
        assert parsed["company"] == "Mistral Ai"
        assert parsed["location_raw"] == "Paris"
        assert parsed["workplace_type"] == "hybrid"
        assert parsed["contract_types"] == "full-time"
        assert parsed["salary_raw"] == "55000-80000 EUR/yearly"
        assert parsed["description_raw"] == "<p>Job description</p>"
        assert parsed["posted_at"] is not None
        assert len(parsed["content_hash"]) == 64

    def test_empty_description(self):
        parsed = _parse_offer(SAMPLE_HIT, "")
        assert parsed["description_raw"] == ""

    def test_missing_optional_fields(self):
        minimal = {
            "slug": "x",
            "name": "Y",
            "organization": {"name": "Z", "slug": "z"},
        }
        parsed = _parse_offer(minimal, "desc")
        assert parsed["location_raw"] is None
        assert parsed["salary_raw"] is None
        assert parsed["workplace_type"] is None

    def test_contract_type_mapping(self):
        hit = {**SAMPLE_HIT, "contract_type": "FREELANCE"}
        parsed = _parse_offer(hit, "desc")
        assert parsed["contract_types"] == "freelance"
