import logging
import time
from datetime import UTC, datetime
from typing import Any, cast

import httpx
from sqlalchemy.orm import Session

from career_scout_ai.storage.dedup import (
    DedupResult,
    check_duplicate,
    compute_content_hash,
)
from career_scout_ai.storage.models import JobListing, ScrapingRun, ScrapingStatus

logger = logging.getLogger(__name__)

PORTAL_NAME = "welcometothejungle"
ALGOLIA_APP_ID = "CSEKHVMS53"
ALGOLIA_API_KEY = "4bd8f6215d0cc52b26430765769e65a0"
ALGOLIA_URL = f"https://{ALGOLIA_APP_ID}-dsn.algolia.net/1/indexes/*/queries"
INDEX_NAME = "wk_cms_jobs_production"

OFFER_URL_TEMPLATE = (
    "https://www.welcometothejungle.com/fr/companies/{company_slug}/jobs/{slug}"
)

# Search queries to cover ML/DS/AI roles
SEARCH_QUERIES = [
    "machine learning",
    "data scientist",
    "ML engineer",
    "AI engineer",
    "deep learning",
]

# Algolia filter: Paris OR Toulouse OR full remote, exclude internships
FILTERS = (
    "(office.city:Paris OR office.city:Toulouse OR remote:fulltime) "
    "AND NOT contract_type:INTERNSHIP "
    "AND NOT contract_type:APPRENTICESHIP"
)

HITS_PER_PAGE = 50
MAX_PAGES = 10  # per query — safety limit
REQUEST_DELAY = 1.0  # seconds between Algolia requests


def _get_algolia_headers() -> dict[str, str]:
    return {
        "X-Algolia-Application-Id": ALGOLIA_APP_ID,
        "X-Algolia-API-Key": ALGOLIA_API_KEY,
        "Content-Type": "application/json",
        "Referer": "https://www.welcometothejungle.com/",
    }


def _format_salary(hit: dict) -> str | None:
    salary_min = hit.get("salary_minimum")
    salary_max = hit.get("salary_maximum")
    currency = hit.get("salary_currency")
    period = hit.get("salary_period")

    if salary_min is None and salary_max is None:
        return None
    if not currency or period == "none":
        return None

    if salary_min and salary_max:
        return f"{salary_min}-{salary_max} {currency}/{period}"
    elif salary_min:
        return f"{salary_min}+ {currency}/{period}"
    else:
        return f"up to {salary_max} {currency}/{period}"


def _format_location(hit: dict) -> str | None:
    offices = hit.get("offices") or []
    cities = list(dict.fromkeys(o.get("city", "") for o in offices if o.get("city")))
    if not cities:
        city = (hit.get("office") or {}).get("city")
        if city:
            cities = [city]
    return ", ".join(cities) if cities else None


def _get_remote_type(hit: dict) -> str | None:
    remote = hit.get("remote")
    mapping = {
        "fulltime": "remote",
        "partial": "hybrid",
        "punctual": "hybrid",
        "no": "office",
    }
    if isinstance(remote, str):
        return mapping.get(remote)
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _parse_offer(hit: dict, description: str) -> dict:
    slug = hit.get("slug", "")
    org = hit.get("organization") or {}
    company = org.get("name", "")
    company_slug = org.get("slug", "")
    title = hit.get("name", "")

    contract_type = hit.get("contract_type", "")
    contract_map = {
        "FULL_TIME": "full-time",
        "FREELANCE": "freelance",
        "TEMPORARY": "temporary",
    }
    contract = contract_map.get(
        contract_type, contract_type.lower() if contract_type else None
    )

    return {
        "portal": PORTAL_NAME,
        "url": OFFER_URL_TEMPLATE.format(company_slug=company_slug, slug=slug),
        "title": title,
        "company": company,
        "location_raw": _format_location(hit),
        "workplace_type": _get_remote_type(hit),
        "contract_types": contract,
        "salary_raw": _format_salary(hit),
        "description_raw": description,
        "posted_at": _parse_datetime(hit.get("published_at")),
        "content_hash": compute_content_hash(title, company, description),
    }


def _fetch_page(client: httpx.Client, query: str, page: int) -> dict[str, Any]:
    payload = {
        "requests": [
            {
                "indexName": INDEX_NAME,
                "params": (
                    f"query={query}"
                    f"&filters={FILTERS}"
                    f"&hitsPerPage={HITS_PER_PAGE}"
                    f"&page={page}"
                ),
            }
        ]
    }
    response = client.post(ALGOLIA_URL, json=payload)
    response.raise_for_status()
    data = cast(dict[str, Any], response.json())
    return cast(dict[str, Any], data["results"][0])


def _process_offer(
    session: Session,
    hit: dict,
) -> bool | None:
    """Dedup check and save a single offer using Algolia profile as description.

    Returns True if new, False if duplicate/skipped, None if no description.
    """
    slug = hit.get("slug", "")
    org = hit.get("organization") or {}
    company_slug = org.get("slug", "")
    url = OFFER_URL_TEMPLATE.format(company_slug=company_slug, slug=slug)

    # Use Algolia 'profile' field as description
    description = hit.get("profile")
    if not description:
        logger.debug("[wttj] No profile/description in Algolia for %s, skipping", url)
        return None

    title = hit.get("name", "")
    company = org.get("name", "")
    content_hash = compute_content_hash(title, company, description)

    # Dedup check
    result = check_duplicate(session, url, content_hash)
    if result == DedupResult.SKIP_URL:
        return False
    if result == DedupResult.SKIP_HASH:
        parsed = _parse_offer(hit, description)
        parsed["is_duplicate"] = True
        session.add(JobListing(**parsed))
        return False

    parsed = _parse_offer(hit, description)
    session.add(JobListing(**parsed))
    return True


def _scrape_query(
    algolia_client: httpx.Client,
    session: Session,
    query: str,
    max_pages: int,
    seen_ids: set[str],
) -> tuple[int, int, int]:
    """Scrape all pages for a single search query.

    Returns (found, new, skipped_no_desc).
    """
    listings_found = 0
    listings_new = 0
    skipped_no_desc = 0

    for page in range(max_pages):
        logger.info("[wttj] query=%r page=%d/%d", query, page + 1, max_pages)
        result = _fetch_page(algolia_client, query, page)

        hits = result.get("hits", [])
        if not hits:
            break

        for hit in hits:
            object_id = hit.get("objectID", "")
            if object_id in seen_ids:
                continue
            seen_ids.add(object_id)

            listings_found += 1
            outcome = _process_offer(session, hit)
            if outcome is True:
                listings_new += 1
            elif outcome is None:
                skipped_no_desc += 1

        session.commit()

        nb_pages = result.get("nbPages", 0)
        if page + 1 >= nb_pages:
            logger.info("[wttj] query=%r reached last page (%d)", query, nb_pages)
            break

        time.sleep(REQUEST_DELAY)

    return listings_found, listings_new, skipped_no_desc


def scrape(session: Session, *, max_pages: int = MAX_PAGES) -> ScrapingRun:
    """Scrape WTTJ via Algolia for ML/DS/AI roles in Paris, Toulouse, and remote."""
    run = ScrapingRun(portal=PORTAL_NAME, status=ScrapingStatus.RUNNING)
    session.add(run)
    session.commit()

    listings_found = 0
    listings_new = 0
    total_skipped = 0

    try:
        with httpx.Client(
            headers=_get_algolia_headers(), timeout=30.0
        ) as algolia_client:
            seen_ids: set[str] = set()

            for query in SEARCH_QUERIES:
                found, new, skipped = _scrape_query(
                    algolia_client, session, query, max_pages, seen_ids
                )
                listings_found += found
                listings_new += new
                total_skipped += skipped

                if query != SEARCH_QUERIES[-1]:
                    time.sleep(REQUEST_DELAY)

        run.status = ScrapingStatus.SUCCESS

    except Exception:
        logger.exception("[wttj] Scraping failed")
        run.status = ScrapingStatus.FAILED
        session.rollback()
        session.add(run)

    run.finished_at = datetime.now(UTC)
    run.listings_found = listings_found
    run.listings_new = listings_new
    session.commit()

    logger.info(
        "[wttj] Scraping complete: found=%d, new=%d, skipped_no_desc=%d, status=%s",
        listings_found,
        listings_new,
        total_skipped,
        run.status,
    )
    return run
