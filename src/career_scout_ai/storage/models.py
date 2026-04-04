from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class ScrapingStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


class JobListing(Base):
    __tablename__ = "job_listings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Scraper fields (deterministic, immutable after insert)
    portal: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    company: Mapped[str] = mapped_column(String(300), nullable=False)
    location_raw: Mapped[str | None] = mapped_column(String(500))
    workplace_type: Mapped[str | None] = mapped_column(String(20))
    contract_types: Mapped[str | None] = mapped_column(String(200))
    salary_raw: Mapped[str | None] = mapped_column(String(500))
    description_raw: Mapped[str | None] = mapped_column(Text)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime)
    scraped_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Dedup fields
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Embedding (optional, for future dedup layer 4)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)

    __table_args__ = (
        Index("ix_portal_scraped", "portal", "scraped_at"),
        Index("ix_content_hash", "content_hash"),
        Index("ix_company_title", "company", "title"),
    )


class ScrapingRun(Base):
    __tablename__ = "scraping_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    portal: Mapped[str] = mapped_column(String(50), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    listings_found: Mapped[int] = mapped_column(Integer, default=0)
    listings_new: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default=ScrapingStatus.RUNNING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)
