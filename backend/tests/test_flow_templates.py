from __future__ import annotations

from app.services.openai_story_engine import ChapterPlan, _apply_flow_template_to_chapter
from app.services.story_blueprint_builders import build_flow_templates, build_template_library


def test_build_flow_templates_expanded_beyond_twenty_with_short_tags() -> None:
    templates = build_flow_templates()

    assert len(templates) >= 36
    assert all(str(item.get("flow_id") or "").strip() for item in templates)
    assert all(str(item.get("quick_tag") or "").strip() for item in templates)
    assert max(len(str(item.get("quick_tag") or "")) for item in templates) <= 6


def test_apply_flow_template_to_chapter_avoids_immediate_repeat() -> None:
    story_bible = {
        "template_library": {"flow_templates": build_flow_templates()},
        "flow_control": {"recent_flow_ids": ["conflict_upgrade"]},
    }
    chapter = ChapterPlan(
        chapter_no=8,
        title="桥上翻脸",
        goal="当众压住对方势头",
        conflict="双方矛盾升级，已经顶到硬碰边缘",
        ending_hook="更大的麻烦逼近",
        chapter_type="turning_point",
        event_type="冲突类",
        progress_kind="风险升级",
        flow_template_id="conflict_upgrade",
        hook_style="危险逼近",
    )

    _apply_flow_template_to_chapter(chapter, story_bible)

    assert chapter.flow_template_id is not None
    assert chapter.flow_template_id != "conflict_upgrade"
    assert chapter.flow_template_tag
    assert chapter.flow_template_name
    assert chapter.flow_turning_points


def test_build_template_library_includes_payoff_cards() -> None:
    from app.schemas.novel import NovelCreate

    payload = NovelCreate(genre="凡人修仙", premise="边城求生", protagonist_name="林凡", style_preferences={})
    library = build_template_library(payload)

    assert len(library.get("payoff_cards") or []) >= 40
    assert library["roadmap"]["current_payoff_card_count"] == len(library.get("payoff_cards") or [])
    assert any((item.get("payoff_mode") == "捡漏反压") for item in (library.get("payoff_cards") or []))
