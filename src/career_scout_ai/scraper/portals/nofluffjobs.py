import logging
import time
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from career_scout_ai.storage.dedup import (
    DedupResult,
    check_duplicate,
    compute_content_hash,
)
from career_scout_ai.storage.models import JobListing, ScrapingRun, ScrapingStatus

logger = logging.getLogger(__name__)

PORTAL_NAME = "nofluffjobs"
SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
DETAIL_URL = "https://nofluffjobs.com/api/posting/{slug}"
OFFER_URL_TEMPLATE = "https://nofluffjobs.com/job/{slug}"
SEARCH_LIMIT = 500  # unique offers per request (NFJ pageNumber is non-functional)
DETAIL_DELAY = 30.0  # seconds between detail requests (~120 req/h)

# NFJ category slugs for data/AI scope:
# data (~2400), artificialIntelligence (~1300), businessIntelligence (~2700)
CATEGORIES = ["data", "artificialIntelligence", "businessIntelligence"]


def _fetch_listings(client: httpx.Client, limit: int) -> list[dict]:
    """Fetch all listings in a single request.

    NFJ ``pageNumber`` param is non-functional (always returns the same
    results).  The ``limit`` param controls how many unique offers the
    API returns (each expanded into multilocation entries).
    """
    response = client.post(
        SEARCH_URL,
        params={
            "salaryCurrency": "PLN",
            "salaryPeriod": "month",
            "limit": limit,
        },
        json={"rawSearch": f"category={','.join(CATEGORIES)}"},
    )
    response.raise_for_status()
    data: dict = response.json()
    postings: list[dict] = data.get("postings", [])
    logger.info(
        "Fetched %d listings (totalCount=%s)",
        len(postings),
        data.get("totalCount"),
    )
    return postings


def _deduplicate_listings(
    postings: list[dict],
    seen: dict[tuple[str, str], dict],
) -> list[dict]:
    """Group multilocation entries by (title, company), merge cities.

    Uses a cross-page `seen` dict so duplicates spanning multiple pages
    are caught without extra detail requests.
    """
    new_unique: list[dict] = []
    for posting in postings:
        key = (posting.get("title", ""), posting.get("name", ""))
        if key not in seen:
            seen[key] = posting
            new_unique.append(posting)
        else:
            # Merge cities from duplicate entry into the first one
            existing_places = seen[key].get("location", {}).get("places", [])
            new_places = posting.get("location", {}).get("places", [])
            existing_cities = {p.get("city") for p in existing_places if p.get("city")}
            for place in new_places:
                city = place.get("city")
                if city and city not in existing_cities:
                    existing_places.append(place)
                    existing_cities.add(city)

    return new_unique


def _fetch_detail(client: httpx.Client, slug: str) -> dict | None:
    try:
        response = client.get(DETAIL_URL.format(slug=slug))
        response.raise_for_status()
        data: dict = response.json()
        return data
    except Exception:
        logger.debug("Failed to fetch detail for %s", slug)
        return None


def _format_salary(original_salary: dict | None) -> str | None:
    if not original_salary:
        return None
    currency = original_salary.get("currency", "")
    types = original_salary.get("types", {})
    parts = []
    for contract, details in types.items():
        if not isinstance(details, dict):
            continue
        salary_range = details.get("range", [])
        if len(salary_range) < 2:
            continue
        period = details.get("period", "Month").lower()
        parts.append(
            f"{salary_range[0]:g}-{salary_range[1]:g} {currency}/{period} ({contract})"
        )
    return "; ".join(parts) if parts else None


def _format_location(location: dict) -> str | None:
    places = location.get("places", [])
    cities = list(
        dict.fromkeys(
            p.get("city", "")
            for p in places
            if p.get("city") and not p.get("provinceOnly")
        )
    )
    return ", ".join(cities) if cities else None


def _get_workplace_type(location: dict) -> str | None:
    if location.get("remote"):
        return "remote"
    places = location.get("places", [])
    has_remote = any(p.get("city") == "Remote" for p in places)
    if has_remote:
        return "remote"
    return "office"


def _get_contract_types(original_salary: dict | None) -> str | None:
    if not original_salary:
        return None
    types = list(original_salary.get("types", {}).keys())
    return ", ".join(types) if types else None


def _parse_datetime(posted: int | None) -> datetime | None:
    if not posted:
        return None
    try:
        return datetime.fromtimestamp(posted / 1000, tz=UTC)
    except (ValueError, OSError):
        return None


def _parse_offer(listing: dict, detail: dict | None) -> dict:
    slug = listing.get("url", "")
    title = listing.get("title", "")
    company = listing.get("name", "")
    location = listing.get("location", {})

    original_salary = None
    description = None
    if detail:
        original_salary = detail.get("essentials", {}).get("originalSalary")
        description = detail.get("requirements", {}).get("description")
        location = detail.get("location", location)

    return {
        "portal": PORTAL_NAME,
        "url": OFFER_URL_TEMPLATE.format(slug=slug),
        "title": title,
        "company": company,
        "location_raw": _format_location(location),
        "workplace_type": _get_workplace_type(location),
        "contract_types": _get_contract_types(original_salary),
        "salary_raw": _format_salary(original_salary),
        "description_raw": description,
        "posted_at": _parse_datetime(listing.get("posted")),
        "content_hash": compute_content_hash(title, company, description),
    }


def _process_offer(
    client: httpx.Client,
    session: Session,
    listing: dict,
) -> bool:
    """Fetch detail, dedup, and save a single offer. Returns True if new."""
    slug = listing.get("url", "")
    offer_url = OFFER_URL_TEMPLATE.format(slug=slug)

    # Pre-check dedup before fetching detail
    preliminary_hash = compute_content_hash(
        listing.get("title", ""),
        listing.get("name", ""),
        None,
    )
    result = check_duplicate(session, offer_url, preliminary_hash)
    if result == DedupResult.SKIP_URL:
        return False

    detail = _fetch_detail(client, slug)
    time.sleep(DETAIL_DELAY)

    parsed = _parse_offer(listing, detail)

    # Re-check with full content hash (now includes description)
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
    limit: int,
) -> tuple[int, int]:
    """Fetch listings, dedup multilocation, process offers."""
    postings = _fetch_listings(client, limit)
    seen: dict[tuple[str, str], dict] = {}
    unique = _deduplicate_listings(postings, seen)
    logger.info("%d listings -> %d unique offers", len(postings), len(unique))

    listings_found = 0
    listings_new = 0
    for listing in unique:
        listings_found += 1
        try:
            if _process_offer(client, session, listing):
                listings_new += 1
        except Exception:
            logger.exception("Failed to process offer: %s", listing.get("url"))

    session.commit()
    return listings_found, listings_new


def scrape(session: Session, *, limit: int = SEARCH_LIMIT) -> ScrapingRun:
    run = ScrapingRun(portal=PORTAL_NAME, status=ScrapingStatus.RUNNING)
    session.add(run)
    session.commit()

    listings_found = 0
    listings_new = 0

    try:
        with httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            listings_found, listings_new = _scrape_listings(client, session, limit)

        run.status = ScrapingStatus.SUCCESS

    except Exception:
        logger.exception("Scraping failed")
        run.status = ScrapingStatus.FAILED
        session.rollback()
        session.add(run)

    run.finished_at = datetime.now(UTC)
    run.listings_found = listings_found
    run.listings_new = listings_new
    session.commit()

    logger.info(
        "Scraping complete: found=%d, new=%d, status=%s",
        listings_found,
        listings_new,
        run.status,
    )
    return run
