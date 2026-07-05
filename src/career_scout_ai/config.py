from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    app_name: str = "Career Scout AI"
    database_path: Path = PROJECT_ROOT / "data" / "career_scout.db"

    # Ollama (local LLM)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout: int = 120

    # Scoring
    agents_dir: Path = PROJECT_ROOT / "config" / "agents"
    profile_path: Path = PROJECT_ROOT / "config" / "profile.md"

    model_config = {"env_file": ".env"}
