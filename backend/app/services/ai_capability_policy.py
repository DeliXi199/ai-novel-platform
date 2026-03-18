from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.services.llm_runtime import get_llm_runtime_config


AI_REQUIRED_STAGE_GROUPS: dict[str, list[str]] = {
    "bootstrap_and_creation": [
        "story_engine_diagnosis",
        "story_strategy_generation",
        "global_outline_generation",
        "arc_outline_generation",
        "bootstrap_character_templates",
    ],
    "planning_and_selection": [
        "importance_eval",
        "importance_eval_detail",
        "chapter_prepare_shortlist",
        "chapter_prepare_selection_schedule",
        "chapter_prepare_selection_cards",
        "chapter_prepare_selection_payoff",
        "chapter_prepare_selection_scene",
        "chapter_prepare_selection_prompt",
        "chapter_prepare_selection_merge",
        "local_constraint_reasoning",
    ],
    "drafting_and_repair": [
        "chapter_generation",
        "chapter_generation_continue",
        "chapter_extension",
        "chapter_closing",
        "chapter_repair",
        "chapter_summary_title_package",
        "chapter_title_refinement",
    ],
    "review_and_guardrails": [
        "chapter_quality_ai_review",
        "hard_fact_guard_review",
        "payoff_ai_selection",
        "payoff_ai_delivery_review",
        "stage_character_review",
    ],
}

LOCAL_ONLY_ALLOWED_OPERATIONS = [
    "压缩索引与上下文裁剪",
    "结构校验与 JSON/schema 校验",
    "运行时快照与诊断汇总",
    "数据库持久化与工作台归档",
    "TTS 文件组织与导出打包",
]


def build_llm_policy_report() -> dict[str, Any]:
    feature_switches = {
        "importance_eval_ai_enabled": bool(getattr(settings, "importance_eval_ai_enabled", True)),
        "local_constraint_reasoning_ai_enabled": bool(getattr(settings, "local_constraint_reasoning_ai_enabled", True)),
        "chapter_preparation_parallel_selection_enabled": bool(getattr(settings, "chapter_preparation_parallel_selection_enabled", True)),
        "chapter_messy_ai_review_enabled": bool(getattr(settings, "chapter_messy_ai_review_enabled", True)),
        "chapter_summary_title_package_enabled": bool(getattr(settings, "chapter_summary_title_package_enabled", True)),
        "chapter_title_refinement_enabled": bool(getattr(settings, "chapter_title_refinement_enabled", True)),
        "payoff_ai_selection_enabled": bool(getattr(settings, "payoff_ai_selection_enabled", True)),
        "payoff_ai_delivery_review_enabled": bool(getattr(settings, "payoff_ai_delivery_review_enabled", True)),
        "hard_fact_llm_review_enabled": bool(getattr(settings, "hard_fact_llm_review_enabled", True)),
    }
    return {
        "policy_version": "2026-03-17",
        "summary": {
            "core_rule": "创造性规划、主筛选、正文生成、AI 复核与标题精修都必须依赖 AI；本地只允许做压缩、校验、持久化与展示。",
            "forbid_silent_fallback": True,
        },
        "llm_runtime": {
            "default": get_llm_runtime_config(None),
            "bootstrap": get_llm_runtime_config("global_outline_generation"),
        },
        "feature_switches": feature_switches,
        "ai_required_stage_groups": AI_REQUIRED_STAGE_GROUPS,
        "local_only_allowed_operations": LOCAL_ONLY_ALLOWED_OPERATIONS,
    }
