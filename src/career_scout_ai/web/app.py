from __future__ import annotations

from collections.abc import Generator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from career_scout_ai.config import AppConfig
from career_scout_ai.storage.database import get_engine, get_session_factory
from career_scout_ai.storage.models import AgentScore, JobListing

config = AppConfig()
TEMPLATES_DIR = Path(__file__).parent / "templates"

# Module-level engine — created once when the server starts
_engine = get_engine(config.database_path)
_SessionFactory = get_session_factory(_engine)


def get_db() -> Generator[Session, None, None]:
    with _SessionFactory() as session:
        yield session


DbDep = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    _engine.dispose()


app = FastAPI(title="Career Scout AI — Mission Control", lifespan=lifespan)


def _cutoff() -> datetime:
    return datetime.now() - timedelta(days=7)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/", response_class=FileResponse)
async def index() -> FileResponse:
    return FileResponse(TEMPLATES_DIR / "index.html", media_type="text/html")


@app.get("/api/stats")
async def get_stats(db: DbDep) -> JSONResponse:
    """Summary statistics for the header bar (last-week window)."""
    cutoff = _cutoff()

    filters = [
        JobListing.is_duplicate.is_(False),
        JobListing.scraped_at >= cutoff,
    ]

    total = db.execute(
        select(func.count())
        .select_from(JobListing)
        .join(AgentScore, AgentScore.job_listing_id == JobListing.id)
        .where(*filters)
    ).scalar_one()

    avg_score = db.execute(
        select(func.avg(AgentScore.score))
        .select_from(AgentScore)
        .join(JobListing, AgentScore.job_listing_id == JobListing.id)
        .where(*filters)
    ).scalar_one()

    max_score = db.execute(
        select(func.max(AgentScore.score))
        .select_from(AgentScore)
        .join(JobListing, AgentScore.job_listing_id == JobListing.id)
        .where(*filters)
    ).scalar_one()

    last_scan = db.execute(select(func.max(JobListing.scraped_at))).scalar_one()

    return JSONResponse(
        {
            "total": total,
            "avg_score": round(float(avg_score), 3) if avg_score is not None else 0.0,
            "max_score": round(float(max_score), 3) if max_score is not None else 0.0,
            "last_scan": last_scan.isoformat() if last_scan else None,
        }
    )


@app.get("/api/recommendations")
async def get_recommendations(
    db: DbDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    """
    Paginated job recommendations sorted by score descending.
    Only includes non-duplicate offers scraped within the last 1 week.

    When multiple agents score the same job, the highest-scoring agent row
    is used (via a MAX subquery), keeping each job appearing at most once.
    """
    cutoff = _cutoff()

    filters = [
        JobListing.is_duplicate.is_(False),
        JobListing.scraped_at >= cutoff,
    ]

    # Subquery: best score per job listing across all agents
    best_score_sq = (
        select(
            AgentScore.job_listing_id,
            func.max(AgentScore.score).label("best_score"),
        )
        .group_by(AgentScore.job_listing_id)
        .subquery()
    )

    total = db.execute(
        select(func.count())
        .select_from(JobListing)
        .join(best_score_sq, best_score_sq.c.job_listing_id == JobListing.id)
        .where(*filters)
    ).scalar_one()

    rows = db.execute(
        select(JobListing, AgentScore)
        .join(AgentScore, AgentScore.job_listing_id == JobListing.id)
        .join(
            best_score_sq,
            (best_score_sq.c.job_listing_id == AgentScore.job_listing_id)
            & (best_score_sq.c.best_score == AgentScore.score),
        )
        .where(*filters)
        .order_by(desc(AgentScore.score))
        .offset(offset)
        .limit(limit)
    ).all()

    items = [
        {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "portal": job.portal,
            "url": job.url,
            "score": round(float(score.score), 3),
            "summary": score.summary,
            "agent_name": score.agent_name,
            "model_name": score.model_name,
            "scored_at": score.scored_at.isoformat() if score.scored_at else None,
            "location": job.location_raw,
            "workplace_type": job.workplace_type,
            "contract_types": job.contract_types,
            "salary": job.salary_raw,
            "description": job.description_raw,
            "posted_at": job.posted_at.isoformat() if job.posted_at else None,
            "scraped_at": job.scraped_at.isoformat() if job.scraped_at else None,
        }
        for job, score in rows
    ]

    return JSONResponse(
        {
            "items": items,
            "offset": offset,
            "limit": limit,
            "total": total,
            "has_more": (offset + len(items)) < total,
        }
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def serve() -> None:
    import threading
    import time
    import webbrowser

    import uvicorn

    # Auto-open browser after server starts
    def open_browser():
        time.sleep(2)  # Wait for server to start
        url = f"http://{config.web_host}:{config.web_port}"
        webbrowser.open(url)

    thread = threading.Thread(target=open_browser, daemon=True)
    thread.start()

    uvicorn.run(app, host=config.web_host, port=config.web_port)
