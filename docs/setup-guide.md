# Setup Guide

This guide provides instructions on how to set up and run the `career-scout-ai` pipeline on a supported system.

**Supported platforms:** Ubuntu 22.04 LTS / 24.04 LTS and macOS.

---

## 1. Automated Installation

A single setup script handles all dependencies, the Python environment, the database, and background scheduling.

1. **Clone the repository:**
   ```bash
   git clone git@github.com:Havac25/career-scout-ai.git
   cd career-scout-ai
   ```

2. **Run the setup script:**

   - **Production Ubuntu VM** (installs systemd scheduling):
     ```bash
     chmod +x setup.sh
     ./setup.sh
     ```

   - **Local development** (macOS or Ubuntu without scheduling):
     ```bash
     chmod +x setup.sh
     ./setup.sh --local
     ```

   *(Note: The script will prompt for your `sudo` password on Ubuntu to install system packages.)*

3. **Reload your shell:**
   The script appends the `uv` binary path to your shell rc file (`~/.zshrc` on zsh, `~/.bashrc` on bash). Reload it before running any `uv` commands manually:
   ```bash
   source ~/.zshrc   # or ~/.bashrc
   ```

---

## 2. AI Scoring (Ollama) — Not Currently Supported

The scoring and filtering phase of `career-scout-ai` was previously powered by a local LLM via **Ollama** (`qwen2.5:3b`). **Ollama integration is currently disabled** — the setup script no longer installs or configures it, and the pipeline will not invoke the scoring phase.

If you want to install Ollama manually for future use or local experimentation:

- **Ubuntu:**
  ```bash
  curl -fsSL https://ollama.com/install.sh | sh
  ollama pull qwen2.5:3b
  ```
- **macOS:**
  ```bash
  brew install ollama
  ollama pull qwen2.5:3b
  ```

> Even after manual installation, the pipeline will not invoke scoring until Ollama support is re-enabled in a future release.

---

## 3. Post-Installation: Troubleshooting `uv: command not found`

`uv` is installed to `~/.local/bin`. If the command is not found after setup, reload your shell rc file:

```bash
source ~/.zshrc    # zsh (macOS default)
# or
source ~/.bashrc   # bash (Ubuntu default)
```

Verify the PATH entry was written:

```bash
grep '.local/bin' ~/.zshrc    # or ~/.bashrc
```

If missing, add it manually:

```bash
echo 'export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

---

## 4. Background Scheduling (Ubuntu Only)

When `./setup.sh` is run **without** `--local` on Ubuntu, it automatically configures the application to run daily at **02:00 Warsaw time** using a `systemd` user timer. `Persistent=true` ensures the task catches up immediately if the VM was offline at the scheduled time.

Manage the scheduler with these commands:

```bash
# Check when the job is scheduled to run next
systemctl --user list-timers career-scout-ai.timer

# View execution logs in real-time
journalctl --user -u career-scout-ai.service -f

# Trigger a run manually right now
systemctl --user start career-scout-ai.service

# Disable the daily schedule temporarily
systemctl --user disable --now career-scout-ai.timer
```

**macOS:** Scheduling is not supported (`systemd` is Linux-only). Use `--local` when running the setup script and trigger runs manually — see Section 5.

---

## 5. Running the Web UI

The Career Scout AI Web UI is a real-time dashboard for viewing job recommendations and match scores.

### Starting the Server

```bash
# Option 1: via Python module
python -m career_scout_ai.web

# Option 2: via uv
uv run career-scout-ai --web
```

The server starts on `http://localhost:8000` by default (configurable via `.env`):
- `WEB_HOST` — Bind address (default: `127.0.0.1`)
- `WEB_PORT` — Port number (default: `8000`)

**Browser Auto-Open:** The application automatically opens your default browser to the dashboard on startup.

### Dashboard Features

- **Mission Control Interface** — Cyberpunk-themed dashboard showing job recommendations
- **Real-time Statistics** — Total targets, average match score, highest score, last scan timestamp
- **Job Listings** — Paginated table of non-duplicate offers sorted by match score
- **Job Details** — Click any row to expand and view:
  - **AI Analysis** — LLM-generated scoring rationale and match tier
  - **Offer Details** — Location, workplace type, salary, contract terms, description, and direct job link
- **Score Indicators** — Color-coded tiers (CRITICAL, STRONG, CANDIDATE, BACKUP, REJECT)
- **Portal Badges** — Visual indicators showing job source (JJI, NFJ)

### Data Requirements

The dashboard displays data from the last 7 days. To see meaningful content:

1. Run the scraper to populate job listings:
   ```bash
   uv run career-scout-ai
   ```

2. Ensure scoring has completed. Jobs must have agent scores to appear in recommendations.

3. The `/api/stats` endpoint shows only non-duplicate offers with agent scores.

---

## 6. Running the Application Manually

```bash
# 1. Navigate to the project directory
cd /path/to/career-scout-ai

# 2. Run the main script
uv run career-scout-ai
```

> **Note:** The AI scoring phase is currently disabled. See Section 2 for details.

---

## 7. AI Assistant Guidelines

When initializing or running the pipeline, ensure `config/profile.md` and `config/agents/` are properly populated. These files are required for the scoring engine to evaluate and filter job listings effectively.
