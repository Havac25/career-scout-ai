from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class AppConfig(BaseSettings):
    app_name: str = "Career Scout AI"
    database_path: Path = PROJECT_ROOT / "data" / "career_scout.db"

    model_config = {"env_file": ".env"}
