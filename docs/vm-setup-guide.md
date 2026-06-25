# VM Setup Guide: Career Scout AI

This document contains the technical specification and setup instructions for the Virtual Machine intended to host the Career Scout AI pipeline and the local LLM (Ollama).

## 1. Hardware Specification (Target: Oracle Cloud Free Tier)

*   **Instance Type:** OCI Ampere A1 Compute (ARM-based)
*   **OCPUs:** 4
*   **RAM:** 24 GB (Critical: Qwen3-8B requires ~6-8GB, leaving enough for system cache and future web UI)
*   **Boot Volume:** 50 GB+ (Standard)
*   **OS:** Ubuntu 22.04 LTS or 24.04 LTS

## 2. Infrastructure Configuration

*   **Networking:**
    *   Ingress Rule: Allow TCP `22` (SSH) from specific IP ranges.
    *   Ingress Rule (Optional): Allow TCP `11434` (Ollama API) if external access to the LLM is needed for debugging.
    *   Ingress Rule (Future): Allow TCP `80/443` for the Phase 5 HTMX UI.

## 3. Application Deployment & Automation

To make the installation seamless, an automated script is provided for Ubuntu environments.

1. **Clone the repository:**
   ```bash
   git clone git@github.com:Havac25/career-scout-ai.git
   cd career-scout-ai
   ```

2. **Run the setup script:**
   The script will install all dependencies (Ollama, Python uv, system packages), setup the database, and install a background timer.
   ```bash
   chmod +x setup-vm.sh
   ./setup-vm.sh
   ```

## 4. Managing Background Scheduling

The setup script automatically configures the application to run daily at 20:00 (Warsaw time) in the background using `systemd` timers. `Persistent=true` ensures it catches up if the VM is temporarily offline at execution time.

Here are the commands to manage and monitor the background job:

```bash
# Check when the job is scheduled to run next
systemctl --user list-timers career-scout-ai.timer

# View the execution logs in real-time
journalctl --user -u career-scout-ai.service -f

# Trigger a run manually right now
systemctl --user start career-scout-ai.service

# Disable the daily scheduling temporarily
systemctl --user disable --now career-scout-ai.timer
```

---
**Note for AI Assistant:** When initializing this issue, ensure `profile.md` and `config/agents/` are properly populated as they are required for the scoring engine to function.