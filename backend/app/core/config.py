from __future__ import annotations

from pydantic import field_validator, model_validator
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

    llm_provider: str = "openai"

    # OpenAI
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-5.4"
    openai_reasoning_effort: str = "medium"
    openai_timeout_seconds: int = 120
    openai_max_output_tokens: int = 4000
    openai_chapter_max_output_tokens: int = 1500

    # DeepSeek
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = 120
    deepseek_max_output_tokens: int = 4000
    deepseek_chapter_max_output_tokens: int = 2200

    # Groq
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: int = 120
    groq_max_output_tokens: int = 4000
    groq_chapter_max_output_tokens: int = 1800

    chapter_target_words: int = 1500
    chapter_hard_min_visible_chars: int = 900
    chapter_min_visible_chars: int = 1200
    chapter_similarity_threshold: float = 0.76
    chapter_context_mode: str = "light"
    chapter_recent_summary_limit: int = 2
    chapter_last_excerpt_chars: int = 500
    chapter_live_hook_limit: int = 6
    chapter_recent_summary_chars: int = 120
    chapter_prompt_max_chars: int = 7600
    chapter_draft_max_attempts: int = 4
    chapter_too_short_retry_attempts: int = 3
    chapter_too_short_retry_delay_ms: int = 1800
    chapter_tail_fix_attempts: int = 2
    chapter_tail_fix_delay_ms: int = 900
    chapter_summary_max_output_tokens: int = 320
    chapter_summary_mode: str = "auto"
    llm_call_min_interval_ms: int = 1200
    llm_trace_limit: int = 16
    return_draft_payload_in_meta: bool = False

    # Dynamic length targets
    chapter_probe_target_min_visible_chars: int = 1000
    chapter_probe_target_max_visible_chars: int = 1500
    chapter_progress_target_min_visible_chars: int = 1400
    chapter_progress_target_max_visible_chars: int = 2200
    chapter_turning_point_target_min_visible_chars: int = 1800
    chapter_turning_point_target_max_visible_chars: int = 2600

    # Layered-outline flow
    bootstrap_initial_chapters: int = 0
    global_outline_acts: int = 4
    arc_outline_size: int = 5
    arc_prefetch_threshold: int = 0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("llm_provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        provider = (value or "").strip().lower()
        if provider not in {"openai", "deepseek", "groq"}:
            raise ValueError("LLM_PROVIDER must be one of: openai, deepseek, groq")
        return provider

    @field_validator("chapter_context_mode")
    @classmethod
    def _normalize_context_mode(cls, value: str) -> str:
        mode = (value or "").strip().lower()
        if mode not in {"light", "full"}:
            raise ValueError("CHAPTER_CONTEXT_MODE must be 'light' or 'full'")
        return mode

    @field_validator("chapter_summary_mode")
    @classmethod
    def _normalize_summary_mode(cls, value: str) -> str:
        mode = (value or "").strip().lower()
        if mode not in {"auto", "llm", "heuristic"}:
            raise ValueError("CHAPTER_SUMMARY_MODE must be 'auto', 'llm', or 'heuristic'")
        return mode

    @field_validator(
        "openai_reasoning_effort",
        mode="before",
    )
    @classmethod
    def _normalize_reasoning_effort(cls, value: str) -> str:
        effort = (value or "").strip().lower()
        if effort not in {"minimal", "low", "medium", "high"}:
            raise ValueError("OPENAI_REASONING_EFFORT must be minimal, low, medium, or high")
        return effort

    @model_validator(mode="after")
    def _validate_numeric_ranges(self) -> "Settings":
        positive_fields = [
            "openai_timeout_seconds",
            "deepseek_timeout_seconds",
            "groq_timeout_seconds",
            "openai_max_output_tokens",
            "deepseek_max_output_tokens",
            "groq_max_output_tokens",
            "openai_chapter_max_output_tokens",
            "deepseek_chapter_max_output_tokens",
            "groq_chapter_max_output_tokens",
            "chapter_target_words",
            "chapter_hard_min_visible_chars",
            "chapter_min_visible_chars",
            "chapter_recent_summary_limit",
            "chapter_last_excerpt_chars",
            "chapter_live_hook_limit",
            "chapter_recent_summary_chars",
            "chapter_prompt_max_chars",
            "chapter_draft_max_attempts",
            "chapter_too_short_retry_attempts",
            "chapter_tail_fix_attempts",
            "chapter_summary_max_output_tokens",
            "llm_call_min_interval_ms",
            "llm_trace_limit",
            "chapter_probe_target_min_visible_chars",
            "chapter_probe_target_max_visible_chars",
            "chapter_progress_target_min_visible_chars",
            "chapter_progress_target_max_visible_chars",
            "chapter_turning_point_target_min_visible_chars",
            "chapter_turning_point_target_max_visible_chars",
            "global_outline_acts",
            "arc_outline_size",
        ]
        for name in positive_fields:
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than 0")

        if not 0 <= self.chapter_similarity_threshold <= 1:
            raise ValueError("chapter_similarity_threshold must be between 0 and 1")

        if self.chapter_hard_min_visible_chars > self.chapter_min_visible_chars:
            raise ValueError("chapter_hard_min_visible_chars cannot exceed chapter_min_visible_chars")

        for prefix in ("chapter_probe", "chapter_progress", "chapter_turning_point"):
            low = getattr(self, f"{prefix}_target_min_visible_chars")
            high = getattr(self, f"{prefix}_target_max_visible_chars")
            if low > high:
                raise ValueError(f"{prefix}_target_min_visible_chars cannot exceed {prefix}_target_max_visible_chars")

        return self


settings = Settings()
