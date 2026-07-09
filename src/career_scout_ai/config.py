from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    app_name: str = "Career Scout AI"
    database_path: Path = PROJECT_ROOT / "data" / "career_scout.db"

    # Web server
    web_port: int = 8080
    web_host: str = "127.0.0.1"

    # Ollama (local LLM — archived, kept for future use)
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout: int = 120

    # OpenRouter (cloud LLM)
    openrouter_api_key: str = ""
    openrouter_model: str = "google/gemini-2.5-flash"
    openrouter_timeout: int = 60

    # Scoring
    agents_dir: Path = PROJECT_ROOT / "config" / "agents"
    profile_path: Path = PROJECT_ROOT / "config" / "profile.md"

    model_config = {"env_file": ".env"}
