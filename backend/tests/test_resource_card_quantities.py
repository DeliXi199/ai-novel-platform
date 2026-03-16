from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.novel import Novel
from app.schemas.novel import NovelCreate
from app.services.chapter_context_support import build_chapter_plan_packet
from app.services.novel_bootstrap import build_base_story_bible
from app.services.resource_card_support import ensure_resource_card_structure, parse_resource_seed
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
        genre="凡人流修仙",
        premise="主角靠有限资源在边城求生。",
        protagonist_name="陆川",
        style_preferences={
            "current_resources": ["三块灵石", "两张符箓", "青锋剑"],
            "factions": ["黑市"],
        },
    )
    novel = Novel(
        id=11,
        title="边城求生",
        genre=payload.genre,
        premise=payload.premise,
        protagonist_name=payload.protagonist_name,
        style_preferences=payload.style_preferences,
        story_bible=build_base_story_bible(payload),
        current_chapter_no=0,
        status="active",
    )
    novel.story_bible = ensure_story_architecture(novel.story_bible or {}, novel)
    return novel


def test_parse_resource_seed_extracts_quantity_and_unit() -> None:
    parsed = parse_resource_seed("三块灵石")
    assert parsed["name"] == "灵石"
    assert parsed["quantity"] == 3
    assert parsed["unit"] == "块"
    assert parsed["stackable"] is True

    weapon = parse_resource_seed("青锋剑")
    assert weapon["name"] == "青锋剑"
    assert weapon["quantity"] == 1
    assert weapon["quantity_mode"] == "entity"


def test_story_domains_resources_keep_quantity_fields() -> None:
    novel = _build_novel()
    resources = (novel.story_bible.get("story_domains") or {}).get("resources") or {}

    assert resources["灵石"]["quantity"] == 3
    assert resources["灵石"]["unit"] == "块"
    assert resources["灵石"]["stackable"] is True
    assert resources["灵石"]["ability_summary"]
    assert "补充灵气" in (resources["灵石"]["core_functions"] or [])
    assert resources["符箓"]["quantity"] == 2
    assert resources["青锋剑"]["quantity"] == 1
    assert resources["青锋剑"]["quantity_mode"] == "entity"
    assert resources["青锋剑"]["resource_kind"] in {"装备/法器", "装备/实体"}


def test_build_chapter_plan_packet_includes_resource_plan_and_quantity_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_ai_reasoning(monkeypatch)
    novel = _build_novel()
    plan = {
        "chapter_no": 1,
        "title": "黑市换符",
        "goal": "陆川在黑市消耗一张符箓换到两块灵石，再试着压价保住青锋剑。",
        "conflict": "黑市摊主看上了青锋剑，想逼他连剑一起押出去。",
        "main_scene": "边城黑市",
        "supporting_character_focus": "摊主老周",
    }
    packet = build_chapter_plan_packet(
        story_bible=novel.story_bible,
        protagonist_name=novel.protagonist_name,
        plan=plan,
        serialized_last={"tail_excerpt": "陆川把青锋剑按在袖口后，走进了黑市。"},
        recent_summaries=[{"chapter_no": 0, "event_summary": "陆川清点了手头资源。"}],
    )

    assert packet["relevant_cards"]["resources"]["灵石"]["quantity"] == 3
    assert packet["relevant_cards"]["resources"]["符箓"]["quantity"] == 2
    assert packet["relevant_cards"]["resources"]["灵石"]["ability_summary"]
    assert packet["resource_plan"]["符箓"]["planned_action"] == "consume"
    assert packet["resource_plan"]["符箓"]["delta_hint"] == -1
    assert packet["resource_plan"]["灵石"]["planned_action"] == "gain"
    assert packet["resource_plan"]["灵石"]["delta_hint"] == 2
    assert packet["resource_capability_plan"]["__meta__"]["reasoning_mode"]
    assert packet["resource_capability_plan"]["灵石"]["expected_costs"]
    assert packet["resource_capability_plan"]["青锋剑"]["resource_kind"]


def test_update_story_architecture_after_chapter_applies_numeric_resource_plan() -> None:
    novel = _build_novel()
    plan = {
        "chapter_no": 1,
        "title": "黑市换符",
        "goal": "陆川在黑市消耗一张符箓换到两块灵石。",
        "ending_hook": "摊主老周忽然问起剑的来路。",
        "supporting_character_focus": "摊主老周",
        "planning_packet": {
            "resource_plan": {
                "符箓": {"planned_action": "consume", "delta_hint": -1, "note": "换价时用掉一张符箓。"},
                "灵石": {"planned_action": "gain", "delta_hint": 2, "note": "成交后多得两块灵石。"},
            },
            "resource_capability_plan": {
                "__meta__": {"reasoning_mode": "local_constraints_seed"},
                "青锋剑": {
                    "should_use": True,
                    "usage_role": "压价威慑",
                    "unlock_change": "维持当前解锁状态",
                    "cooldown_after_use": "无",
                    "expected_costs": ["可能损耗灵力"],
                    "expected_risks": ["暴露兵器来路"],
                }
            },
        },
    }
    summary = SimpleNamespace(
        event_summary="陆川用一张符箓换回两块灵石，并意识到老周开始打听青锋剑。",
        open_hooks=["老周为何盯上剑"],
        closed_hooks=[],
        character_updates={"摊主老周": {"attitude": "试探"}},
    )

    updated = update_story_architecture_after_chapter(
        story_bible=novel.story_bible,
        novel=novel,
        chapter_no=1,
        chapter_title="黑市换符",
        plan=plan,
        summary=summary,
        last_chapter_tail="陆川把剑压在袖口，走进了黑市。",
    )

    resources = (updated.get("story_domains") or {}).get("resources") or {}
    assert resources["符箓"]["quantity"] == 1
    assert resources["灵石"]["quantity"] == 5
    assert "第1章按规划gain 2块" in resources["灵石"]["recent_change"]
    assert ensure_resource_card_structure(resources["青锋剑"])["quantity"] == 1
    assert resources["青锋剑"]["last_capability_update"]["chapter_no"] == 1
    assert resources["青锋剑"]["unlock_state"]["last_trigger"]["chapter_no"] == 1
