# Local Run Guide (Linux PC)

This guide provides instructions on how to set up and run the `career-scout-ai` application locally on your Linux PC.

## 1. Automated Setup

To make setup as easy as possible, an automated setup script is included in the repository.

1. **Get the code:**
   Clone the repository from your Git host (e.g., GitHub, GitLab) to your Linux PC:
   ```bash
   git clone git@github.com:Havac25/career-scout-ai.git
   cd career-scout-ai
   ```

2. **Run the setup script:**
   This script will automatically install system dependencies, `uv`, `Ollama`, download the AI model, set up the Python virtual environment, initialize the database, create the `.env` file, and set up the background scheduling.
   ```bash
   chmod +x setup-local-linux.sh
   ./setup-local-linux.sh
   ```
   *(Note: The script will prompt for your `sudo` password to install system packages and start the Ollama service).*

3. **Configure lid switch behavior (one-time manual step):**
   Restarting `systemd-logind` terminates the active session, so this step must be run manually after the setup script completes. It prevents the laptop from suspending when the lid is closed on AC power:
   ```bash
   sudo mkdir -p /etc/systemd/logind.conf.d
   echo "[Login]
   HandleLidSwitchExternalPower=ignore" | sudo tee /etc/systemd/logind.conf.d/career-scout.conf
   sudo systemctl restart systemd-logind
   ```
   *(Note: Your SSH or terminal session will be terminated by the last command. This is expected — reconnect and the setting will be active.)*

## 2. Managing Background Scheduling

The setup script automatically configures the application to run daily at 02:00 (Warsaw time) in the background using `systemd` timers. The job will also run correctly if your laptop is closed, provided it is plugged into AC power. If the job was missed due to the laptop being off or sleeping on battery, `Persistent=true` ensures it will catch up immediately upon next wake.

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

## 3. Running the Application Manually

If you prefer not to use the background scheduler, or just want to run it directly:

```bash
# 1. Navigate to the project directory
cd /path/to/career-scout-ai

# 2. Activate the virtual environment
source .venv/bin/activate

# 3. Run the main script
uv run career-scout-ai
```

*(Note: Ensure that the `ollama` service is running (`systemctl status ollama`) before starting the application, otherwise the scoring phase will fail).*
