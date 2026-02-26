from pydantic import BaseSettings


class AppConfig(BaseSettings):
    app_name: str

    class Config:
        env_file = ".env"
