from __future__ import annotations

from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.chapter_repair_pipeline import classify_chapter_repair
from app.services.openai_story_engine import generate_chapter_from_plan
from app.services.prompt_templates import chapter_body_draft_user_prompt, chapter_closing_user_prompt


def test_body_prompt_reserves_closing_stage() -> None:
    prompt = chapter_body_draft_user_prompt(
        novel_context={"project_card": {"genre_positioning": "修仙", "protagonist": {"name": "方尘"}}},
        chapter_plan={"title": "废料区试手", "hook_style": "信息反转", "proactive_move": "主动注入灵力试镜"},
        last_chapter={"continuity_bridge": {"opening_anchor": "他把铜镜重新翻到掌心。"}},
        recent_summaries=[],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
        body_target_visible_chars_min=1300,
        body_target_visible_chars_max=2100,
    )
    assert "章尾收束会在下一阶段单独生成" in prompt
    assert "不要把最后的章末落点一次写满" in prompt



def test_closing_prompt_reuses_generation_method_and_tail_only() -> None:
    prompt = chapter_closing_user_prompt(
        chapter_plan={
            "title": "废料区试手",
            "goal": "验证古镜能否被灵力激活",
            "mid_turn": "镜面连续两次没有反应",
            "discovery": "镜面边缘出现一丝极淡涟漪",
            "payoff_or_pressure": "主角确认古镜并非死物，但激活条件仍不明",
            "ending_hook": "镜背里似乎多出一道极浅纹路",
            "hook_style": "信息反转",
        },
        existing_content=(
            "方尘先用左手食指按住镜面，缓缓注入一丝灵力。\n\n"
            "镜面仍旧毫无反应，只在掌心留下一点冰凉。"
        ),
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
        closing_target_visible_chars_min=180,
        closing_target_visible_chars_max=320,
    )
    assert "【正文主生成方法】" in prompt
    assert "只输出紧接正文主体后面的新增文本" in prompt
    assert "不要回头概括全章" in prompt



def test_generate_chapter_from_plan_uses_body_and_closing_phases(monkeypatch) -> None:
    import app.services.openai_story_engine as ose

    calls: list[dict[str, object]] = []

    def fake_call_text_response(*, stage: str, system_prompt: str, user_prompt: str, max_output_tokens: int | None = None, timeout_seconds: int | None = None) -> str:
        calls.append({
            "stage": stage,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "max_output_tokens": max_output_tokens,
            "timeout_seconds": timeout_seconds,
        })
        if stage == "chapter_generation_body":
            return "方尘把铜镜翻到掌心，先换了三种注入灵力的方式。\n\n第二次试到一半时，镜背忽然浮出一道极淡的凉意。"
        if stage == "chapter_generation_closing":
            return "\n\n他没有继续加力，只把镜子慢慢收回袖中。刚才那道凉意已经够他确认一件事——这面古镜并不是死物，只是开门的方法还没摸对。袖底贴着镜背的那一面，似乎又多出了一道浅得几乎看不见的纹路。"
        raise AssertionError(stage)

    monkeypatch.setattr(ose, "call_text_response", fake_call_text_response)
    monkeypatch.setattr(ose, "current_chapter_max_output_tokens", lambda *args, **kwargs: 1200)
    monkeypatch.setattr(ose.settings, "chapter_dynamic_continuation_enabled", False, raising=False)

    draft = generate_chapter_from_plan(
        novel_context={"project_card": {"genre_positioning": "修仙", "protagonist": {"name": "方尘"}}},
        chapter_plan={
            "chapter_no": 3,
            "title": "废料区试手",
            "goal": "验证古镜能否被灵力激活",
            "payoff_or_pressure": "主角确认古镜并非死物，但激活条件仍不明",
            "ending_hook": "镜背里似乎多出一道极浅纹路",
            "hook_style": "信息反转",
        },
        last_chapter={"continuity_bridge": {"opening_anchor": "方尘回到废料区角落。"}},
        recent_summaries=[],
        active_interventions=[],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
        request_timeout_seconds=36,
    )

    assert [item["stage"] for item in calls] == ["chapter_generation_body", "chapter_generation_closing"]
    assert "这面古镜并不是死物" in draft.content
    assert draft.title == "废料区试手"



def test_classify_too_messy_after_tail_fix_escalates_tail_strategy() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_TOO_MESSY,
        message="套话过密",
        stage="chapter_quality",
        details={"style_hits": {"若有若无": 4}},
    )
    action = classify_chapter_repair(
        exc,
        attempt_plan={"title": "废料区试手"},
        targets={"target_visible_chars_min": 1600, "target_visible_chars_max": 2600},
        repair_trace=[
            {
                "attempt_no": 1,
                "repair_type": "ending_incomplete",
                "strategy_id": "ai_append_inline_tail",
                "status": "rejected",
            }
        ],
        attempt_no=1,
    )
    assert action is not None
    assert action.strategy_id == "ai_rewrite_last_paragraph"
    assert action.execution_mode == "replace_last_paragraph"


def test_continuation_prompt_includes_state_style_and_continuity() -> None:
    from app.services.prompt_templates import chapter_body_continue_user_prompt

    prompt = chapter_body_continue_user_prompt(
        chapter_plan={
            "title": "废料区试手",
            "goal": "验证古镜能否被灵力激活",
            "payoff_or_pressure": "确认古镜并非死物，但可能已被人注意到",
            "ending_hook": "废铁堆后传来脚步声",
            "hook_style": "危险逼近",
        },
        existing_content="方尘把镜子按在掌心，缓缓注入灵力。\n\n镜面先是毫无反应，随后才浮出极浅一线灰纹。",
        last_chapter={"continuity_bridge": {"opening_anchor": "他没有立刻离开废料区。", "unresolved_action_chain": "镜子还在手里，试验还没停。"}},
        recent_summaries=[{"event_summary": "上一章确认古镜并非凡物。"}],
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
        continuation_target_visible_chars_min=280,
        continuation_target_visible_chars_max=520,
        continuation_round=1,
        max_segments=3,
    )
    assert "【正文当前状态摘要】" in prompt
    assert "【文风继承摘要】" in prompt
    assert "【轻量连续性锚点】" in prompt
    assert "【正文开头风格锚点】" in prompt


def test_closing_prompt_includes_state_style_and_continuity() -> None:
    from app.services.prompt_templates import chapter_closing_user_prompt

    prompt = chapter_closing_user_prompt(
        chapter_plan={
            "title": "废料区试手",
            "goal": "验证古镜能否被灵力激活",
            "payoff_or_pressure": "确认古镜并非死物，但激活条件仍不明",
            "ending_hook": "镜背里似乎多出一道极浅纹路",
            "hook_style": "信息反转",
        },
        existing_content="方尘把镜子翻到掌心，再次压入一线灵力。\n\n这一次，镜背内侧终于浮出一点极浅的凉意。",
        last_chapter={"continuity_bridge": {"opening_anchor": "他回到废料区角落。"}},
        recent_summaries=[{"event_summary": "上一章已经试出古镜会吃灵力。"}],
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
        closing_target_visible_chars_min=180,
        closing_target_visible_chars_max=320,
    )
    assert "【正文当前状态摘要】" in prompt
    assert "【文风继承摘要】" in prompt
    assert "【轻量连续性锚点】" in prompt
    assert "【正文开头风格锚点】" in prompt


def test_body_prompt_is_lightweight_and_defers_heavy_inheritance_context() -> None:
    prompt = chapter_body_draft_user_prompt(
        novel_context={
            "project_card": {"genre_positioning": "修仙", "protagonist": {"name": "方尘"}},
            "story_memory": {
                "project_card": {"genre_positioning": "修仙"},
                "current_volume_card": {"name": "旧城卷"},
                "execution_brief": {"focus": "先验证古镜，再处理尾部风险"},
                "hard_fact_guard": {"境界": "炼气一层"},
                "recent_retrospectives": [{"issue": "结尾发虚"}],
            },
        },
        chapter_plan={
            "title": "废料区试手",
            "goal": "验证古镜能否被灵力激活",
            "proactive_move": "主动注入灵力试镜",
            "hook_style": "危险逼近",
        },
        last_chapter={"continuity_bridge": {"opening_anchor": "他重新翻出那面古镜。"}},
        recent_summaries=[{"event_summary": "上一章确认古镜会吃灵力。"}],
        active_interventions=[{"instruction": "保留一点危险感"}],
        target_words=2200,
        target_visible_chars_min=1600,
        target_visible_chars_max=2600,
        body_target_visible_chars_min=1300,
        body_target_visible_chars_max=2100,
    )
    assert "【正文主体轻量上下文】" in prompt
    assert "【文风继承摘要】" not in prompt
    assert "【正文当前状态摘要】" not in prompt
    assert "【轻量连续性锚点】" not in prompt
    assert "章尾收束会在下一阶段单独生成" in prompt


def test_phase_timeouts_bias_budget_toward_initial_body(monkeypatch) -> None:
    import app.services.openai_story_engine as ose

    monkeypatch.setattr(ose.settings, "chapter_closing_timeout_seconds", 28, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_timeout_ratio", 0.76, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_min_timeout_seconds", 84, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_continuation_min_timeout_seconds", 36, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_continuation_preferred_timeout_seconds", 48, raising=False)

    body_timeout, continuation_timeout, closing_timeout = ose._chapter_phase_timeouts(100, max_segments=3)

    assert body_timeout is not None and continuation_timeout is not None and closing_timeout is not None
    assert body_timeout > continuation_timeout
    assert body_timeout >= 60
    assert continuation_timeout >= 36
    assert closing_timeout >= 20


def test_safe_continuation_timeout_returns_none_when_budget_too_low(monkeypatch) -> None:
    import app.services.openai_story_engine as ose

    monkeypatch.setattr(ose.settings, "chapter_continuation_min_timeout_seconds", 36, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_continuation_timeout_share", 0.62, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_continuation_closing_reserve_seconds", 28, raising=False)

    started_at = 100.0
    monkeypatch.setattr(ose.time, "monotonic", lambda: 130.0)

    timeout = ose._resolve_safe_continuation_timeout(
        60,
        started_at,
        preferred_continuation_timeout=48,
        preferred_closing_timeout=28,
    )

    assert timeout is None


def test_generate_chapter_falls_back_to_closing_after_continuation_timeout(monkeypatch) -> None:
    import app.services.openai_story_engine as ose

    stages: list[str] = []

    def fake_call_text_response(*, stage: str, system_prompt: str, user_prompt: str, max_output_tokens: int | None = None, timeout_seconds: int | None = None) -> str:
        stages.append(stage)
        if stage == "chapter_generation_body":
            return "方尘把镜子按在掌心，先后换了两种注入法，镜面却只在边角浮出一点模糊灰意。"
        if stage == "chapter_generation_continue":
            raise GenerationError(
                code=ErrorCodes.API_TIMEOUT,
                message="timeout",
                stage="chapter_generation_continue",
                details={"timeout_seconds": timeout_seconds},
            )
        if stage == "chapter_generation_closing":
            return "他没有继续加力，只把铜镜收入袖中，决定先离开废料区再慢慢拆这道反应。"
        raise AssertionError(stage)

    monkeypatch.setattr(ose, "call_text_response", fake_call_text_response)
    monkeypatch.setattr(ose.settings, "chapter_dynamic_continuation_enabled", True, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_max_segments", 2, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_continuation_min_growth_chars", 20, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_total_visible_chars_cap", 900, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_continuation_target_min_visible_chars", 120, raising=False)

    draft = generate_chapter_from_plan(
        novel_context={},
        chapter_plan={
            "chapter_no": 3,
            "title": "废料区试手",
            "goal": "验证镜子的反应",
            "progress_kind": "信息推进",
            "payoff_or_pressure": "确认镜子并非死物，同时留下被人注意到的风险",
            "ending_hook": "有人在暗处盯上了方尘",
            "hook_style": "危险逼近",
        },
        last_chapter={},
        recent_summaries=[],
        active_interventions=[],
        target_words=140,
        target_visible_chars_min=220,
        target_visible_chars_max=320,
        request_timeout_seconds=120,
    )

    assert stages == ["chapter_generation_body", "chapter_generation_continue", "chapter_generation_closing"]
    assert draft.body_stop_reason == "continuation_timeout_fallback_to_closing"
    assert "决定先离开废料区再慢慢拆这道反应" in draft.content



def test_classify_too_messy_generates_retry_plan_with_specific_feedback() -> None:
    exc = GenerationError(
        code=ErrorCodes.CHAPTER_TOO_MESSY,
        message="写法重复偏重",
        stage="chapter_quality",
        details={
            "messy_metrics": {
                "repeated_sentence_ratio": 0.4,
                "repeated_openings": {"方尘没有立": 3},
                "style_clue_hits": {"微弱": 3},
            },
            "ai_style_review": {
                "verdict": "messy",
                "problem_types": ["句式重复", "开头写法单一"],
                "evidence": ["前几句连续用同一种起手判断句"],
                "repair_brief": "把判断句拆开，换成更具体的动作推进。",
                "must_change": ["不要连着三句都用‘没有立刻’起手"],
                "avoid": ["先看着某物再下判断"],
            },
        },
    )
    action = classify_chapter_repair(
        exc,
        attempt_plan={"title": "废料区试手"},
        targets={"target_visible_chars_min": 1600, "target_visible_chars_max": 2600},
        repair_trace=[],
        attempt_no=1,
    )
    assert action is not None
    assert action.strategy_id == "regenerate_style_rewritten_draft"
    assert action.execution_mode == "insert_retry_attempt"
    assert action.retry_plan is not None
    assert action.retry_plan.get("retry_focus") == "style_cleanup"
    assert "句式重复" in str(action.retry_plan.get("writing_note") or "")
