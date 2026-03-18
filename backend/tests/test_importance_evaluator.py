from __future__ import annotations

import pytest

from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.chapter_context_support import build_chapter_plan_packet
from app.services.generation_exceptions import ErrorCodes, GenerationError
from app.services.importance_evaluator import evaluate_story_elements_importance, sort_entities_by_importance
from app.services.novel_bootstrap import build_base_story_bible
from app.services.story_architecture import ensure_story_architecture, update_story_architecture_after_chapter




def _patch_ai_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.services.importance_evaluator._ai_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.importance_evaluator.call_json_response",
        lambda **kwargs: {"evaluations": []},
    )
    monkeypatch.setattr("app.services.constraint_reasoning._ai_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.constraint_reasoning.call_json_response",
        lambda **kwargs: {"result": {}, "reason": "测试桩返回", "confidence": "high", "constraint_checks": ["ok"]},
    )

def _build_novel() -> Novel:
    payload = NovelCreate(
        genre="金手指修仙",
        premise="主角靠古镜与少量灵石在边城求生。",
        protagonist_name="林凡",
        style_preferences={
            "current_resources": ["残缺古镜", "三块灵石", "两张符箓"],
            "factions": ["黑市", "青岚宗"],
            "golden_finger": "残缺古镜",
        },
    )
    novel = Novel(
        id=21,
        title="古镜求生",
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences,
        story_bible=build_base_story_bible(payload),
        current_chapter_no=2,
        status="active",
    )
    novel.story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    domains = (novel.story_bible.get("story_domains") or {})
    domains.setdefault("characters", {})["顾青河"] = {
        "name": "顾青河",
        "entity_type": "character",
        "role_type": "supporting",
        "protagonist_relation_level": "互相试探",
        "current_goal": "摸清古镜的真实来历。",
        "resource_refs": ["残缺古镜"],
        "faction_refs": ["青岚宗"],
        "status": "active",
    }
    domains.setdefault("relations", {})["林凡::顾青河"] = {
        "relation_id": "林凡::顾青河",
        "subject": "林凡",
        "target": "顾青河",
        "relation_type": "与主角关系",
        "current_level": "互相试探",
        "recent_trigger": "顾青河开始追问古镜。",
    }
    return novel


def test_unified_importance_evaluator_assigns_cross_entity_tiers() -> None:
    novel = _build_novel()
    result = evaluate_story_elements_importance(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        scope="planning",
        chapter_no=3,
        plan={"goal": "林凡带着残缺古镜去黑市试探顾青河。", "supporting_character_focus": "顾青河"},
        recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
        touched_entities={
            "character": ["林凡", "顾青河"],
            "resource": ["残缺古镜", "灵石"],
            "relation": ["林凡::顾青河"],
            "faction": ["主角阵营", "青岚宗"],
        },
        allow_ai=False,
    )

    assert result["evaluations"]["character"]["林凡"]["tier"] == "核心级"
    assert result["evaluations"]["resource"]["残缺古镜"]["tier"] in {"核心级", "重要级"}
    assert result["evaluations"]["relation"]["林凡::顾青河"]["score"] >= 60
    assert novel.story_bible["importance_state"]["entity_index"]["resource"]["残缺古镜"]["importance_tier"] in {"核心级", "重要级"}


def test_build_chapter_plan_packet_uses_importance_to_keep_core_resources_visible(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    plan = {
        "chapter_no": 3,
        "title": "夜市试探",
        "goal": "林凡带着残缺古镜进黑市，同时用一张符箓压价。",
        "conflict": "顾青河和黑市都在盯着古镜。",
        "main_scene": "边城黑市",
        "supporting_character_focus": "顾青河",
        "supporting_character_note": "说话冷淡，但会在关键句前停半拍。",
    }
    packet = build_chapter_plan_packet(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        plan=plan,
        serialized_last={"tail_excerpt": "林凡把古镜按回袖口。", "continuity_bridge": {"onstage_characters": ["林凡", "顾青河"]}},
        recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
    )

    assert packet["selected_elements"]["characters"][0] == "林凡"
    assert "残缺古镜" in packet["selected_elements"]["resources"]
    assert packet["importance_snapshot"]["resource"]["残缺古镜"]["score"] >= packet["importance_snapshot"]["resource"].get("灵石", {}).get("score", 0)
    assert packet["resource_capability_plan"]["残缺古镜"]["resource_scope"] == "核心资源"
    assert packet["resource_capability_plan"]["残缺古镜"]["capability_focus"]


def test_post_chapter_update_records_importance_history(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    updated = update_story_architecture_after_chapter(
        story_bible=novel.story_bible,
        novel=novel,
        chapter_no=3,
        chapter_title="夜市试探",
        plan={
            "goal": "林凡借古镜和顾青河继续试探。",
            "supporting_character_focus": "顾青河",
            "planning_packet": {
                "resource_plan": {"灵石": {"planned_action": "consume", "delta_hint": -1, "note": "打点消息用掉一块灵石。"}},
                "selected_elements": {"factions": ["黑市"]},
            },
        },
        summary=type("Summary", (), {
            "event_summary": "林凡用一块灵石打点消息，并确认顾青河没有完全站在黑市那边。",
            "open_hooks": ["顾青河到底想换什么"],
            "closed_hooks": [],
            "character_updates": {"顾青河": {"attitude": "缓和"}},
        })(),
        last_chapter_tail="林凡把古镜按回袖口。",
    )
    history = (updated.get("importance_state") or {}).get("evaluation_history") or []
    assert history
    assert history[-1]["scope"] == "post_chapter"
    assert (updated.get("story_domains") or {}).get("relations", {}).get("林凡::顾青河", {}).get("importance_score", 0) >= 50


def test_importance_evaluator_raises_when_ai_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    novel = _build_novel()
    monkeypatch.setattr("app.services.importance_evaluator._ai_enabled", lambda: False)

    with pytest.raises(GenerationError) as exc_info:
        evaluate_story_elements_importance(
            story_bible=novel.story_bible,
            protagonist_name=novel.protagonist_name,
            scope="planning",
            chapter_no=3,
            plan={"goal": "林凡带着残缺古镜去黑市试探顾青河。"},
            recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。"}],
            touched_entities={"character": ["林凡"]},
            allow_ai=True,
        )

    assert exc_info.value.code == ErrorCodes.AI_REQUIRED_UNAVAILABLE


def test_build_chapter_plan_packet_raises_when_constraint_ai_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    novel = _build_novel()
    monkeypatch.setattr("app.services.importance_evaluator._ai_enabled", lambda: True)
    monkeypatch.setattr("app.services.importance_evaluator.call_json_response", lambda **kwargs: {"evaluations": []})
    monkeypatch.setattr("app.services.constraint_reasoning._ai_enabled", lambda: False)

    with pytest.raises(GenerationError) as exc_info:
        build_chapter_plan_packet(
            story_bible=novel.story_bible,
            protagonist_name=novel.protagonist_name,
            plan={
                "chapter_no": 3,
                "title": "夜市试探",
                "goal": "林凡带着残缺古镜进黑市，同时用一张符箓压价。",
                "conflict": "顾青河和黑市都在盯着古镜。",
                "main_scene": "边城黑市",
                "supporting_character_focus": "顾青河",
            },
            serialized_last={"tail_excerpt": "林凡把古镜按回袖口。", "continuity_bridge": {"onstage_characters": ["林凡", "顾青河"]}},
            recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
        )

    assert exc_info.value.code == ErrorCodes.AI_REQUIRED_UNAVAILABLE


def test_importance_evaluator_persists_hint_summary_and_soft_rank() -> None:
    novel = _build_novel()
    result = evaluate_story_elements_importance(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        scope="planning",
        chapter_no=3,
        plan={"goal": "林凡带着残缺古镜去黑市试探顾青河。", "supporting_character_focus": "顾青河"},
        recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
        touched_entities={
            "character": ["林凡", "顾青河"],
            "resource": ["残缺古镜", "灵石"],
            "relation": ["林凡::顾青河"],
            "faction": ["主角阵营", "青岚宗"],
        },
        allow_ai=False,
    )

    character_snapshot = result["evaluations"]["character"]["顾青河"]
    character_card = novel.story_bible["story_domains"]["characters"]["顾青河"]
    assert character_snapshot["hint_summary"]
    assert character_snapshot["soft_rank_score"] >= character_snapshot["score"]
    assert character_card["importance_hint_summary"]
    assert character_card["importance_soft_rank_score"] >= character_card["importance_score"]


def test_sort_entities_by_importance_prefers_soft_rank_score() -> None:
    container = {
        "甲": {"importance_score": 90, "importance_soft_rank_score": 90},
        "乙": {"importance_score": 78, "importance_soft_rank_score": 109},
        "丙": {"importance_score": 82, "importance_soft_rank_score": 82},
    }

    ordered = sort_entities_by_importance(container, ["甲", "乙", "丙"])
    assert ordered == ["乙", "甲", "丙"]


def test_importance_evaluator_throttles_ai_between_adjacent_planning_chapters(monkeypatch: pytest.MonkeyPatch) -> None:
    novel = _build_novel()
    calls: list[str] = []
    monkeypatch.setattr("app.services.importance_evaluator._ai_enabled", lambda: True)

    def _fake_call_json_response(**kwargs):
        calls.append(str(kwargs.get("stage") or ""))
        return {"evaluations": []}

    monkeypatch.setattr("app.services.importance_evaluator.call_json_response", _fake_call_json_response)

    evaluate_story_elements_importance(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        scope="planning",
        chapter_no=3,
        plan={"goal": "林凡带着残缺古镜去黑市试探顾青河。", "supporting_character_focus": "顾青河"},
        recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
        touched_entities={"character": ["林凡", "顾青河"], "resource": ["残缺古镜", "灵石"]},
        allow_ai=True,
    )
    first_call_count = len(calls)
    assert first_call_count >= 1

    evaluate_story_elements_importance(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        scope="planning",
        chapter_no=4,
        plan={"goal": "林凡继续借黑市消息试探顾青河。", "supporting_character_focus": "顾青河"},
        recent_summaries=[{"chapter_no": 3, "event_summary": "林凡拿到了部分黑市旧账。", "open_hooks": ["顾青河到底站哪边"]}],
        touched_entities={"character": ["林凡", "顾青河"], "resource": ["残缺古镜", "旧账簿"]},
        allow_ai=True,
    )
    assert len(calls) == first_call_count


def test_build_chapter_plan_packet_exposes_importance_lanes(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    plan = {
        "chapter_no": 3,
        "title": "夜市试探",
        "goal": "林凡带着残缺古镜进黑市，同时用一张符箓压价。",
        "conflict": "顾青河和黑市都在盯着古镜。",
        "main_scene": "边城黑市",
        "supporting_character_focus": "顾青河",
        "supporting_character_note": "说话冷淡，但会在关键句前停半拍。",
    }
    packet = build_chapter_plan_packet(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        plan=plan,
        serialized_last={"tail_excerpt": "林凡把古镜按回袖口。", "continuity_bridge": {"onstage_characters": ["林凡", "顾青河"]}},
        recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
    )

    runtime = packet.get("importance_runtime") or {}
    lanes = (runtime.get("selection_lanes") or {}).get("characters") or {}
    assert lanes.get("selected_by_lane")
    assert "importance_mainline_characters" in (packet.get("selected_elements") or {})
    assert packet["selected_elements"]["characters"]



def test_post_chapter_importance_generates_next_chapter_handoff(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    result = evaluate_story_elements_importance(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        scope="post_chapter",
        chapter_no=3,
        plan={"goal": "林凡借古镜和顾青河继续试探。", "supporting_character_focus": "顾青河"},
        recent_summaries=[{"chapter_no": 3, "event_summary": "林凡确认顾青河暂时不会翻脸。", "open_hooks": ["顾青河真正想换什么"]}],
        touched_entities={
            "character": ["林凡", "顾青河"],
            "resource": ["残缺古镜"],
            "relation": ["林凡::顾青河"],
            "faction": ["青岚宗"],
        },
        allow_ai=True,
    )

    handoff = result.get("next_chapter_handoff") or {}
    assert handoff.get("source_chapter") == 3
    assert (handoff.get("must_carry") or {}).get("character")
    assert (novel.story_bible.get("importance_state") or {}).get("next_chapter_handoff", {}).get("source_chapter") == 3



def test_build_chapter_plan_packet_uses_handoff_and_skips_regular_planning_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    captured_allow_ai: list[bool] = []

    from app.services import chapter_context_support as chapter_context_module
    from app.services.importance_evaluator import evaluate_story_elements_importance as original_importance_eval

    def _wrapped_importance_eval(**kwargs):
        if kwargs.get("scope") == "planning":
            captured_allow_ai.append(bool(kwargs.get("allow_ai")))
        return original_importance_eval(**kwargs)

    monkeypatch.setattr(chapter_context_module, "evaluate_story_elements_importance", _wrapped_importance_eval)
    novel.story_bible.setdefault("importance_state", {})["next_chapter_handoff"] = {
        "source_chapter": 2,
        "confidence": 0.82,
        "must_carry": {"character": ["顾青河"], "resource": ["残缺古镜"], "relation": ["林凡::顾青河"], "faction": []},
        "warm": {"character": [], "resource": [], "relation": [], "faction": []},
        "cooldown": {"character": [], "resource": [], "relation": [], "faction": []},
        "defer": {"character": [], "resource": [], "relation": [], "faction": []},
        "reason_summary": "下章优先续上顾青河与古镜这条线。",
    }

    packet = build_chapter_plan_packet(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        plan={
            "chapter_no": 3,
            "title": "夜市试探",
            "goal": "林凡带着残缺古镜进黑市，同时试探顾青河的真实态度。",
            "conflict": "顾青河和黑市都在盯着古镜。",
            "main_scene": "边城黑市",
            "supporting_character_focus": "顾青河",
        },
        serialized_last={"tail_excerpt": "林凡把古镜按回袖口。", "continuity_bridge": {"onstage_characters": ["林凡", "顾青河"]}},
        recent_summaries=[{"chapter_no": 2, "event_summary": "顾青河开始追问古镜。", "open_hooks": ["古镜到底是什么"]}],
    )

    assert captured_allow_ai and captured_allow_ai[-1] is True
    assert (packet.get("importance_handoff") or {}).get("source_chapter") == 2
    runtime = packet.get("importance_runtime") or {}
    assert ((runtime.get("selection_lanes") or {}).get("characters") or {}).get("handoff_applied") is True
