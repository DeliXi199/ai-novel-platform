from app.services.chapter_context_common import _collect_live_hooks, _tail_paragraphs
from app.services.chapter_payload_budget import _fit_chapter_payload_budget


def test_collect_live_hooks_skips_closed_and_duplicates() -> None:
    recent_summaries = [
        {"chapter_no": 1, "open_hooks": ["古镜为何发热", "黑市是谁在查"], "closed_hooks": []},
        {"chapter_no": 2, "open_hooks": ["黑市是谁在查", "顾青河想做什么"], "closed_hooks": ["古镜为何发热"]},
    ]

    hooks = _collect_live_hooks(recent_summaries)

    assert "古镜为何发热" not in hooks
    assert hooks.count("黑市是谁在查") == 1
    assert "顾青河想做什么" in hooks



def test_fit_chapter_payload_budget_keeps_bridge_excerpt_in_sync(monkeypatch) -> None:
    long_excerpt = "尾声" * 220
    novel_context = {
        "context_mode": "planned_local",
        "premise": "前提" * 120,
        "story_memory": {
            "global_direction": [{"act_no": 1}, {"act_no": 2}],
            "live_hooks": ["a", "b", "c", "d"],
            "core_conflict": "冲突" * 80,
            "phase_rule": "规则" * 80,
        },
    }
    recent_summaries = [
        {"chapter_no": 1, "event_summary": "事件1"},
        {"chapter_no": 2, "event_summary": "事件2"},
    ]
    serialized_last = {
        "tail_excerpt": long_excerpt,
        "last_two_paragraphs": ["第一段" * 80, "第二段" * 80],
        "unresolved_action_chain": ["线索1", "线索2", "线索3"],
        "continuity_bridge": {
            "tail_excerpt": long_excerpt,
            "last_two_paragraphs": ["第一段" * 80, "第二段" * 80],
            "unresolved_action_chain": ["线索1", "线索2", "线索3"],
        },
    }
    serialized_active = [{"id": 1}, {"id": 2}]

    monkeypatch.setattr("app.services.chapter_payload_budget.settings.chapter_prompt_max_chars", 300)

    context, summaries, last, active, stats = _fit_chapter_payload_budget(
        novel_context=novel_context,
        recent_summaries=recent_summaries,
        serialized_last=serialized_last,
        serialized_active=serialized_active,
    )

    assert last["tail_excerpt"] == last["continuity_bridge"]["tail_excerpt"]
    assert last["last_two_paragraphs"] == last["continuity_bridge"]["last_two_paragraphs"]
    assert last["unresolved_action_chain"] == last["continuity_bridge"]["unresolved_action_chain"]
    assert len(context["story_memory"]["global_direction"]) <= 2
    assert len(context["story_memory"]["live_hooks"]) <= 3
    assert stats["payload_chars_after"] <= stats["payload_chars_before"]
    assert len(summaries) <= len(recent_summaries)
    assert len(active) <= len(serialized_active)



def test_tail_paragraphs_prefers_recent_blocks() -> None:
    content = "第一段\n\n第二段\n\n第三段"
    assert _tail_paragraphs(content, count=2) == ["第二段", "第三段"]
