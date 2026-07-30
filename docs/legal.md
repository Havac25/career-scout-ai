# Legal Analysis — Scraping

## Key Principles (EU/GDPR/Copyright)

- **Personal use** significantly reduces legal risk vs. commercial use
- **EU Database Directive (96/9/EC)** — extracting a "substantial part" of a database is prohibited; 10-20 listings/h per portal is minimal extraction
- **GDPR** — we do not store personal data of recruiters (names, emails, phones); we only parse job listing content
- **robots.txt** — respecting it = evidence of good faith
- **No redistribution** — scraped data stays local, never published
- **LinkedIn: SKIPPED.** The only portal where risk is real (ToS + active enforcement)

## Portal Risk Assessment

| Portal | Risk | Method | Rate limit | Status |
|--------|------|--------|-----------|--------|
| **JustJoinIT** | LOW | Public API | 30-60 req/h | ✅ Implemented |
| **NoFluffJobs** | MEDIUM | Internal JSON API | ~12 req/h | ✅ Implemented |
| **Welcome to the Jungle** | LOW-MEDIUM | Algolia Search API | ~60 req/h | ✅ Implemented |
| **Himalayas** | LOW | Public API | ~24 req/h | ✅ Implemented |
| **AI-Jobs.net** | LOW | Scraping (fully open robots.txt) | ~30-40 req/h | ✅ Implemented |
| **Bulldogjob** | MEDIUM-LOW | Scraping | 10-15 req/h | 📋 Planned |
| **APEC** | MEDIUM-LOW | Scraping | 10-15 req/h | 📋 Planned |
| **LesJeudis** | MEDIUM | Scraping | 8-12 req/h | 📋 Planned |
| **WeLoveDevs** | MEDIUM-LOW | Scraping | 8-12 req/h | 📋 Planned |
| **ChooseYourBoss** | MEDIUM | Scraping | 8-12 req/h | 📋 Planned |
| **LinkedIn** | HIGH | — | — | ❌ Skipped |

## Detailed Justifications

### JustJoinIT — LOW
Has a public API (`api.justjoin.it`). Data is publicly accessible. We use the official API — no scraping needed.

### NoFluffJobs — MEDIUM
Internal JSON API (`/api/posting`, `/api/search/posting`) used by the frontend. `robots.txt` disallows `/api/`. Polish company, GDPR applies. Conservative rate-limit (5 min/request) as mitigation.

### AI-Jobs.net — LOW
`robots.txt` fully open (`Allow: /`, only `/account/` disallowed) — the most permissive stance of any portal checked. No API is exposed, so listing and detail pages are fetched as plain server-rendered HTML (no JS rendering, WAF, or bot-detection encountered). Rate-limited conservatively (~1.5-2s between requests) despite the low risk.

### LinkedIn — HIGH (SKIPPED)
ToS explicitly prohibit scraping. LinkedIn actively pursues scrapers (hiQ Labs case). Aggressive bot detection.
