# Career Scout AI — Project Plan

> Status: Production-ready PoC. Core functionality complete and operational. What has been built, and what comes next.

---

## Table of Contents

1. [Project Vision](#project-vision)
2. [What Has Been Done](#what-has-been-done)
    - [Overview](#overview)
    - [Data Ingestion & Scraping](#data-ingestion--scraping)
    - [Data Storage & Deduplication](#data-storage--deduplication)
    - [Scoring & Intelligence](#scoring--intelligence)
    - [User Interface](#user-interface)
3. [Future Improvements](#future-improvements)
    - [Phase 2 (Continued): More Portals](#phase-2-continued-more-portals)
    - [Phase 3: Advanced Deduplication](#phase-3-advanced-deduplication)
    - [Phase 5 (Enhanced): Advanced UI Features](#phase-5-enhanced-advanced-ui-features)
    - [Phase 6: Automation & Deployment](#phase-6-automation--deployment)
4. [Related Documents](#related-documents)

---

## Project Vision

A Python application that scrapes IT job listings from PL+FR portals in the background, deduplicates (hashing + fuzzy matching), stores in SQLite, then filters/scores them with a cloud LLM (Gemini via OpenRouter) against the user's profile and agent-defined criteria. Outputs ranked HTML reports. UI via FastAPI + vanilla JavaScript. Runs locally on Mac; optional migration to Oracle Cloud Free Tier.

**Cost:** Minimal pay-as-you-go API costs (typically <$1/month utilizing Gemini 2.5 Flash via OpenRouter; local Ollama client archived for potential future $0 cost offline runs).

---

> For tech stack details, system architecture diagrams, database schema, project structure, scraper workflows, and architectural decisions, see [architecture.md](architecture.md).

---

## What Has Been Done

### Overview

Career Scout AI is a **production-ready proof of concept** with full end-to-end functionality:
- **Data pipeline:** Scrapes job listings from 3 major portals (PL/FR)
- **Deduplication:** Multi-layer content-based dedup prevents duplicates
- **Intelligence:** Cloud LLM (Gemini 2.5 Flash) scores jobs against user profiles
- **Extensibility:** Agent-based personas via markdown files; add new scoring criteria without code changes
- **UI:** Real-time dashboard with cyberpunk theme, pagination, expandable job details
- **Database:** SQLite with Alembic migrations, zero-config setup

All core flows have been tested and validated. The system currently processes ~200 new job listings per day with scoring completion in 30-50 minutes.

### Data Ingestion & Scraping

**JustJoinIT Scraper** ✅
- Integrated with public v2 API (`/v2/user-panel/offers`)
- Pagination support with configurable `max_pages` limit
- Fetches job descriptions via JSON-LD schema (schema.org JobPosting)
- Implements preliminary deduplication checks before detail fetch
- Rate limiting: 0.5s delay for detail fetches, 1.0s between pages
- **Status:** Fully functional, production-ready

**NoFluffJobs Scraper** ✅
- Integrated with internal search API (`/api/search/posting`)
- Single-batch fetch with up to 500 results per request
- In-memory deduplication: groups multi-location posts by (title, company) to avoid redundant detail requests
- Conservative rate limiting: 300s (~5 min) delay per detail fetch to respect limits
- Fetches original salary and full description per listing
- **Status:** Fully functional, production-ready

**Welcome to the Jungle Scraper** ✅
- Integrated with Algolia Search API directly (bypassing SPA scraping and AWS WAF challenges)
- Fetches job descriptions natively from the `profile` field in the Algolia response
- Skips job listings missing the necessary metadata
- **Status:** Fully functional, production-ready

**Deduplication at Ingestion** (Layer 1-2)
- Layer 1: URL-based duplicate check (prevents re-scraping same URLs)
- Layer 2: Content hash (SHA256 of title+company+description) prevents identical offers from different portals
- Cross-portal duplicates are flagged (`is_duplicate=true`) but saved for alternate salary/description data
- **Status:** Fully functional

### Data Storage & Deduplication

**SQLite + SQLAlchemy Database** ✅
- Zero-config setup with automatic migrations via Alembic
- Current schema: 3 tables (JobListing, ScrapingRun, AgentScore)
- JobListing: immutable record with URL, title, company, content_hash, is_duplicate flag, created_at
- ScrapingRun: tracks execution metadata (start_time, end_time, status)
- AgentScore: stores LLM evaluations with unique constraint on (job_listing_id, agent_name)
- **Status:** Production database with working migrations

**Content-Based Deduplication** ✅
- Hashing strategy: SHA256(title + company + description) avoids location-based false positives
- Multilocation offers have identical description but different locations → not deduplicated
- Reserved column for Layer 4 (embedding-based) dedup; not yet populated
- **Status:** Layers 1-2 fully operational; Layer 4 reserved for future

### Scoring & Intelligence

**OpenRouter Cloud LLM Integration** ✅
- Model: Gemini 2.5 Flash (via OpenRouter API)
- Cost-effective: $0.075 per 1M tokens (~$0.01-0.05 per daily run)
- Strict JSON schema enforcement ensures parsed output
- Retry logic with exponential backoff for transient failures
- Response healing: malformed JSON is auto-corrected before parsing
- **Status:** Production-ready with error handling

**Ollama Local LLM Fallback** ✅ (Archived)
- Model: Qwen 2.5 3B via Ollama HTTP API (localhost)
- Kept in codebase for potential offline/self-hosted deployments
- ~6 GB RAM requirement (fits on Oracle Cloud A1 24GB free tier)
- **Status:** Functional but archived in favor of cloud LLM for simplicity

**Multi-Agent Scoring Engine** ✅
- Agents defined as markdown files in `config/agents/`
- Each agent has custom instructions (rubric) for evaluating offers
- Scoring workflow:
  1. Load user profile (`config/profile.md`) and agent rubrics
  2. Fetch unscored, non-duplicate job listings
  3. For each agent, for each offer: build prompts → call LLM → parse JSON → store score
- Output: score (0.0-1.0) + summary (LLM reasoning)
- Idempotent: unique constraint on (job_listing_id, agent_name) prevents duplicate calls
- New agents can be added without code changes or migrations
- **Status:** Fully operational with multi-agent support

**Score Calculation & Storage**
- Model version tracking: each score records which LLM version was used
- Timestamps: scored_at field for audit trails
- Re-scoring: only new unscored offers are processed; re-running engine skips already-scored items
- **Status:** Production-ready

### User Interface

**FastAPI Backend** ✅
- REST API with 3 endpoints:
  - `GET /api/stats` — summary statistics (total offers, avg/max scores, last scan timestamp)
  - `GET /api/recommendations` — paginated job listings with best agent scores
  - Browser auto-open on startup (configurable via .env)
- Async-ready with SQLAlchemy session factory
- Response filtering: only non-duplicate offers, last 7 days, highest score per job
- **Status:** Production-ready

**Web Dashboard (Cyberpunk Theme)** ✅
- **Mission Control Dashboard** — Cyberpunk-themed interface with glitch effects, neon colors, grid background, CRT scanlines
- **Real-time Stats Header:**
  - "Targets Acquired" (total unique offers)
  - "Avg Match Score" (average across all scores)
  - "Top Score" (highest score)
  - "Last Scan" (last scraping execution timestamp)
- **Job Listings Table:**
  - Sorted by score descending
  - Color-coded match indicators: CRITICAL (0.8+), STRONG (0.6-0.8), CANDIDATE (0.4-0.6), BACKUP (0.2-0.4), REJECT (<0.2)
  - Portal badges (JJI, NFJ) showing job source
  - Direct links to original job postings
- **Expandable Job Details:**
  - Single-click expansion reveals two tabs:
    - Tab 1: AI Analysis (LLM score + summary from best agent)
    - Tab 2: Offer Details (full job description, company, salary, etc.)
  - Smooth animations and interactions
- **Pagination & Filtering:**
  - "Load More" button for browsing results
  - Configurable results per page
  - Date filter allowing users to select a custom cutoff date for displayed offers
- **Frontend Stack:**
  - Vanilla HTML/CSS/JavaScript (894 lines, no framework dependencies)
  - No build step required
  - Full control over styling and interactions
- **Configuration:**
  - Port and host via `.env` (WEB_HOST, WEB_PORT)
  - Browser auto-opens on server startup
- **Status:** Production-ready PoC with distinctive brand identity

---

## Future Improvements

### Phase 2 (Continued): More Portals

**Priority: High** — Expands coverage to FR, EU remote, and US remote markets.

#### Selected Portals (Next Implementation Batch)

| Portal | Region | Type | Effort | Notes |
|--------|--------|------|--------|-------|
| **Himalayas** | Global remote | Free JSON API (no auth) | Low | Best API — keyword/seniority/timezone search, 200-500 ML/AI listings |
| **Remotive** | Global remote | Free JSON API (no auth) | Low | Category filter (`?category=data`), 50-200 remote ML/DS listings |
| **AI-Jobs.net** | Global remote | HTML scraping | Low | 100% AI/ML niche, 500-2000 listings, very open robots.txt |
| **Free-Work** | FR | HTML scraping | Low-Medium | Major French IT board (15k+ offers), strong for B2B/freelance ML roles |

#### Worth Considering (Future Expansion)

| Portal | Region | Type | Effort | Notes |
|--------|--------|------|--------|-------|
| APEC | FR | Internal JSON API | Medium | Quasi-public French service for senior "cadres", 300-800 ML/DS listings |
| WeLoveDevs | FR | HTML scraping | Low | No robots.txt restrictions, small volume (50-150) |
| Otta | EU/US | SPA (Playwright) | Medium | Wide-open robots.txt, curated quality tech listings, 100-300 ML/AI |
| WeWorkRemotely | US remote | RSS + HTML | Low | RSS feeds available, open robots.txt, small volume (30-100) |
| Arbeitnow | EU remote | Free JSON API | Low | Free public API, Germany-focused but has EU remote, 50-150 ML/DS |
| Wellfound | US startups | Headless + stealth | High | Cloudflare-protected, good for AI startup roles, 200-500 listings |
| LesJeudis | FR | Headless + stealth | High | Cloudflare-protected, 100-300 IT listings |
| Bulldogjob | PL | HTML scraping | Medium | Bot detection likely; deprioritized (NFJ+JJI cover PL well) |
| ChooseYourBoss | FR | HTML scraping | Medium | Small volume (50-100), unclear bot detection stance |

**What's needed:**
- Stealth middleware: User-Agent pool, fingerprint masking, random human-like delays
- Rate limiter: token bucket algorithm + jitter (8-25s base, micro/macro pauses)
- Robots.txt checker: parse and respect robots.txt per portal
- Playwright integration for SPA portals (Otta)
- Portal-specific scraper logic: adapt to each site's structure

**Estimated impact:** +300-600 new ML/AI listings/day across all 5 selected portals.

### Phase 3: Advanced Deduplication

**Priority: Medium** — Improves data quality; catches cross-portal duplicates with minor content variations.

**Fuzzy Matching (Layer 3)**
- Use `rapidfuzz` library to compare (company, title) of new offers vs existing records
- Threshold: 85% similarity
- Flag fuzzy matches as `is_duplicate=true` (save, don't skip)
- Benefit: Catches offers with slight wording differences across portals (e.g., "Senior Backend Engineer" vs "Senior Backend Software Engineer")

**Embedding-Based Dedup (Layer 4)** *(optional; reserved schema column)*
- Use `sentence-transformers` to generate embeddings for offer descriptions
- Compute cosine similarity against existing embeddings
- High similarity (e.g., >0.95) flags as duplicate
- Benefit: Catches semantic duplicates (same job, very different wording)

**When to implement:** Becomes valuable once 3+ portals are scraping overlapping positions. Currently only 2 portals active, so basic hashing suffices for MVP.

### Phase 5 (Enhanced): Advanced UI Features

**Priority: Low-Medium** — Improves user experience; nice-to-have features beyond core MVP.

**Charts & Visualizations**
- Tech trends: bar chart of most-requested technologies (extracted via LLM)
- Salary ranges: histogram of salary bands by role/seniority
- Remote % distribution: pie chart showing remote/hybrid/office split

**Filtering & Search**
- Filter by portal (JJI, NFJ, WTTJ, etc.)
- Filter by score range (show only "CRITICAL" offers, etc.)
- Search by keyword (title, company, location)

**Export Functionality**
- Export recommendations to CSV (job title, company, score, summary, link)
- Export as HTML report (styled, shareable)
- Export as JSON (for downstream processing)

**Agent Management UI**
- View/edit agents in web UI instead of editing .md files directly
- Add/remove agents without restarting
- Test scoring on single offer before bulk run

**Additional Dashboard Features**
- Historical trends: graph of average scores over time
- Agent comparison: side-by-side scores for same offer across agents
- Notification system: alert when high-match jobs appear
- Job watchlist: save interesting offers for later review

### Phase 6: Automation & Deployment

**Priority: High** — Required for autonomous 24/7 operation beyond development.

**Scheduled Scraping**
- APScheduler for background job scheduling
- Staggered scraping cycles: every 3 hours, randomized portal order
- 10-30 minute pauses between portals to avoid rate limit detection
- Health checks: log successes/failures, alert on repeated errors

**Deployment Options**

*Local (Mac):*
- `launchd` plist for auto-start on boot
- Systemd service file (for Linux)

*Cloud (Oracle Free Tier):*
- Migrate to Oracle Cloud ARM instance (4 cores, 24 GB RAM, $0/month)
- Docker containerization for consistent environment
- Optional: Run local Ollama on cloud for fully offline operation

**Monitoring & Logging**
- Structured logging (JSON format) for easy parsing
- Log rotation to avoid disk fill
- Metrics: job count per run, execution time, error rate
- Optional: Send metrics to monitoring service (e.g., Datadog, New Relic)

**Database Backups**
- Periodic backups of SQLite file
- Backup retention policy (e.g., keep last 30 days)
- Optional: Migrate to PostgreSQL for multi-user/production resilience

---

## Related Documents

- [architecture.md](architecture.md) — tech stack, system architecture, database schema, project structure, scraper workflows, and architectural decisions
- [setup-guide.md](setup-guide.md) — instructions on setting up, running, troubleshooting, and scheduling the pipeline
- [legal.md](legal.md) — scraping legal analysis per portal
- [original-plan.md](archive/original-plan.md) — archive: original full plan (model details, deployment, rate limits)
- [decisions.md](archive/decisions.md) — archive: ADRs in full format (context/decision/rationale)
- [roadmap.md](archive/roadmap.md) — archive: original Phase 1 & 2 implementation milestones (Polish)
