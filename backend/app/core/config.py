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

    llm_provider: str = "mock"

    # OpenAI
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-5.4"
    openai_reasoning_effort: str = "medium"
    openai_timeout_seconds: int = 120
    openai_max_output_tokens: int = 4000

    # Groq
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: int = 120
    groq_max_output_tokens: int = 4000

    chapter_target_words: int = 1800
    chapter_recent_summary_limit: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
