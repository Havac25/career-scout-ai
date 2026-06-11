from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
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

    agent_scores: Mapped[list["AgentScore"]] = relationship(
        back_populates="job_listing", lazy="select"
    )

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


class AgentScore(Base):
    __tablename__ = "agent_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_listing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_listings.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)

    job_listing: Mapped["JobListing"] = relationship(
        back_populates="agent_scores", lazy="select"
    )

    __table_args__ = (
        UniqueConstraint("job_listing_id", "agent_name", name="uq_listing_agent"),
        Index("ix_agent_name_score", "agent_name", "score"),
    )
