from career_scout_ai.scraper.portals.nofluffjobs import (
    _deduplicate_listings,
    _format_location,
    _format_salary,
    _get_contract_types,
    _get_workplace_type,
    _parse_offer,
)


class TestFormatSalary:
    def test_single_b2b(self):
        salary = {
            "currency": "PLN",
            "types": {
                "b2b": {"range": [15000, 25000], "period": "Month"},
            },
        }
        assert _format_salary(salary) == "15000-25000 PLN/month (b2b)"

    def test_multiple_contract_types(self):
        salary = {
            "currency": "PLN",
            "types": {
                "b2b": {"range": [18000, 25000], "period": "Month"},
                "permanent": {"range": [14000, 20000], "period": "Month"},
            },
        }
        result = _format_salary(salary)
        assert "b2b" in result
        assert "permanent" in result
        assert "PLN/month" in result

    def test_no_salary_none(self):
        assert _format_salary(None) is None

    def test_empty_types(self):
        salary: dict[str, str | dict[str, dict[str, list[int] | str]]] = {
            "currency": "PLN",
            "types": {},
        }
        assert _format_salary(salary) is None

    def test_period_normalization(self):
        salary = {
            "currency": "EUR",
            "types": {
                "b2b": {"range": [5000, 8000], "period": "Hour"},
            },
        }
        result = _format_salary(salary)
        assert "hour" in result
        assert "Hour" not in result

    def test_range_too_short_skipped(self):
        salary = {
            "currency": "PLN",
            "types": {
                "b2b": {"range": [15000], "period": "Month"},
            },
        }
        assert _format_salary(salary) is None


class TestFormatLocation:
    def test_single_city(self):
        location = {"places": [{"city": "Warszawa"}]}
        assert _format_location(location) == "Warszawa"

    def test_multiple_cities(self):
        location = {"places": [{"city": "Warszawa"}, {"city": "Kraków"}]}
        assert _format_location(location) == "Warszawa, Kraków"

    def test_deduplicates_cities(self):
        location = {"places": [{"city": "Warszawa"}, {"city": "Warszawa"}]}
        assert _format_location(location) == "Warszawa"

    def test_filters_province_only(self):
        location = {
            "places": [
                {"city": "Warszawa", "provinceOnly": False},
                {"city": "Mazowieckie", "provinceOnly": True},
            ]
        }
        assert _format_location(location) == "Warszawa"

    def test_empty_places(self):
        location: dict[str, list[dict[str, str]]] = {"places": []}
        assert _format_location(location) is None

    def test_no_places_key(self):
        location: dict[str, list[dict[str, str]]] = {}
        assert _format_location(location) is None


class TestGetWorkplaceType:
    def test_remote_flag(self):
        location = {"remote": True, "places": []}
        assert _get_workplace_type(location) == "remote"

    def test_remote_city(self):
        location = {"remote": False, "places": [{"city": "Remote"}]}
        assert _get_workplace_type(location) == "remote"

    def test_office(self):
        location = {"remote": False, "places": [{"city": "Warszawa"}]}
        assert _get_workplace_type(location) == "office"

    def test_no_remote_key(self):
        location = {"places": [{"city": "Kraków"}]}
        assert _get_workplace_type(location) == "office"


class TestGetContractTypes:
    def test_extracts_types(self):
        salary: dict[str, dict[str, dict[str, str]]] = {
            "types": {"b2b": {}, "permanent": {}}
        }
        result = _get_contract_types(salary)
        assert "b2b" in result
        assert "permanent" in result

    def test_no_salary(self):
        assert _get_contract_types(None) is None

    def test_empty_types(self):
        salary: dict[str, dict[str, dict[str, str]]] = {"types": {}}
        assert _get_contract_types(salary) is None


class TestDeduplicateListings:
    def test_merges_same_offer_different_cities(self):
        postings = [
            {
                "title": "Data Engineer",
                "name": "Acme",
                "url": "acme-data-engineer",
                "location": {"places": [{"city": "Warszawa"}]},
            },
            {
                "title": "Data Engineer",
                "name": "Acme",
                "url": "acme-data-engineer",
                "location": {"places": [{"city": "Kraków"}]},
            },
        ]
        seen: dict[tuple[str, str], dict] = {}
        unique = _deduplicate_listings(postings, seen)
        assert len(unique) == 1
        cities = [p["city"] for p in unique[0]["location"]["places"]]
        assert "Warszawa" in cities
        assert "Kraków" in cities

    def test_keeps_different_offers(self):
        postings = [
            {
                "title": "Data Engineer",
                "name": "Acme",
                "url": "acme-data-engineer",
                "location": {"places": [{"city": "Warszawa"}]},
            },
            {
                "title": "ML Engineer",
                "name": "Acme",
                "url": "acme-ml-engineer",
                "location": {"places": [{"city": "Warszawa"}]},
            },
        ]
        seen: dict[tuple[str, str], dict] = {}
        unique = _deduplicate_listings(postings, seen)
        assert len(unique) == 2

    def test_no_duplicate_cities_after_merge(self):
        postings = [
            {
                "title": "Data Engineer",
                "name": "Acme",
                "url": "acme-data-engineer",
                "location": {"places": [{"city": "Warszawa"}]},
            },
            {
                "title": "Data Engineer",
                "name": "Acme",
                "url": "acme-data-engineer",
                "location": {"places": [{"city": "Warszawa"}]},
            },
        ]
        seen: dict[tuple[str, str], dict] = {}
        unique = _deduplicate_listings(postings, seen)
        assert len(unique) == 1
        cities = [p["city"] for p in unique[0]["location"]["places"]]
        assert cities == ["Warszawa"]

    def test_cross_page_seen_dict(self):
        seen: dict[tuple[str, str], dict] = {}
        page1 = [
            {
                "title": "DS",
                "name": "Corp",
                "url": "corp-ds",
                "location": {"places": [{"city": "Gdańsk"}]},
            },
        ]
        page2 = [
            {
                "title": "DS",
                "name": "Corp",
                "url": "corp-ds",
                "location": {"places": [{"city": "Wrocław"}]},
            },
        ]
        unique1 = _deduplicate_listings(page1, seen)
        unique2 = _deduplicate_listings(page2, seen)
        assert len(unique1) == 1
        assert len(unique2) == 0
        cities = [p["city"] for p in seen[("DS", "Corp")]["location"]["places"]]
        assert "Gdańsk" in cities
        assert "Wrocław" in cities


SAMPLE_LISTING = {
    "url": "acme-data-scientist",
    "title": "Data Scientist",
    "name": "Acme Corp",
    "location": {
        "remote": False,
        "places": [{"city": "Warszawa"}, {"city": "Kraków"}],
    },
    "posted": 1735689600000,  # 2025-01-01T00:00:00Z
}

SAMPLE_DETAIL = {
    "essentials": {
        "originalSalary": {
            "currency": "PLN",
            "types": {
                "b2b": {"range": [20000, 30000], "period": "Month"},
            },
        },
    },
    "requirements": {
        "description": "We need a data scientist with Python skills.",
    },
    "location": {
        "remote": True,
        "places": [{"city": "Warszawa"}, {"city": "Kraków"}],
    },
}


class TestParseOffer:
    def test_maps_all_fields(self):
        parsed = _parse_offer(SAMPLE_LISTING, SAMPLE_DETAIL)
        assert parsed["portal"] == "nofluffjobs"
        assert parsed["url"] == "https://nofluffjobs.com/job/acme-data-scientist"
        assert parsed["title"] == "Data Scientist"
        assert parsed["company"] == "Acme Corp"
        assert parsed["location_raw"] == "Warszawa, Kraków"
        assert parsed["workplace_type"] == "remote"
        assert "b2b" in parsed["contract_types"]
        assert "20000-30000 PLN/month" in parsed["salary_raw"]
        assert (
            parsed["description_raw"] == "We need a data scientist with Python skills."
        )
        assert parsed["posted_at"] is not None
        assert len(parsed["content_hash"]) == 64

    def test_without_detail(self):
        parsed = _parse_offer(SAMPLE_LISTING, None)
        assert parsed["title"] == "Data Scientist"
        assert parsed["company"] == "Acme Corp"
        assert parsed["salary_raw"] is None
        assert parsed["description_raw"] is None
        assert parsed["contract_types"] is None
        assert parsed["location_raw"] == "Warszawa, Kraków"
        assert parsed["workplace_type"] == "office"

    def test_minimal_listing(self):
        minimal = {"url": "x", "title": "Y", "name": "Z"}
        parsed = _parse_offer(minimal, None)
        assert parsed["portal"] == "nofluffjobs"
        assert parsed["url"] == "https://nofluffjobs.com/job/x"
        assert parsed["title"] == "Y"
        assert parsed["company"] == "Z"
        assert parsed["salary_raw"] is None
        assert parsed["description_raw"] is None
        assert parsed["location_raw"] is None
        assert parsed["posted_at"] is None
