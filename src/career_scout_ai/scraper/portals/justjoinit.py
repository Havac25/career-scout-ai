import json
import logging
import re
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
BASE_URL = "https://api.justjoin.it/v2/user-panel/offers"
OFFER_URL_TEMPLATE = "https://justjoin.it/offers/{slug}"
PER_PAGE = 50
MAX_PAGES = 5  # Safety limit for MVP (~250 offers per run)
REQUEST_DELAY = 1.0  # seconds between API page requests
DETAIL_DELAY = 0.5  # seconds between offer detail requests

_JSONLD_RE = re.compile(
    r'\{"@context":"https://schema\.org","@type":"JobPosting".*?\}(?=</script>)',
)


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
    locations = offer.get("multilocation") or []
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


def _fetch_description(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url, follow_redirects=True)
        response.raise_for_status()
        match = _JSONLD_RE.search(response.text)
        if match:
            data = json.loads(match.group(0))
            description: str | None = data.get("description")
            return description
    except Exception:
        logger.debug("Failed to fetch description for %s", url)
    return None


def _parse_offer(offer: dict) -> dict:
    slug = offer.get("slug", "")
    title = offer.get("title", "")
    company = offer.get("companyName", "")

    return {
        "portal": PORTAL_NAME,
        "url": OFFER_URL_TEMPLATE.format(slug=slug),
        "title": title,
        "company": company,
        "location_raw": _format_location(offer),
        "salary_raw": _format_salary(offer.get("employmentTypes", [])),
        "description_raw": None,
        "posted_at": _parse_datetime(offer.get("publishedAt")),
        "content_hash": compute_content_hash(title, company, None),
    }


def fetch_page(client: httpx.Client, page: int) -> dict:
    response = client.get(BASE_URL, params={"page": page, "perPage": PER_PAGE})
    response.raise_for_status()
    data: dict = response.json()
    return data


def scrape(session: Session, *, max_pages: int = MAX_PAGES) -> ScrapingRun:
    run = ScrapingRun(portal=PORTAL_NAME, status=ScrapingStatus.RUNNING)
    session.add(run)
    session.commit()

    listings_found = 0
    listings_new = 0

    try:
        with (
            httpx.Client(
                headers={"User-Agent": "CareerScoutAI/0.1"},
                timeout=30.0,
            ) as web_client,
            httpx.Client(
                headers={"User-Agent": "CareerScoutAI/0.1", "Version": "2"},
                timeout=30.0,
            ) as client,
        ):
            for page in range(1, max_pages + 1):
                logger.info("Fetching page %d/%d", page, max_pages)
                data = fetch_page(client, page)

                offers = data.get("data", [])
                if not offers:
                    logger.info("No more offers on page %d, stopping", page)
                    break

                for offer in offers:
                    listings_found += 1
                    parsed = _parse_offer(offer)

                    result = check_duplicate(
                        session,
                        parsed["url"],
                        parsed["content_hash"],
                    )
                    if result == DedupResult.SKIP_URL:
                        continue
                    if result == DedupResult.SKIP_HASH:
                        parsed["is_duplicate"] = True

                    description = _fetch_description(web_client, parsed["url"])
                    if description:
                        parsed["description_raw"] = description
                        parsed["content_hash"] = compute_content_hash(
                            parsed["title"],
                            parsed["company"],
                            description,
                        )
                    time.sleep(DETAIL_DELAY)

                    listing = JobListing(**parsed)
                    session.add(listing)
                    listings_new += 1

                session.commit()

                meta = data.get("meta", {})
                if meta.get("nextPage") is None:
                    logger.info("Reached last page")
                    break

                if page < max_pages:
                    time.sleep(REQUEST_DELAY)

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
