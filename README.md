# Career Scout AI

AI-powered job market analyzer that scrapes listings, filters them using LLMs, and generates personalized skill-gap reports.

## Python Version

This project targets **Python 3.12**.

## Setup Instructions

### Prerequisites

Install the [uv](https://docs.astral.sh/uv/getting-started/installation/) package manager.

### Getting Started

1. Install Python 3.12 and sync project dependencies (uv handles Python installation automatically):
   ```bash
   uv python install 3.12
   uv sync
   ```

2. Install pre-commit hooks:
   ```bash
   uv run pre-commit install
   ```

That's it! Pre-commit hooks will now run automatically on every `git commit`.

> **Tip:** To manually run all hooks against every file (e.g., to verify setup), use:
> ```bash
> uv run pre-commit run --all-files
> ```

## Configuration

To configure the application, create a `.env` file in the root directory of the project and define the required environment variables. For example:

```
APP_NAME=Career Scout AI
```

This variable is used to set the name of the application. Ensure that the `.env` file is excluded from version control by keeping it listed in `.gitignore`.

## Usage

### Running the Scraper

```bash
uv run career-scout-ai
```

Results are stored in `data/career_scout.db` (SQLite). Logs go to `data/scraper.log`.

### Running the Web UI Dashboard

```bash
python -m career_scout_ai.web
```

Opens an interactive cyberpunk-themed dashboard on `http://localhost:8000` displaying job recommendations, match scores, and detailed offer analysis.

**Note:** The dashboard requires scraped data and agent scores. Run the scraper first, then start the Web UI.

## Documentation

See `docs/` for detailed project documentation:

- [`docs/project-plan.md`](docs/project-plan.md) — vision, architecture, implementation plan, status, and ADRs
- [`docs/setup-guide.md`](docs/setup-guide.md) — setup instructions, running scraper and Web UI, troubleshooting
- [`docs/legal.md`](docs/legal.md) — scraping risk analysis per portal
