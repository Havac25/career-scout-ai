import html
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

PORTAL_NAME = "himalayas"
SEARCH_URL = "https://himalayas.app/jobs/api/search"

# Search queries to cover ML/DS/AI roles (mirrors WTTJ's query list)
SEARCH_QUERIES = [
    "machine learning",
    "data scientist",
    "ML engineer",
    "AI engineer",
    "deep learning",
]

MAX_PAGES = 10  # per query — safety limit (API returns up to 20 results/page)
REQUEST_DELAY = 10  # seconds between requests (per Himalayas rate-limit guidance)
RETRY_BACKOFFS = [5, 15, 30]  # seconds, one per retry attempt on transient errors

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw_html: str | None) -> str | None:
    if not raw_html:
        return None
    text = _TAG_RE.sub(" ", raw_html)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip() or None


def _format_salary(job: dict) -> str | None:
    salary_min = job.get("minSalary")
    salary_max = job.get("maxSalary")
    currency = job.get("currency")
    period = job.get("salaryPeriod")

    if salary_min is None and salary_max is None:
        return None
    if not currency:
        return None

    if salary_min and salary_max:
        return f"{salary_min}-{salary_max} {currency}/{period}"
    elif salary_min:
        return f"{salary_min}+ {currency}/{period}"
    else:
        return f"up to {salary_max} {currency}/{period}"


def _format_location(job: dict) -> str | None:
    locations = job.get("locationRestrictions") or []
    cities = list(dict.fromkeys(loc for loc in locations if loc))
    return ", ".join(cities) if cities else None


def _parse_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(value, tz=UTC)
    except (ValueError, OSError, OverflowError):
        return None


def _parse_offer(job: dict) -> dict:
    title = job.get("title", "")
    company = job.get("companyName", "")
    description = _strip_html(job.get("description"))
    url = job.get("guid") or job.get("applicationLink", "")

    return {
        "portal": PORTAL_NAME,
        "url": url,
        "title": title,
        "company": company,
        "location_raw": _format_location(job),
        "workplace_type": "remote",
        "contract_types": job.get("employmentType"),
        "salary_raw": _format_salary(job),
        "description_raw": description,
        "posted_at": _parse_datetime(job.get("pubDate")),
        "content_hash": compute_content_hash(title, company, description),
    }


def _fetch_page(client: httpx.Client, query: str, page: int) -> dict:
    params: dict[str, str | int] = {"q": query, "page": page}

    last_exc: Exception | None = None
    for attempt, backoff in enumerate([0, *RETRY_BACKOFFS], start=1):
        if backoff:
            logger.warning(
                "[himalayas] query=%r page=%d retrying in %ds (attempt %d/%d)",
                query,
                page,
                backoff,
                attempt,
                len(RETRY_BACKOFFS) + 1,
            )
            time.sleep(backoff)

        try:
            response = client.get(SEARCH_URL, params=params)
            if response.status_code == 429:
                last_exc = httpx.HTTPStatusError(
                    "429 rate limited", request=response.request, response=response
                )
                continue
            response.raise_for_status()
            data: dict = response.json()
            return data
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_exc = exc
            continue
        except httpx.HTTPStatusError:
            # Non-retryable client/server errors (4xx other than 429)
            raise

    if last_exc is not None:
        raise last_exc
    raise RuntimeError(
        f"[himalayas] query={query!r} page={page} failed with no captured exception"
    )


def _process_offer(session: Session, job: dict) -> bool:
    """Dedup, format, and save a single offer. Returns True if new."""
    parsed = _parse_offer(job)

    result = check_duplicate(session, parsed["url"], parsed["content_hash"])
    if result == DedupResult.SKIP_URL:
        return False
    if result == DedupResult.SKIP_HASH:
        parsed["is_duplicate"] = True

    session.add(JobListing(**parsed))
    return True


def _scrape_query(
    client: httpx.Client,
    session: Session,
    query: str,
    max_pages: int,
    seen_guids: set[str],
) -> tuple[int, int]:
    """Scrape all pages for a single search query. Returns (found, new)."""
    listings_found = 0
    listings_new = 0

    for page in range(1, max_pages + 1):
        logger.info("[himalayas] query=%r page=%d/%d", query, page, max_pages)
        data = _fetch_page(client, query, page)

        jobs = data.get("jobs", [])
        if not jobs:
            logger.info("[himalayas] query=%r no more jobs, stopping", query)
            break

        for job in jobs:
            guid = job.get("guid", "")
            if guid in seen_guids:
                continue
            seen_guids.add(guid)

            listings_found += 1
            if _process_offer(session, job):
                listings_new += 1

        session.commit()

        limit = data.get("limit", len(jobs))
        if len(jobs) < limit:
            logger.info("[himalayas] query=%r reached last page", query)
            break

        if page < max_pages:
            time.sleep(REQUEST_DELAY)

    return listings_found, listings_new


def scrape(session: Session, *, max_pages: int = MAX_PAGES) -> ScrapingRun:
    """Scrape Himalayas via the public Search API for ML/DS/AI roles."""
    run = ScrapingRun(portal=PORTAL_NAME, status=ScrapingStatus.RUNNING)
    session.add(run)
    session.commit()

    listings_found = 0
    listings_new = 0

    try:
        with httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            timeout=120.0,
        ) as client:
            seen_guids: set[str] = set()

            for query in SEARCH_QUERIES:
                found, new = _scrape_query(
                    client, session, query, max_pages, seen_guids
                )
                listings_found += found
                listings_new += new

                if query != SEARCH_QUERIES[-1]:
                    time.sleep(REQUEST_DELAY)

        run.status = ScrapingStatus.SUCCESS

    except Exception:
        logger.exception("[himalayas] Scraping failed")
        session.rollback()
        session.add(run)
        run.status = ScrapingStatus.FAILED

    run.finished_at = datetime.now(UTC)
    run.listings_found = listings_found
    run.listings_new = listings_new
    session.commit()

    logger.info(
        "[himalayas] Scraping complete: found=%d, new=%d, status=%s",
        listings_found,
        listings_new,
        run.status,
    )
    return run
