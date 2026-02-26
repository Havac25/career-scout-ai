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
