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

PORTAL_NAME = "justjoinit"
BASE_URL = "https://justjoin.it/api/candidate-api"
OFFERS_URL = f"{BASE_URL}/offers"
DETAIL_URL_TEMPLATE = f"{OFFERS_URL}/{{slug}}"
OFFER_URL_TEMPLATE = "https://justjoin.it/job-offer/{slug}"
MAX_BATCHES = 25  # API returns 10 offers per batch (~250 offers per run)
REQUEST_DELAY = 1.0  # seconds between API page requests
DETAIL_DELAY = 0.5  # seconds between offer detail requests

# Current equivalents of the previous Other, DevOps, Data, Architecture, and AI IDs.
CATEGORIES = ["other", "devops", "data", "architecture", "ai"]


def _format_salary(employment_types: list[dict]) -> str | None:
    parts = []
    for et in employment_types:
        salary_from = et.get("from")
        salary_to = et.get("to")
        if salary_from is None and salary_to is None:
            continue
        currency = et.get("currency", "").upper()
        unit = et.get("unit", "month")
        contract = et.get("type", "")
        gross = "gross" if et.get("gross") else "net"
        range_str = f"{salary_from}-{salary_to}" if salary_to else str(salary_from)
        parts.append(f"{range_str} {currency}/{unit} ({contract}, {gross})")
    return "; ".join(parts) if parts else None


def _format_location(offer: dict) -> str | None:
    locations = offer.get("locations") or []
    cities = list(
        dict.fromkeys(loc.get("city", "") for loc in locations if loc.get("city"))
    )
    if not cities and offer.get("city"):
        cities = [offer["city"]]
    return ", ".join(cities) if cities else None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _fetch_detail(client: httpx.Client, slug: str) -> dict | None:
    try:
        response = client.get(DETAIL_URL_TEMPLATE.format(slug=slug))
        response.raise_for_status()
        data: dict = response.json()
        return data
    except Exception:
        logger.debug("Failed to fetch detail for %s", slug)
    return None


def _parse_offer(offer: dict, detail: dict | None = None) -> dict:
    source = detail or offer
    slug = offer.get("slug", "")
    title = offer.get("title", "")
    company = offer.get("companyName", "")

    employment_types = source.get("employmentTypes", [])
    original_employment_types = [
        et for et in employment_types if et.get("currencySource") == "original"
    ]
    contract_types = list(
        dict.fromkeys(et.get("type", "") for et in employment_types if et.get("type"))
    )
    description = source.get("body")

    return {
        "portal": PORTAL_NAME,
        "url": OFFER_URL_TEMPLATE.format(slug=slug),
        "title": title,
        "company": company,
        "location_raw": _format_location(source),
        "workplace_type": source.get("workplaceType"),
        "contract_types": ", ".join(contract_types) if contract_types else None,
        "salary_raw": _format_salary(original_employment_types),
        "description_raw": description,
        "posted_at": _parse_datetime(source.get("publishedAt")),
        "content_hash": compute_content_hash(title, company, description),
    }


def _fetch_page(client: httpx.Client, cursor: int) -> dict:
    params: list[tuple[str, str | int | float | bool | None]] = [
        ("from", cursor),
        ("sortBy", "publishedAt"),
        ("orderBy", "descending"),
    ]
    params.extend(("categories", category) for category in CATEGORIES)
    response = client.get(OFFERS_URL, params=httpx.QueryParams(params))
    response.raise_for_status()
    data: dict = response.json()
    return data


def _process_offer(
    client: httpx.Client,
    session: Session,
    offer: dict,
) -> bool:
    """Dedup, fetch detail, and save a single offer. Returns True if new."""
    slug = offer.get("slug", "")
    offer_url = OFFER_URL_TEMPLATE.format(slug=slug)
    preliminary_hash = compute_content_hash(
        offer.get("title", ""), offer.get("companyName", ""), None
    )

    result = check_duplicate(
        session,
        offer_url,
        preliminary_hash,
    )
    if result == DedupResult.SKIP_URL:
        return False

    detail = _fetch_detail(client, slug)
    time.sleep(DETAIL_DELAY)
    parsed = _parse_offer(offer, detail)

    result = check_duplicate(session, parsed["url"], parsed["content_hash"])
    if result == DedupResult.SKIP_URL:
        return False
    if result == DedupResult.SKIP_HASH:
        parsed["is_duplicate"] = True

    session.add(JobListing(**parsed))
    return True


def _scrape_pages(
    client: httpx.Client,
    session: Session,
    max_batches: int,
) -> tuple[int, int]:
    """Iterate API cursor batches, process offers."""
    listings_found = 0
    listings_new = 0
    cursor = 0

    for batch in range(1, max_batches + 1):
        logger.info("Fetching batch %d/%d (from=%d)", batch, max_batches, cursor)
        data = _fetch_page(client, cursor)

        offers = data.get("data", [])
        if not offers:
            logger.info("No more offers at cursor %d, stopping", cursor)
            break

        for offer in offers:
            listings_found += 1
            if _process_offer(client, session, offer):
                listings_new += 1

        session.commit()

        next_page = data.get("meta", {}).get("next")
        if not next_page or next_page.get("cursor") is None:
            logger.info("Reached last batch")
            break
        cursor = next_page["cursor"]

        if batch < max_batches:
            time.sleep(REQUEST_DELAY)

    return listings_found, listings_new


def scrape(session: Session, *, max_batches: int = MAX_BATCHES) -> ScrapingRun:
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
            },
            timeout=30.0,
        ) as client:
            listings_found, listings_new = _scrape_pages(client, session, max_batches)

        run.status = ScrapingStatus.SUCCESS

    except Exception:
        logger.exception("Scraping failed")
        session.rollback()
        session.add(run)
        run.status = ScrapingStatus.FAILED

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
