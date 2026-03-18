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
    auto_init_db_on_startup: bool = True

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

    # OpenAI
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-5.4"
    openai_reasoning_effort: str = "medium"
    openai_timeout_seconds: int = 180
    openai_max_output_tokens: int = 4000
    openai_chapter_max_output_tokens: int = 1500

    # DeepSeek
    deepseek_api_key: str | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    deepseek_timeout_seconds: int = 180
    deepseek_max_output_tokens: int = 4000
    deepseek_chapter_max_output_tokens: int = 2200

    # Groq
    groq_api_key: str | None = None
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "openai/gpt-oss-20b"
    groq_timeout_seconds: int = 180
    groq_max_output_tokens: int = 4000
    groq_chapter_max_output_tokens: int = 1800

    chapter_target_words: int = 1500
    chapter_hard_min_visible_chars: int = 900
    chapter_min_visible_chars: int = 1200
    chapter_similarity_threshold: float = 0.76
    chapter_context_mode: str = "light"
    chapter_recent_summary_limit: int = 3
    chapter_last_excerpt_chars: int = 500
    chapter_live_hook_limit: int = 6
    chapter_recent_summary_chars: int = 120
    chapter_prompt_max_chars: int = 7600
    chapter_draft_max_attempts: int = 2
    chapter_too_short_retry_attempts: int = 1
    chapter_too_short_retry_delay_ms: int = 1200
    chapter_tail_fix_attempts: int = 2
    chapter_closing_enabled: bool = True
    chapter_dynamic_continuation_enabled: bool = True
    chapter_body_generation_ratio: float = 0.82
    chapter_body_max_output_tokens_ratio: float = 0.78
    chapter_body_timeout_ratio: float = 0.76
    chapter_body_min_timeout_seconds: int = 84
    chapter_continuation_min_timeout_seconds: int = 36
    chapter_continuation_preferred_timeout_seconds: int = 48
    chapter_continuation_timeout_share: float = 0.62
    chapter_continuation_closing_reserve_seconds: int = 28
    chapter_body_max_segments: int = 2
    chapter_body_continuation_target_min_visible_chars: int = 360
    chapter_body_continuation_target_max_visible_chars: int = 900
    chapter_body_continuation_max_output_tokens: int = 720
    chapter_body_continuation_min_growth_chars: int = 180
    chapter_body_force_closing_margin_chars: int = 220
    chapter_body_total_visible_chars_cap: int = 5200
    chapter_closing_target_min_visible_chars: int = 180
    chapter_closing_target_max_visible_chars: int = 360
    chapter_closing_timeout_seconds: int = 28
    chapter_closing_max_output_tokens: int = 520
    chapter_extension_min_llm_timeout_seconds: int = 24
    chapter_extension_soft_min_timeout_seconds: int = 14
    chapter_tail_fix_delay_ms: int = 600
    chapter_weak_ending_retry_attempts: int = 1
    chapter_scene_continuity_check_enabled: bool = True
    chapter_scene_continuity_retry_attempts: int = 1
    chapter_scene_continuity_retry_delay_ms: int = 800
    chapter_too_messy_retry_attempts: int = 1
    chapter_too_messy_retry_delay_ms: int = 900
    chapter_messy_ai_review_enabled: bool = True
    chapter_messy_ai_timeout_seconds: int = 18
    chapter_messy_ai_max_output_tokens: int = 700
    chapter_weak_ending_retry_delay_ms: int = 900
    chapter_generation_wall_clock_limit_seconds: int = 600
    chapter_total_llm_attempt_cap: int = 3
    chapter_runtime_min_llm_timeout_seconds: int = 32
    chapter_runtime_min_remaining_for_retry_seconds: int = 45
    chapter_runtime_summary_reserve_seconds: int = 12
    chapter_retry_compact_prompt_after_attempt: int = 2
    chapter_summary_force_heuristic_below_seconds: int = 30
    chapter_summary_max_output_tokens: int = 320
    chapter_summary_mode: str = "llm"
    chapter_summary_title_package_enabled: bool = True
    chapter_summary_title_package_timeout_seconds: int = 24
    chapter_summary_title_package_max_output_tokens: int = 1200
    stage_character_review_timeout_seconds: int = 60
    stage_character_review_max_output_tokens: int = 520
    stage_character_review_retry_attempts: int = 1
    stage_character_review_retry_backoff_ms: int = 1200
    stage_character_review_retry_timeout_increment_seconds: int = 0
    chapter_title_refinement_enabled: bool = True
    chapter_title_recent_window: int = 20
    chapter_title_similarity_threshold: float = 0.72
    chapter_title_refinement_candidate_count: int = 5
    chapter_title_timeout_seconds: int = 18
    chapter_title_max_output_tokens: int = 900
    payoff_ai_selection_enabled: bool = True
    payoff_ai_selection_timeout_seconds: int = 12
    payoff_ai_selection_max_output_tokens: int = 420
    payoff_ai_selection_score_gap_threshold: float = 4.0
    payoff_ai_delivery_review_enabled: bool = True
    payoff_ai_delivery_review_timeout_seconds: int = 14
    payoff_ai_delivery_review_max_output_tokens: int = 520
    hard_fact_llm_review_enabled: bool = True
    hard_fact_llm_timeout_seconds: int = 25
    hard_fact_llm_max_output_tokens: int = 700
    hard_fact_llm_max_conflicts_per_review: int = 4
    hard_fact_llm_context_chars: int = 2200
    llm_call_min_interval_ms: int = 1200
    llm_trace_limit: int = 16
    llm_api_max_retries: int = 1
    return_draft_payload_in_meta: bool = False

    importance_eval_ai_enabled: bool = True
    importance_eval_timeout_seconds: int = 20
    importance_eval_max_output_tokens: int = 360
    importance_eval_summary_card_limit: int = 16
    importance_eval_summary_budget_chars: int = 3000
    importance_eval_force_keep_limit: int = 4
    importance_eval_detail_review_limit: int = 3
    importance_eval_detail_timeout_seconds: int = 26
    importance_eval_detail_max_output_tokens: int = 480
    importance_eval_planning_ai_interval_chapters: int = 2
    importance_eval_post_chapter_ai_interval_chapters: int = 3
    importance_eval_bootstrap_ai_enabled: bool = True
    importance_handoff_enabled: bool = True
    importance_handoff_decay_chapters: int = 2
    importance_handoff_min_confidence: float = 0.55
    importance_handoff_must_carry_bonus: float = 20.0
    importance_handoff_warm_bonus: float = 10.0
    importance_handoff_cooldown_penalty: float = 8.0
    importance_handoff_defer_penalty: float = 5.0

    resource_capability_plan_cache_enabled: bool = True
    resource_capability_plan_force_refresh_interval_chapters: int = 4
    resource_capability_plan_recent_trigger_window: int = 1
    importance_eval_shortlist_retry_attempts: int = 2
    importance_eval_shortlist_retry_backoff_ms: int = 500
    importance_eval_detail_retry_attempts: int = 2
    importance_eval_detail_retry_backoff_ms: int = 500
    importance_eval_summary_refresh_interval_chapters: int = 3
    importance_eval_exploration_slots: int = 1
    importance_eval_activation_slots: int = 1
    importance_eval_mainline_soft_cap: int = 4
    importance_eval_continuous_presence_penalty: float = 8.0

    local_constraint_reasoning_ai_enabled: bool = True
    local_constraint_reasoning_timeout_seconds: int = 30
    local_constraint_reasoning_max_output_tokens: int = 720
    local_constraint_reasoning_retry_attempts: int = 2
    local_constraint_reasoning_retry_backoff_ms: int = 600
    local_constraint_reasoning_retry_timeout_increment_seconds: int = 10

    chapter_frontload_decision_timeout_seconds: int = 22
    chapter_frontload_decision_retry_attempts: int = 2
    chapter_frontload_decision_retry_backoff_ms: int = 800
    chapter_frontload_decision_retry_timeout_increment_seconds: int = 10
    chapter_frontload_decision_prompt_compact_after_attempt: int = 2
    chapter_frontload_decision_compact_prompt_threshold_chars: int = 7000
    chapter_frontload_decision_max_timeout_seconds: int = 42
    chapter_preparation_parallel_selection_enabled: bool = True
    chapter_preparation_parallel_max_workers: int = 4
    chapter_preparation_merge_timeout_seconds: int = 24
    chapter_preparation_merge_max_timeout_seconds: int = 46
    chapter_preparation_merge_max_output_tokens: int = 720

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

    async_task_max_workers: int = 2
    async_task_recover_orphaned_on_startup: bool = True

    story_workspace_archive_enabled: bool = True
    story_workspace_archive_root: str | None = None
    story_workspace_archive_pretty_json: bool = True
    story_workspace_archive_include_story_bible: bool = False
    story_workspace_archive_keep_files_per_novel: int = 240

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
    def story_workspace_archive_root_path(self) -> Path:
        if self.story_workspace_archive_root:
            return Path(self.story_workspace_archive_root).expanduser().resolve()
        return BACKEND_DIR / "data" / "story_workspace_snapshots"

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
