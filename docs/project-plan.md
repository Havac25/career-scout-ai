# Career Scout AI — Project Plan

> Consolidated document: vision, implementation plan, current status, and key architecture decisions.

---

## Table of Contents

1. [Project Vision](#project-vision)
2. [Tech Stack](#tech-stack)
3. [Target Project Structure](#target-project-structure)
4. [Implementation Plan](#implementation-plan)
   - [Phase 1: Foundation](#phase-1-foundation)
   - [Phase 2: Scraper Engine](#phase-2-scraper-engine)
   - [Phase 3: Advanced Deduplication](#phase-3-advanced-deduplication)
   - [Phase 4: LLM Scoring & Reports](#phase-4-llm-scoring--reports)
   - [Phase 5: Web UI](#phase-5-web-ui)
   - [Phase 6: Automation & Deployment](#phase-6-automation--deployment)
5. [Architecture](#architecture)
   - [Processing Flow](#processing-flow)
   - [Data Models](#data-models)
   - [Scraper Details](#scraper-details)
6. [Architecture Decision Records (ADRs)](#architecture-decision-records-adrs)
7. [Related Documents](#related-documents)

---

## Project Vision

A Python application that scrapes IT job listings from PL+FR portals in the background, deduplicates (hashing + fuzzy matching), stores in SQLite, then filters/scores them with a local LLM (Ollama) against the user's profile and agent-defined criteria. Outputs ranked HTML reports. UI via FastAPI + TailwindCSS + HTMX. Runs locally on Mac; optional migration to Oracle Cloud Free Tier.

**Cost:** $0 (Ollama is local; optional GPT-4o-mini for future enhancements ~$1-3/month).

---

## Tech Stack

| Component | Technology | Notes |
|-----------|-----------|-------|
| Language | Python 3.12 | — |
| Packaging | `uv` + `pyproject.toml` + hatchling | — |
| HTTP | `httpx` | Lightweight, async-ready |
| Scraping (JS) | `playwright` | For JS-rendered portals (e.g. WTTJ) |
| Database | SQLite + SQLAlchemy 2.0 | Zero config; PostgreSQL migration possible |
| Migrations | Alembic | — |
| Config | `pydantic-settings` + `.env` | — |
| Local LLM | Ollama (`mistral-small` / `llama3.2`) | Scoring, summaries — zero cost |
| Cloud LLM (optional) | GPT-4o-mini | Future option for trend reports |
| Scheduler | APScheduler | Scraping and report schedules |
| Web UI | FastAPI + Jinja2 + HTMX + TailwindCSS | — |
| Charts | Plotly / Chart.js | Trend visualization |
| Linting | Ruff, mypy, pre-commit | — |
| Testing | pytest, pytest-httpx | — |

---

## Target Project Structure

```
career-scout-ai/
├── pyproject.toml
├── .env
├── config/
│   ├── profile.md             # User profile: education, experience, aspirations
│   └── agents/
│       └── default.md         # Agent instructions (what offers to select)
├── data/
│   └── career_scout.db       # SQLite database (scraped offers)
├── src/career_scout_ai/
│   ├── config.py
│   ├── main.py
│   ├── scraper/
│   │   ├── stealth.py          # User-Agent pool, fingerprint
│   │   ├── rate_limiter.py     # Token bucket + jitter
│   │   ├── humanizer.py        # Random delays, human-like behavior
│   │   ├── robots_checker.py
│   │   └── portals/
│   │       ├── justjoinit.py
│   │       ├── nofluffjobs.py
│   │       ├── bulldogjob.py
│   │       ├── welcometothejungle.py
│   │       ├── apec.py
│   │       ├── lesjeudis.py
│   │       ├── welovedevs.py
│   │       └── chooseyourboss.py
│   ├── storage/
│   │   ├── models.py           # JobListing, ScrapingRun, AgentScore
│   │   ├── database.py
│   │   ├── dedup.py
│   │   └── migrations/
│   ├── scoring/
│   │   ├── ollama_client.py    # Ollama API client
│   │   └── scorer.py           # Profile + agent + offer → score + summary
│   └── web/
│       ├── app.py
│       ├── routes/
│       ├── templates/
│       └── static/
└── tests/
```

---

## Implementation Plan

### Phase 1: Foundation

- [x] Project init (`pyproject.toml`, `uv`, hatchling, pre-commit)
- [x] Pydantic Settings (`config.py`) + `.env`
- [x] SQLAlchemy models: `JobListing` (immutable), `ScrapingRun`
- [x] SQLite engine + session factory + Alembic migrations
- [x] 2-layer deduplication: URL + content hash (`dedup.py`)

### Phase 2: Scraper Engine

- [x] **JustJoinIT** scraper — public API v2, pagination, JSON-LD description
- [ ] **NoFluffJobs** scraper — internal search API + detail endpoint, multilocation dedup
- [ ] **Bulldogjob** scraper — HTML scraping
- [ ] **Welcome to the Jungle** scraper — Playwright (SPA)
- [ ] **FR portals:** APEC, LesJeudis, WeLoveDevs, ChooseYourBoss
- [ ] Stealth middleware: User-Agent pool, fingerprint masking, random delays
- [ ] Rate limiter: token bucket + jitter (8-25s base, micro/macro pauses)
- [ ] Robots checker: parse and respect `robots.txt`
- [x] Entry point `main.py` — sequential scraper execution

#### Notes

- Portals scraped sequentially (single IP → staggered, not parallel). Random order each cycle.
- NFJ requires portal-specific multilocation dedup: grouping by (title, company) and merging cities before detail fetch to avoid redundant 5-min-delayed requests.
- Stealth middleware, rate limiter, and robots checker are NOT needed for JJI (public API) or NFJ (ultra-conservative 300s delay is sufficient). They become necessary when adding HTML-scraped portals (Bulldogjob, WTTJ, FR portals) which have bot detection and higher request volumes.

### Phase 3: Advanced Deduplication

- [ ] Fuzzy cross-portal dedup (`rapidfuzz`, threshold 85%)
- [ ] Flag `is_duplicate=true` for cross-portal matches (save, don't skip)
- [ ] Optional: `sentence-transformers` embeddings + cosine similarity (layer 4)

#### Notes

- Current basic dedup (URL + content hash) is unlikely to catch cross-portal duplicates — URLs differ between portals, and descriptions/company names typically have formatting differences that break exact hash matching. Theoretically possible if content is byte-identical, but rare in practice.
- Fuzzy matching compares (company, title) of new offers against existing records. Unlike layers 1-2 which SKIP duplicates, fuzzy matches are SAVED with `is_duplicate=true` — cross-portal duplicates may contain different salary/description data worth keeping.
- Becomes valuable once ≥2 portals scrape overlapping offers (already possible with JJI + NFJ, but real value comes with more portals).

### Phase 4: LLM Scoring & Reports

- [ ] User profile file (`config/profile.md`) — education, experience, projects, aspirations
- [ ] Create `AgentScore` SQLAlchemy model + Alembic migration:
  - `job_listing_id` (FK → JobListing)
  - `agent_name` (e.g., "ml-researcher", "ai-engineering")
  - `score` (Float, 0-1)
  - `summary` (Text — why this offer is relevant)
  - `scored_at`, `model_version`
  - Unique constraint on (job_listing_id, agent_name)
- [ ] Agent definition as .md file (`config/agents/default.md`) — describes what kind of offers to select. Scoring prompt combines profile + agent instructions + offer → score (0-1) + summary. Adding a new agent = new .md file in `config/agents/`
- [ ] Ollama client + retry logic + timeout handling

#### Notes

- Ollama-only (no paid models). Design so swapping to an API model is trivial (same prompt, different client).
- ~200 offers/day × ~10s/offer = ~33 min batch — acceptable for daily run.
- No separate CV parser needed — profile is a plain .md file read directly.
- Multi-agent design: adding a new agent = new .md instruction file + scoring run. No migration needed.
- Re-scoring one agent (e.g., after prompt change) doesn't affect other agents' results.

### Phase 5: Web UI

- [ ] Static HTML report with top offers ranked by score + summaries
- [ ] FastAPI + Jinja2 + HTMX + TailwindCSS (+ DaisyUI)
- [ ] Views: Dashboard, Listings (filtering/sorting), Reports, Settings
- [ ] Charts: Plotly — tech trends, salary ranges, % remote

#### Notes

- **MVP first:** Start with a simple list of best-matched offers against user's CV (basic agent, no dashboards/charts).

### Phase 6: Automation & Deployment

- [ ] APScheduler — staggered scraping cycles (every 3h, random portal order, 10-30 min pauses)
- [ ] Health checks + monitoring
- [ ] `launchd` plist (macOS auto-start) / Docker (optional)
- [ ] Optional migration: Oracle Cloud Free Tier (ARM 4 cores, 24 GB RAM, $0/month)

---

## Architecture

### Processing Flow

```
Portal API
    │
    ▼
┌──────────────────────────────────────────────────┐
│ 1. FETCH LISTINGS (per portal)                   │
│    API request → list of offers (basic metadata) │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ 2. PRELIMINARY DEDUP                             │
│    URL exact match → SKIP (don't fetch detail)   │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ 3. FETCH DETAIL                                  │
│    JJI: HTML page → JSON-LD description          │
│    NFJ: /api/posting/{slug} → description+salary │
└────────────────────────┬─────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────┐
│ 4. FINAL DEDUP                                   │
│    Layer 1: URL exact match → SKIP               │
│    Layer 2: content_hash match → SAVE (duplicate)│
│                                                  │
│    content_hash = SHA256(                        │
│      title.lower().strip() |                     │
│      company.lower().strip() |                   │
│      description.lower().strip()                 │
│    )                                             │
└────────────────────────┬─────────────────────────┘
                         │ (new or marked duplicate)
                         ▼
                     [ SQLite ]
```

### Data Models

#### `JobListing`

Immutable record per scraped offer.

| Field | Type | Notes |
|-------|------|-------|
| `id` | Integer, PK | Auto-increment |
| `portal` | String(50) | Source portal name |
| `url` | String(2048), unique | Direct link, also dedup layer 1 |
| `title` | String(500) | |
| `company` | String(300) | |
| `location_raw` | String(500), nullable | Raw text, not parsed |
| `workplace_type` | String(20), nullable | e.g. "remote", "office", "hybrid" |
| `contract_types` | String(200), nullable | Comma-separated, e.g. "b2b, uop" |
| `salary_raw` | String(500), nullable | Raw salary string |
| `description_raw` | Text, nullable | Full description (HTML stripped) |
| `posted_at` | DateTime, nullable | Publication date on portal |
| `scraped_at` | DateTime | Server-default `now()` |
| `content_hash` | String(64) | SHA256 — dedup layer 2 |
| `is_duplicate` | Boolean | Default false |
| `embedding` | LargeBinary, nullable | Reserved for future ML dedup |

Indexes: `(portal, scraped_at)`, `(content_hash)`, `(company, title)`.

#### `ScrapingRun`

Operational log per scraper execution.

| Field | Type | Notes |
|-------|------|-------|
| `id` | Integer, PK | Auto-increment |
| `portal` | String(50) | |
| `started_at` | DateTime | Server-default `now()` |
| `finished_at` | DateTime, nullable | |
| `listings_found` | Integer | Total offers seen |
| `listings_new` | Integer | Offers inserted (after dedup) |
| `status` | String(20) | running / success / failed / partial |
| `error_message` | Text, nullable | |

### Scraper Details

#### JustJoinIT

- **Source:** Public API `api.justjoin.it/v2/user-panel/offers`
- **Method:** Paginated GET (50/page, max 5 pages)
- **Categories:** Other/DS(5), DevOps/MLOps(12), Data(19), Architecture(23), C-level/AI(25)
- **Description:** Fetched separately from offer HTML page via JSON-LD `<script>` tag (requires second HTTP client)
- **Rate limiting:** 1s between pages, 0.5s between detail (HTML) requests
- **Dedup:** Preliminary URL check before fetching description; hash recomputed after description fetch

#### NoFluffJobs

- **Source:** Internal API `nofluffjobs.com/api/search/posting` + `/api/posting/{slug}`
- **Method:** Single POST (limit=500), then detail GET per unique offer
- **Categories:** data, artificialIntelligence, businessIntelligence
- **Dedup:** Multilocation entries merged by (title, company) before detail fetch; preliminary URL check before detail; full hash check after detail
- **Rate limiting:** 300s (5 min) between detail requests (~12 req/h)
- **Params:** `salaryCurrency=PLN`, `salaryPeriod=month` — required by API (does NOT filter, only converts displayed salary)

---

## Architecture Decision Records (ADRs)

| # | Date | Decision | Rationale |
|---|------|----------|-----------|
| 1 | 2026-04 | **SQLite** as database | Zero config, sufficient for ~200 listings/day. PostgreSQL migration possible via SQLAlchemy. |
| 2 | 2026-04 | **2-layer dedup** (URL + content hash) instead of planned 3 layers | Fuzzy matching only makes sense with multiple portals. Layers 1-2 suffice for MVP. |
| 3 | 2026-04 | **Content hash** = SHA256(title + company + description), not location | Description better identifies uniqueness. Multilocation offers have identical description but different locations. |
| 4 | 2026-05 | **JJI description** from JSON-LD (schema.org JobPosting) | Simpler than DOM parsing. Stable format. |
| 5 | 2026-05 | **NFJ salaryCurrency/salaryPeriod** = PLN/month | Doesn't filter — only converts displayed amount. Without them API returns 0 results. |
| 6 | 2026-05 | **NFJ detail delay** = 300s (~12 req/h) | Conservative limit. `robots.txt` disallows `/api/`. Safety > speed. |
| 7 | 2026-05 | **NFJ multilocation dedup** before detail fetch | Group by (title, company). Without this: 3× more detail requests = 3× longer. |
| 8 | 2026-05 | **Sequential** scraper execution (not parallel) | Single IP, code simplicity. Scheduler (APScheduler) in Phase 6. |

---

## Related Documents

- [legal.md](legal.md) — scraping legal analysis per portal
