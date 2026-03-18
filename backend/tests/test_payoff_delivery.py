from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.novel import Novel
from app.services import chapter_generation as cg
from app.services.chapter_quality import assess_payoff_delivery



def test_assess_payoff_delivery_detects_public_payoff() -> None:
    content = (
        "林凡把药包轻轻放回木盘，先问掌柜那味药材为什么只剩最后一份。\n\n"
        "掌柜原本还想压价，听见这话后目光一顿，立刻改了先前的口风。\n\n"
        "林凡顺势把价码压了回去，当场换到了那味关键药材。\n\n"
        "旁边两个伙计互看一眼，不敢再插嘴，掌柜却把林凡的模样记住了，心里已经起了追查的念头。"
    )
    plan = {
        "title": "药铺压价",
        "progress_kind": "资源推进",
        "payoff_visibility": "public",
        "payoff_level": "medium",
        "reader_payoff": "主角把关键药材压价换到手。",
        "new_pressure": "掌柜开始记住主角并准备追查来路。",
        "planning_packet": {
            "selected_payoff_card": {
                "card_id": "payoff_trade_crush",
                "payoff_mode": "压价反杀",
                "payoff_visibility": "public",
                "reader_payoff": "主角在交易桌上不靠硬打，靠判断把价码压回来了。",
                "new_pressure": "掌柜会记住主角，并在事后追查。",
                "aftershock": "风头一露，后续交易会更难藏。",
                "external_reaction": "必须让掌柜或旁人改口、迟疑或变脸。",
            }
        },
    }

    payload = assess_payoff_delivery(title="药铺压价", content=content, chapter_plan=plan)

    assert payload["delivery_level"] in {"medium", "high"}
    assert payload["visibility_fit"] is True
    assert payload["reward_hits"] >= 1
    assert payload["reaction_hits"] >= 1
    assert payload["pressure_hits"] >= 1
    assert payload["runtime_note"]
    assert payload["summary_lines"]



def test_assess_payoff_delivery_flags_hollow_payoff() -> None:
    content = (
        "林凡坐在窗边想了很久。\n\n"
        "他觉得今晚的交易未必简单，于是把药盒重新放回桌上。\n\n"
        "外面风声渐急，他暂时压下念头，打算明日再看。"
    )
    plan = {
        "title": "先按不动",
        "progress_kind": "资源推进",
        "payoff_visibility": "public",
        "payoff_level": "strong",
        "reader_payoff": "主角必须拿到关键药材并让掌柜吃瘪。",
        "new_pressure": "掌柜会追查主角的来路。",
    }

    payload = assess_payoff_delivery(title="先按不动", content=content, chapter_plan=plan)

    assert payload["delivery_level"] == "low"
    assert "回报落袋不够明确" in payload["missed_targets"]
    assert any(item in payload["missed_targets"] for item in ["外部反应显影不足", "结果句不够清晰"])



def test_generate_next_chapter_persists_payoff_delivery_runtime(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    novel = Novel(
        title="测试爽点兑现",
        genre="修仙",
        premise="主角在坊市里抢一味关键药材。",
        protagonist_name="林凡",
        style_preferences={},
        story_bible={},
        current_chapter_no=0,
        status="planning_ready",
    )
    db.add(novel)
    db.commit()
    db.refresh(novel)

    monkeypatch.setattr(cg, "begin_llm_trace", lambda trace_key: "trace-payoff")
    monkeypatch.setattr(cg, "clear_llm_trace", lambda: None)
    monkeypatch.setattr(cg, "get_llm_trace", lambda: [])
    monkeypatch.setattr(cg, "_acquire_generation_slot", lambda db, novel_id: "planning_ready")
    monkeypatch.setattr(cg, "_load_novel_or_404", lambda db, novel_id: db.query(Novel).filter(Novel.id == novel_id).first())
    monkeypatch.setattr(cg, "_release_generation_slot", lambda db, novel_id, status: None)
    monkeypatch.setattr(cg, "_ensure_generation_runtime_budget", lambda **kwargs: None)
    monkeypatch.setattr(cg, "ensure_story_architecture", lambda story_bible, novel: story_bible or {})
    monkeypatch.setattr(cg, "refresh_planning_views", lambda story_bible, current_chapter_no: story_bible)
    monkeypatch.setattr(cg, "_ensure_outline_state", lambda story_bible: None)
    monkeypatch.setattr(cg, "_validate_required_planning_docs", lambda story_bible, chapter_no: None)
    monkeypatch.setattr(cg, "_validate_fact_ledger_state", lambda story_bible, chapter_no: None)
    monkeypatch.setattr(cg, "_promote_pending_arc_if_needed", lambda story_bible, next_chapter_no: None)
    monkeypatch.setattr(cg, "_auto_prepare_future_planning", lambda db, novel, **kwargs: {"planned_until": 4})

    plan = {
        "chapter_no": 1,
        "title": "药铺压价",
        "goal": "拿到关键药材。",
        "opening_beat": "林凡走进坊市药铺。",
        "supporting_character_focus": "陈掌柜",
        "event_type": "交易类",
        "progress_kind": "资源推进",
        "proactive_move": "主动压价试探掌柜底线",
        "payoff_or_pressure": "换到药材，但被掌柜记住",
        "payoff_visibility": "public",
        "payoff_level": "medium",
        "reader_payoff": "主角把关键药材压价换到手。",
        "new_pressure": "掌柜开始记住主角。",
        "planning_packet": {
            "selected_payoff_card": {
                "card_id": "payoff_trade_crush",
                "payoff_mode": "压价反杀",
                "payoff_visibility": "public",
                "reader_payoff": "主角在交易桌上不靠硬打，靠判断把价码压回来了。",
                "new_pressure": "掌柜会记住主角，并在事后追查。",
                "aftershock": "风头一露，后续交易会更难藏。",
                "external_reaction": "必须让掌柜或旁人改口、迟疑或变脸。",
            }
        },
    }
    monkeypatch.setattr(cg, "_ensure_plan_for_chapter", lambda db, novel, next_no, recent_summaries: dict(plan))
    monkeypatch.setattr(cg, "_enrich_plan_agency", lambda novel, current_plan, **kwargs: current_plan)
    monkeypatch.setattr(cg, "collect_active_interventions", lambda db, novel_id, next_chapter_no: [])
    monkeypatch.setattr(cg, "_serialize_active_interventions", lambda active: [])
    monkeypatch.setattr(cg, "_serialize_last_chapter", lambda last_chapter, protagonist_name=None: {})
    monkeypatch.setattr(cg, "build_chapter_plan_packet", lambda **kwargs: kwargs["plan"].get("planning_packet") or {})
    monkeypatch.setattr(cg, "review_character_relation_schedule_and_select_cards", lambda **kwargs: ({}, SimpleNamespace(selected_card_ids=[], selection_note="")))
    monkeypatch.setattr(cg, "apply_schedule_review_to_packet", lambda packet, review: packet)
    monkeypatch.setattr(cg, "apply_soft_card_ranking_to_packet", lambda packet, chapter_plan=None: packet)
    monkeypatch.setattr(cg, "apply_card_selection_to_packet", lambda packet, selected_ids, selection_note="": packet)
    monkeypatch.setattr(cg, "_save_pipeline_execution_packet", lambda **kwargs: {"scene_outline": ["入店", "压价"], "chapter_execution_card": kwargs["plan"]})
    monkeypatch.setattr(cg, "serialize_local_novel_context", lambda **kwargs: {"context_mode": "planned_local", "story_memory": {}})
    monkeypatch.setattr(cg, "_fit_chapter_payload_budget", lambda **kwargs: (kwargs["novel_context"], kwargs["recent_summaries"], kwargs["serialized_last"], kwargs["serialized_active"], {"prompt_chars": 128}))
    monkeypatch.setattr(
        cg,
        "_attempt_generate_validated_chapter",
        lambda **kwargs: (
            "药铺压价",
            "林凡把药包轻轻放回木盘，先问掌柜那味药材为什么只剩最后一份。\n\n掌柜原本还想压价，听见这话后目光一顿，立刻改了先前的口风。\n\n林凡顺势把价码压了回去，当场换到了那味关键药材。\n\n旁边两个伙计互看一眼，不敢再插嘴，掌柜却把林凡的模样记得更清楚了。",
            {"title": "药铺压价"},
            dict(plan),
            {"target_visible_chars_min": 900, "target_visible_chars_max": 1600},
            {"quality_rejections": []},
        ),
    )
    monkeypatch.setattr(
        cg,
        "generate_chapter_summary_and_title_package",
        lambda **kwargs: SimpleNamespace(
            summary=SimpleNamespace(
                event_summary="林凡压回价码，换到关键药材。",
                character_updates={"陈掌柜": {"态度": "记住了林凡"}},
                new_clues=["药铺也在找同类药材"],
                open_hooks=["掌柜会不会追查林凡来路"],
                closed_hooks=[],
                model_dump=lambda mode="python": {
                    "event_summary": "林凡压回价码，换到关键药材。",
                    "character_updates": {"陈掌柜": {"态度": "记住了林凡"}},
                    "new_clues": ["药铺也在找同类药材"],
                    "open_hooks": ["掌柜会不会追查林凡来路"],
                    "closed_hooks": [],
                },
            ),
            title_refinement=SimpleNamespace(
                recommended_title="药铺压价",
                candidates=[],
            ),
        ),
    )
    monkeypatch.setattr(
        cg,
        "validate_and_register_chapter",
        lambda *args, **kwargs: (
            kwargs.get("story_bible") or {},
            {"realm": [], "life_status": [], "injury_status": [], "identity_exposure": [], "item_ownership": []},
            {"passed": True, "conflict_count": 0},
        ),
    )
    monkeypatch.setattr(cg, "update_story_architecture_after_chapter", lambda **kwargs: kwargs["story_bible"])
    monkeypatch.setattr(cg, "sync_character_registry", lambda db, novel, **kwargs: None)
    monkeypatch.setattr(cg, "_mark_generated_chapter_delivery", lambda db, novel, chapter: (novel, {"delivery_mode": "live_publish", "serial_stage": "published", "is_published": True, "locked_from_edit": True, "published_at": None}))

    chapter = cg.generate_next_chapter(db, novel)

    assert chapter.generation_meta["payoff_delivery"]["delivery_level"] in {"medium", "high"}
    assert chapter.generation_meta["payoff_delivery"]["runtime_note"]
    live_runtime = ((db.query(Novel).filter(Novel.id == novel.id).first().story_bible or {}).get("workflow_state") or {}).get("live_runtime") or {}
    assert live_runtime["payoff_delivery_level"] in {"medium", "high"}
    assert live_runtime["payoff_delivery_note"]



def test_review_payoff_delivery_with_ai_requests_compensation(monkeypatch) -> None:
    from app.services.chapter_quality import review_payoff_delivery_with_ai

    monkeypatch.setattr("app.services.chapter_quality.is_openai_enabled", lambda: True)
    monkeypatch.setattr(
        "app.services.chapter_quality.call_json_response",
        lambda **kwargs: {
            "delivery_level": "low",
            "verdict": "兑现偏虚",
            "missed_targets": ["回报落袋不够明确", "外部反应显影不足"],
            "runtime_note": "这章气氛有了，但回报和显影都还不够硬。",
            "summary_lines": [
                "兑现判断：兑现偏虚。",
                "主要问题：回报没真正落袋，旁人也没明显反应。",
                "下一章应补一次明确回收。",
            ],
            "should_compensate_next_chapter": True,
            "compensation_priority": "high",
            "compensation_note": "下一章优先补一次明确落袋与外部显影。",
        },
    )
    local = {
        "delivery_level": "low",
        "selected_level": "strong",
        "verdict": "兑现偏虚",
        "visibility_fit": False,
        "missed_targets": ["回报落袋不够明确", "外部反应显影不足"],
        "summary_lines": ["本地判定偏虚。"],
    }
    reviewed = review_payoff_delivery_with_ai(
        title="先按不动",
        content="林凡想了想，决定明日再看。",
        chapter_plan={"payoff_level": "strong", "payoff_visibility": "public"},
        local_review=local,
    )
    assert reviewed["ai_review_used"] is True
    assert reviewed["review_source"] == "ai_rechecked"
    assert reviewed["should_compensate_next_chapter"] is True
    assert reviewed["compensation_priority"] == "high"
