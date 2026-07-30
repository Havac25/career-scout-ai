from datetime import UTC, datetime, timedelta

from bs4 import BeautifulSoup

from career_scout_ai.scraper.portals.aijobsnet import (
    _parse_detail_page,
    _parse_listing_item,
    _parse_listing_page,
    _parse_offer,
    _parse_relative_time,
)

SAMPLE_LI_HTML = """
<li class="d-flex justify-content-between position-relative pb-2">
<div>
    <div>
        <a class="font-monospace fw-bold stretched-link"
           href="/job/ml-engineer-remote-12345/" target="_blank">
            <span class="fw-light text-bg-primary px-1 rounded d-none d-sm-inline">
            Featured</span>
            <span class="fw-light text-bg-primary px-1 rounded d-inline d-sm-none">
            Feat.</span>
            Machine Learning Engineer
        </a>
        <span class="text-bg-success px-1 rounded">USD 150K-200K</span>
    </div>
    <div>
        <span>Python</span> | <span>PyTorch</span>
    </div>
    <div>
        <span class="text-success">Remote work</span>
    </div>
</div>
<div class="text-end">
    <div>
        <span class="text-bg-warning px-1 rounded">Senior-level</span>
        <span class="text-bg-secondary px-1 rounded">Full Time</span>
    </div>
    <div>
        Remote
        <span class="text-bg-success px-1 rounded">R</span>
    </div>
    <div class="text-muted">3h ago</div>
</div>
</li>
"""

SAMPLE_LI_MINIMAL_HTML = """
<li class="d-flex justify-content-between position-relative pb-2">
<div>
    <div>
        <a class="font-monospace fw-bold stretched-link"
           href="/job/minimal-role-1/" target="_blank">
            Minimal Role
        </a>
    </div>
    <div></div>
    <div></div>
</div>
<div class="text-end">
    <div>
        <span class="text-bg-warning px-1 rounded">Entry-level</span>
        <span class="text-bg-secondary px-1 rounded">Full Time</span>
    </div>
    <div>
        Warsaw, Poland
    </div>
    <div class="text-muted">8d ago</div>
</div>
</li>
"""

SAMPLE_PAGE_WITH_LOAD_MORE = (
    SAMPLE_LI_HTML
    + """
<button class="btn btn-outline-primary w-100 my-3" hx-post="/?page=2"
        hx-swap="outerHTML" hx-include="#search_form">Load more</button>
"""
)

SAMPLE_DETAIL_HTML = """
<html><body>
<main>
<h1>Machine Learning Engineer</h1>
<div class="col-6 col-md-5 col-lg-4 text-end">
    <div class="fw-bold mb-2">
        <a class="text-decoration-none d-block text-break" href="/company/acme-123/">
            @ Acme Corp
        </a>
    </div>
</div>
<h5>Tasks</h5>
<ul>
    <li>Build ML pipelines</li>
    <li>Deploy models to production</li>
</ul>
<h5>Perks/Benefits</h5>
<ul>
    <li><a href="/jobs/perk-remote-work/">Remote work</a></li>
</ul>
<h5>Skills/Tech-stack</h5>
<p>
    <a href="/jobs/skill-python/">Python</a> |
    <a href="/jobs/skill-pytorch/">PyTorch</a>
</p>
<h5>Education</h5>
<p>
    <a href="/jobs/education-bachelor/">Bachelor</a>
</p>
</main>
</body></html>
"""

SAMPLE_DETAIL_NO_SECTIONS_HTML = """
<html><body>
<main>
<h1>Bare Role</h1>
<div class="col-6 col-md-5 col-lg-4 text-end">
    <div class="fw-bold mb-2">
        <a class="text-decoration-none d-block text-break" href="/company/bare-co-1/">
            @ Bare Co
        </a>
    </div>
</div>
</main>
</body></html>
"""


class TestParseRelativeTime:
    def test_hours_ago(self):
        result = _parse_relative_time("3h ago")
        expected = datetime.now(UTC) - timedelta(hours=3)
        assert abs((result - expected).total_seconds()) < 5

    def test_days_ago(self):
        result = _parse_relative_time("8d ago")
        expected = datetime.now(UTC) - timedelta(days=8)
        assert abs((result - expected).total_seconds()) < 5

    def test_minutes_ago(self):
        result = _parse_relative_time("45min ago")
        expected = datetime.now(UTC) - timedelta(minutes=45)
        assert abs((result - expected).total_seconds()) < 5

    def test_weeks_ago(self):
        result = _parse_relative_time("2w ago")
        expected = datetime.now(UTC) - timedelta(weeks=2)
        assert abs((result - expected).total_seconds()) < 5

    def test_none(self):
        assert _parse_relative_time(None) is None

    def test_unparseable(self):
        assert _parse_relative_time("just now") is None

    def test_empty_string(self):
        assert _parse_relative_time("") is None


class TestParseListingItem:
    def test_full_item(self):
        soup = BeautifulSoup(SAMPLE_LI_HTML, "html.parser")
        li = soup.find("li")
        item = _parse_listing_item(li)

        assert item["title"] == "Machine Learning Engineer"
        assert item["url"] == "https://aijobs.net/job/ml-engineer-remote-12345/"
        assert item["salary_raw"] == "USD 150K-200K"
        assert item["seniority"] == "Senior-level"
        assert item["contract_types"] == "Full Time"
        assert item["location_raw"] == "Remote"
        assert item["workplace_type"] == "remote"
        assert item["posted_at"] is not None

    def test_minimal_item(self):
        soup = BeautifulSoup(SAMPLE_LI_MINIMAL_HTML, "html.parser")
        li = soup.find("li")
        item = _parse_listing_item(li)

        assert item["title"] == "Minimal Role"
        assert item["url"] == "https://aijobs.net/job/minimal-role-1/"
        assert item["salary_raw"] is None
        assert item["seniority"] == "Entry-level"
        assert item["contract_types"] == "Full Time"
        assert item["location_raw"] == "Warsaw, Poland"
        assert item["workplace_type"] is None
        assert item["posted_at"] is not None


class TestParseListingPage:
    def test_with_load_more(self):
        items, has_more = _parse_listing_page(SAMPLE_PAGE_WITH_LOAD_MORE)
        assert len(items) == 1
        assert has_more is True

    def test_without_load_more(self):
        items, has_more = _parse_listing_page(SAMPLE_LI_HTML)
        assert len(items) == 1
        assert has_more is False

    def test_empty_page(self):
        items, has_more = _parse_listing_page("")
        assert items == []
        assert has_more is False


class TestParseDetailPage:
    def test_full_sections(self):
        company, description = _parse_detail_page(SAMPLE_DETAIL_HTML)
        assert company == "Acme Corp"
        assert "Tasks: Build ML pipelines; Deploy models to production" in description
        assert "Perks/Benefits: Remote work" in description
        assert "Skills/Tech-stack: Python; PyTorch" in description
        assert "Education: Bachelor" in description

    def test_no_sections(self):
        company, description = _parse_detail_page(SAMPLE_DETAIL_NO_SECTIONS_HTML)
        assert company == "Bare Co"
        assert description is None


class TestParseOffer:
    def test_maps_all_fields(self):
        listing = {
            "title": "Machine Learning Engineer",
            "url": "https://aijobs.net/job/ml-engineer-remote-12345/",
            "salary_raw": "USD 150K-200K",
            "seniority": "Senior-level",
            "contract_types": "Full Time",
            "location_raw": "Remote",
            "workplace_type": "remote",
            "posted_at": datetime.now(UTC),
        }
        parsed = _parse_offer(listing, "Acme Corp", "Build ML pipelines")

        assert parsed["portal"] == "aijobsnet"
        assert parsed["url"] == "https://aijobs.net/job/ml-engineer-remote-12345/"
        assert parsed["title"] == "Machine Learning Engineer"
        assert parsed["company"] == "Acme Corp"
        assert parsed["location_raw"] == "Remote"
        assert parsed["workplace_type"] == "remote"
        assert parsed["contract_types"] == "Senior-level, Full Time"
        assert parsed["salary_raw"] == "USD 150K-200K"
        assert parsed["description_raw"] == "Build ML pipelines"
        assert parsed["posted_at"] is not None
        assert len(parsed["content_hash"]) == 64

    def test_missing_optional_fields(self):
        listing = {
            "title": "X",
            "url": "https://aijobs.net/job/x/",
            "salary_raw": None,
            "seniority": None,
            "contract_types": None,
            "location_raw": None,
            "workplace_type": None,
            "posted_at": None,
        }
        parsed = _parse_offer(listing, "Y", None)

        assert parsed["location_raw"] is None
        assert parsed["salary_raw"] is None
        assert parsed["contract_types"] is None
        assert parsed["description_raw"] is None
        assert parsed["workplace_type"] is None
