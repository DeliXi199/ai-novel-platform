from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Novel Platform MVP"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"

    postgres_server: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "novel_user"
    postgres_password: str = "novel_password"
    postgres_db: str = "novel_db"
    database_url: str = "postgresql+psycopg2://novel_user:novel_password@127.0.0.1:5432/novel_db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
