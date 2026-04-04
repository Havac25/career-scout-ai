import json

from career_scout_ai.scraper.portals.justjoinit import (
    _fetch_description,
    _format_location,
    _format_salary,
    _parse_offer,
)


class TestFormatSalary:
    def test_single_b2b(self):
        types = [
            {
                "from": 15000,
                "to": 20000,
                "currency": "pln",
                "unit": "month",
                "type": "b2b",
                "gross": False,
            }
        ]
        assert _format_salary(types) == "15000-20000 PLN/month (b2b, net)"

    def test_multiple_types(self):
        types = [
            {
                "from": 10000,
                "to": 15000,
                "currency": "pln",
                "unit": "month",
                "type": "permanent",
                "gross": True,
            },
            {
                "from": 12000,
                "to": 18000,
                "currency": "pln",
                "unit": "month",
                "type": "b2b",
                "gross": False,
            },
        ]
        result = _format_salary(types)
        assert "permanent" in result
        assert "b2b" in result

    def test_no_salary(self):
        types = [
            {
                "from": None,
                "to": None,
                "currency": "pln",
                "unit": "month",
                "type": "b2b",
                "gross": True,
            }
        ]
        assert _format_salary(types) is None

    def test_empty_list(self):
        assert _format_salary([]) is None


class TestFormatLocation:
    def test_multilocation(self):
        offer = {"multilocation": [{"city": "Warszawa"}, {"city": "Kraków"}]}
        assert _format_location(offer) == "Warszawa, Kraków"

    def test_deduplicates_cities(self):
        offer = {"multilocation": [{"city": "Warszawa"}, {"city": "Warszawa"}]}
        assert _format_location(offer) == "Warszawa"

    def test_fallback_to_city(self):
        offer = {"multilocation": [], "city": "Gdańsk"}
        assert _format_location(offer) == "Gdańsk"

    def test_no_location(self):
        offer: dict = {"multilocation": []}
        assert _format_location(offer) is None


SAMPLE_OFFER = {
    "slug": "acme-data-scientist-warszawa-python",
    "title": "Data Scientist",
    "companyName": "Acme Corp",
    "multilocation": [{"city": "Warszawa"}],
    "employmentTypes": [
        {
            "from": 15000,
            "to": 20000,
            "currency": "pln",
            "unit": "month",
            "type": "b2b",
            "gross": False,
        },
        {
            "from": 12000,
            "to": 16000,
            "currency": "pln",
            "unit": "month",
            "type": "permanent",
            "gross": True,
        },
    ],
    "workplaceType": "hybrid",
    "publishedAt": "2026-03-15T10:00:00.000Z",
}


class TestParseOffer:
    def test_maps_all_fields(self):
        parsed = _parse_offer(SAMPLE_OFFER)
        assert parsed["portal"] == "justjoinit"
        assert (
            parsed["url"]
            == "https://justjoin.it/offers/acme-data-scientist-warszawa-python"
        )
        assert parsed["title"] == "Data Scientist"
        assert parsed["company"] == "Acme Corp"
        assert parsed["location_raw"] == "Warszawa"
        assert parsed["workplace_type"] == "hybrid"
        assert "b2b" in parsed["contract_types"]
        assert "permanent" in parsed["contract_types"]
        assert "PLN" in parsed["salary_raw"]
        assert parsed["description_raw"] is None
        assert parsed["posted_at"] is not None
        assert len(parsed["content_hash"]) == 64

    def test_missing_optional_fields(self):
        minimal = {"slug": "x", "title": "Y", "companyName": "Z"}
        parsed = _parse_offer(minimal)
        assert parsed["location_raw"] is None
        assert parsed["salary_raw"] is None
        assert parsed["workplace_type"] is None
        assert parsed["contract_types"] is None


class TestFetchDescription:
    def test_extracts_from_jsonld(self, httpx_mock):
        jsonld = json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "JobPosting",
                "description": "We are looking for a Data Scientist.",
            },
            separators=(",", ":"),
        )
        html = f"<html><script>{jsonld}</script></html>"
        httpx_mock.add_response(url="https://justjoin.it/offers/test-slug", text=html)

        import httpx

        with httpx.Client() as client:
            result = _fetch_description(client, "https://justjoin.it/offers/test-slug")
        assert result == "We are looking for a Data Scientist."

    def test_returns_none_when_no_jsonld(self, httpx_mock):
        httpx_mock.add_response(
            url="https://justjoin.it/offers/test-slug", text="<html></html>"
        )

        import httpx

        with httpx.Client() as client:
            result = _fetch_description(client, "https://justjoin.it/offers/test-slug")
        assert result is None

    def test_returns_none_on_http_error(self, httpx_mock):
        httpx_mock.add_response(
            url="https://justjoin.it/offers/test-slug", status_code=500
        )

        import httpx

        with httpx.Client() as client:
            result = _fetch_description(client, "https://justjoin.it/offers/test-slug")
        assert result is None
