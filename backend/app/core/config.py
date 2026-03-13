from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = BACKEND_DIR / ".env"


class Settings(BaseSettings):
    app_name: str = "AI Novel Platform MVP"
    app_env: str = "development"
    app_debug: bool = True
    api_v1_prefix: str = "/api/v1"
    cors_allow_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    postgres_server: str = "127.0.0.1"
    postgres_port: int = 5432
    postgres_user: str = "novel_user"
    postgres_password: str = "novel_password"
    postgres_db: str = "novel_db"
    database_url: str = "postgresql+psycopg2://novel_user:novel_password@127.0.0.1:5432/novel_db"

    llm_provider: str = "deepseek"
    bootstrap_llm_provider: str | None = None
    bootstrap_model: str | None = None
    bootstrap_timeout_seconds: int | None = None
    bootstrap_prefer_non_reasoning: bool = True

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
    chapter_draft_max_attempts: int = 2
    chapter_too_short_retry_attempts: int = 1
    chapter_too_short_retry_delay_ms: int = 1200
    chapter_tail_fix_attempts: int = 1
    chapter_extension_min_llm_timeout_seconds: int = 20
    chapter_extension_soft_min_timeout_seconds: int = 12
    chapter_tail_fix_delay_ms: int = 600
    chapter_weak_ending_retry_attempts: int = 1
    chapter_weak_ending_retry_delay_ms: int = 900
    chapter_generation_wall_clock_limit_seconds: int = 420
    chapter_total_llm_attempt_cap: int = 2
    chapter_runtime_min_llm_timeout_seconds: int = 25
    chapter_runtime_min_remaining_for_retry_seconds: int = 45
    chapter_runtime_summary_reserve_seconds: int = 12
    chapter_retry_compact_prompt_after_attempt: int = 2
    chapter_summary_force_heuristic_below_seconds: int = 30
    chapter_summary_max_output_tokens: int = 320
    chapter_summary_mode: str = "auto"
    hard_fact_llm_review_enabled: bool = True
    hard_fact_llm_timeout_seconds: int = 25
    hard_fact_llm_max_output_tokens: int = 700
    hard_fact_llm_max_conflicts_per_review: int = 4
    hard_fact_llm_context_chars: int = 2200
    llm_call_min_interval_ms: int = 1200
    llm_trace_limit: int = 16
    llm_api_max_retries: int = 0
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
    planning_window_size: int = 7
    planning_strict_mode: bool = True
    arc_outline_chunk_size: int = 2
    json_repair_attempts: int = 1
    json_invalid_regeneration_attempts: int = 1
    json_repair_max_output_tokens: int = 2200

    # TTS
    tts_enabled: bool = True
    media_root: str | None = None
    tts_default_voice: str = "zh-CN-YunxiNeural"
    tts_default_rate: str = "+0%"
    tts_default_volume: str = "+0%"
    tts_default_pitch: str = "+0Hz"

    @field_validator(
        "llm_provider",
        "bootstrap_llm_provider",
        "bootstrap_model",
        "openai_api_key",
        "openai_base_url",
        "openai_model",
        "deepseek_api_key",
        "deepseek_base_url",
        "deepseek_model",
        "groq_api_key",
        "groq_base_url",
        "groq_model",
        mode="before",
    )
    @classmethod
    def _strip_text_like_values(cls, value: str | None):
        if value is None:
            return None
        if isinstance(value, str):
            cleaned = value.strip().strip('"').strip("'").strip()
            return cleaned or None
        return value

    model_config = SettingsConfigDict(
        env_file=str(DEFAULT_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_allow_origin_list(self) -> list[str]:
        if not self.cors_allow_origins:
            return ["*"]
        parts = [part.strip() for part in self.cors_allow_origins.split(",")]
        return [part for part in parts if part] or ["*"]

    @property
    def is_production(self) -> bool:
        return str(self.app_env or "").lower() == "production"

    @property
    def media_root_path(self) -> Path:
        if self.media_root:
            return Path(self.media_root).expanduser().resolve()
        return BACKEND_DIR / "data" / "media"

    @property
    def expose_diagnostic_runtime(self) -> bool:
        return bool(self.app_debug) and not self.is_production


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


class _SettingsProxy:
    def __getattr__(self, item: str) -> Any:
        return getattr(get_settings(), item)

    def __repr__(self) -> str:
        return repr(get_settings())


settings = _SettingsProxy()
