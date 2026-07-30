import logging
import re
import time
from datetime import UTC, datetime, timedelta

import httpx
from bs4 import BeautifulSoup, Tag
from sqlalchemy.orm import Session

from career_scout_ai.storage.dedup import (
    DedupResult,
    check_duplicate,
    compute_content_hash,
)
from career_scout_ai.storage.models import JobListing, ScrapingRun, ScrapingStatus

logger = logging.getLogger(__name__)

PORTAL_NAME = "aijobsnet"
BASE_URL = "https://aijobs.net"
LISTING_URL = f"{BASE_URL}/"

# Topic IDs (from /ac/topic/ autocomplete), OR'd together in one query to
# scope the otherwise-unfiltered feed to ML/DS/AI roles. The site's default
# feed is NOT pre-filtered to AI/ML despite its marketing tagline -- it also
# surfaces unrelated jobs (e.g. hotel/SEO roles), so this filter is required.
TOPIC_IDS = [
    17,  # Machine Learning
    9,  # Data Science
    6,  # Artificial Intelligence
    2,  # Data Engineering
    5,  # MLOps
    18,  # Computer Vision
    39,  # Natural Language Processing (NLP)
]

MAX_PAGES = 30  # safety cap, 50 listings/page -> ~1500 listings/run (~12-14 days fresh)
REQUEST_DELAY = 1.5  # seconds between listing pages
DETAIL_DELAY = 2.0  # seconds between detail-page fetches

_RELATIVE_TIME_RE = re.compile(r"(\d+)\s*(h|d|w|mo|min)\s*ago", re.IGNORECASE)

_UNIT_TO_TIMEDELTA = {
    "min": lambda n: timedelta(minutes=n),
    "h": lambda n: timedelta(hours=n),
    "d": lambda n: timedelta(days=n),
    "w": lambda n: timedelta(weeks=n),
    "mo": lambda n: timedelta(days=n * 30),
}


def _get_csrf_token(client: httpx.Client) -> str:
    """Fetch the homepage to obtain the csrftoken cookie + form token."""
    response = client.get(LISTING_URL)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    token_input = soup.find("input", {"name": "csrfmiddlewaretoken"})
    if not isinstance(token_input, Tag):
        raise RuntimeError("Could not find csrfmiddlewaretoken on aijobs.net homepage")
    value = token_input.get("value")
    return str(value) if value else ""


def _parse_relative_time(text: str | None) -> datetime | None:
    """Parse relative time strings like '1h ago', '8d ago' into a datetime.

    Precision is approximate (down to the smallest unit shown), which is
    acceptable since posted_at is mainly used for coarse date filtering.
    """
    if not text:
        return None
    match = _RELATIVE_TIME_RE.search(text)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    delta_fn = _UNIT_TO_TIMEDELTA.get(unit)
    if delta_fn is None:
        return None
    return datetime.now(UTC) - delta_fn(amount)


def _parse_salary(li: Tag) -> str | None:
    left_col = li.find("div", recursive=False)
    if left_col is None:
        return None
    title_row = left_col.find("div", recursive=False)
    if title_row is None:
        return None
    badge = title_row.select_one(".text-bg-success, .text-bg-secondary")
    if badge is None:
        return None
    text = badge.get_text(strip=True)
    return text or None


def _parse_seniority_and_contract(li: Tag) -> tuple[str | None, str | None]:
    right_col = li.select_one("div.text-end")
    if right_col is None:
        return None, None

    seniority_badge = right_col.select_one(".text-bg-warning")
    seniority = seniority_badge.get_text(strip=True) if seniority_badge else None

    contract_badges = right_col.select(".text-bg-secondary")
    contract_parts = [
        text for badge in contract_badges if (text := badge.get_text(strip=True))
    ]
    contract_types = ", ".join(contract_parts) if contract_parts else None
    return seniority, contract_types


def _parse_location_and_remote(li: Tag) -> tuple[str | None, str | None]:
    right_col = li.select_one("div.text-end")
    if right_col is None:
        return None, None

    location_divs = right_col.find_all("div", recursive=False)
    if len(location_divs) < 2:
        return None, None

    location_div = location_divs[1]
    is_remote = location_div.select_one(".text-bg-success") is not None

    # Location text is the direct text of the div, excluding the badge span
    location_text = location_div.find(string=True, recursive=False)
    location = location_text.strip() if location_text else None

    workplace_type = "remote" if is_remote else None
    return location or None, workplace_type


def _parse_posted_at(li: Tag) -> datetime | None:
    posted_div = li.select_one("div.text-muted")
    if posted_div is None:
        return None
    return _parse_relative_time(posted_div.get_text(strip=True))


def _parse_title_and_url(li: Tag) -> tuple[str, str]:
    link = li.select_one("a.stretched-link")
    if link is None:
        return "", ""
    href = link.get("href", "")
    if isinstance(href, str) and href.startswith("/"):
        url = f"{BASE_URL}{href}"
    else:
        url = str(href)

    # Title text excludes "Featured"/"Feat." badge spans
    for span in link.select("span"):
        span.extract()
    title = link.get_text(strip=True)
    return title, url


def _parse_listing_item(li: Tag) -> dict:
    title, url = _parse_title_and_url(li)
    salary_raw = _parse_salary(li)
    seniority, contract_types = _parse_seniority_and_contract(li)
    location_raw, workplace_type = _parse_location_and_remote(li)
    posted_at = _parse_posted_at(li)

    return {
        "title": title,
        "url": url,
        "salary_raw": salary_raw,
        "seniority": seniority,
        "contract_types": contract_types,
        "location_raw": location_raw,
        "workplace_type": workplace_type,
        "posted_at": posted_at,
    }


def _get_missing_fields(listing: dict) -> set[str]:
    """Return set of field names that are None (empty/missing)."""
    return {key for key, value in listing.items() if value is None}


def _parse_listing_page(fragment_html: str) -> tuple[list[dict], bool]:
    """Parse a listing page fragment into raw listing dicts + has-more flag."""
    soup = BeautifulSoup(fragment_html, "html.parser")
    items = [_parse_listing_item(li) for li in soup.find_all("li", recursive=False)]
    load_more_re = re.compile(r"Load more", re.IGNORECASE)
    has_more = soup.find("button", string=load_more_re) is not None
    return items, has_more


def _parse_detail_page(detail_html: str) -> tuple[str, str | None]:
    """Parse a job detail page into (company, description_raw)."""
    soup = BeautifulSoup(detail_html, "html.parser")

    company = ""
    company_link = soup.select_one('a[href^="/company/"]')
    if company_link is not None:
        company = company_link.get_text(strip=True).lstrip("@").strip()

    sections: list[str] = []
    for heading in soup.find_all("h5"):
        heading_text = heading.get_text(strip=True)
        items = []
        sibling = heading.find_next_sibling()
        if sibling and sibling.name == "ul":
            items = [li.get_text(strip=True) for li in sibling.find_all("li")]
        elif sibling and sibling.name == "p":
            items = [
                part.strip()
                for part in sibling.get_text(separator="|", strip=True).split("|")
                if part.strip()
            ]
        if items:
            sections.append(f"{heading_text}: {'; '.join(items)}")

    description_raw = "\n\n".join(sections) if sections else None
    return company, description_raw


def _fetch_listing_page(client: httpx.Client, csrf_token: str, page: int) -> str:
    data = {
        "csrfmiddlewaretoken": csrf_token,
        "topics": [str(topic_id) for topic_id in TOPIC_IDS],
    }

    response = client.post(
        LISTING_URL,
        params={"page": page},
        data=data,
        headers={"HX-Request": "true", "Referer": LISTING_URL},
    )
    response.raise_for_status()
    return str(response.text)


def _fetch_detail_page(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url)
        response.raise_for_status()
        return str(response.text)
    except Exception:
        logger.debug("[aijobsnet] Failed to fetch detail page: %s", url)
        return None


def _parse_offer(listing: dict, company: str, description: str | None) -> dict:
    title = listing["title"]
    contract_types_parts = [
        part
        for part in (listing.get("seniority"), listing.get("contract_types"))
        if part
    ]
    contract_types = ", ".join(contract_types_parts) if contract_types_parts else None

    return {
        "portal": PORTAL_NAME,
        "url": listing["url"],
        "title": title,
        "company": company,
        "location_raw": listing.get("location_raw"),
        "workplace_type": listing.get("workplace_type"),
        "contract_types": contract_types,
        "salary_raw": listing.get("salary_raw"),
        "description_raw": description,
        "posted_at": listing.get("posted_at"),
        "content_hash": compute_content_hash(title, company, description),
    }


def _process_offer(client: httpx.Client, session: Session, listing: dict) -> bool:
    """Fetch detail, dedup, and save a single offer. Returns True if new."""
    url = listing["url"]
    if not url:
        return False

    # Cheap pre-check by URL only, before spending a detail-page request.
    preliminary_hash = compute_content_hash(listing["title"], "", None)
    result = check_duplicate(session, url, preliminary_hash)
    if result == DedupResult.SKIP_URL:
        return False

    detail_html = _fetch_detail_page(client, url)
    time.sleep(DETAIL_DELAY)

    company, description = ("", None)
    if detail_html:
        company, description = _parse_detail_page(detail_html)

    parsed = _parse_offer(listing, company, description)

    result = check_duplicate(session, parsed["url"], parsed["content_hash"])
    if result == DedupResult.SKIP_URL:
        return False
    if result == DedupResult.SKIP_HASH:
        parsed["is_duplicate"] = True

    session.add(JobListing(**parsed))
    return True


def _scrape_listings(
    client: httpx.Client,
    session: Session,
    csrf_token: str,
    max_pages: int,
) -> tuple[int, int]:
    listings_found = 0
    listings_new = 0

    for page in range(1, max_pages + 1):
        logger.info("[aijobsnet] page=%d/%d", page, max_pages)
        fragment_html = _fetch_listing_page(client, csrf_token, page)
        items, has_more = _parse_listing_page(fragment_html)

        if not items:
            logger.info("[aijobsnet] no more listings, stopping")
            break

        for listing in items:
            listings_found += 1
            missing = _get_missing_fields(listing)
            if missing:
                logger.warning(
                    "[aijobsnet] Incomplete parse for %s: missing %s",
                    listing.get("url", "unknown"),
                    ", ".join(sorted(missing)),
                )
            try:
                if _process_offer(client, session, listing):
                    listings_new += 1
            except Exception:
                logger.exception(
                    "[aijobsnet] Failed to process offer: %s", listing.get("url")
                )

        session.commit()

        if not has_more:
            logger.info("[aijobsnet] reached last page")
            break

        if page < max_pages:
            time.sleep(REQUEST_DELAY)

    return listings_found, listings_new


def scrape(session: Session, *, max_pages: int = MAX_PAGES) -> ScrapingRun:
    """Scrape AI-Jobs.net via topic-filtered HTMX listing pages + detail fetch."""
    run = ScrapingRun(portal=PORTAL_NAME, status=ScrapingStatus.RUNNING)
    session.add(run)
    session.commit()

    listings_found = 0
    listings_new = 0

    try:
        with httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            csrf_token = _get_csrf_token(client)
            listings_found, listings_new = _scrape_listings(
                client, session, csrf_token, max_pages
            )

        run.status = ScrapingStatus.SUCCESS

    except Exception:
        logger.exception("[aijobsnet] Scraping failed")
        session.rollback()
        session.add(run)
        run.status = ScrapingStatus.FAILED

    run.finished_at = datetime.now(UTC)
    run.listings_found = listings_found
    run.listings_new = listings_new
    session.commit()

    logger.info(
        "[aijobsnet] Scraping complete: found=%d, new=%d, status=%s",
        listings_found,
        listings_new,
        run.status,
    )
    return run
