from app.services import hard_fact_guard as hfg


def test_extract_chapter_hard_facts_does_not_mark_protagonist_dead_from_blocked_path_phrase() -> None:
    facts = hfg.extract_chapter_hard_facts(
        protagonist_name="方尘",
        chapter_no=3,
        chapter_title="旧路",
        content="只是这条路，现在被堵死了。方尘转过身，继续往前走。",
        plan=None,
        summary=None,
        reference_state={"life_status": {"方尘": {"status": "alive", "chapter_no": 2}}},
    )
    assert facts["life_status"] == []


def test_apply_llm_review_to_report_filters_rejected_conflicts() -> None:
    report = {
        "chapter_no": 4,
        "passed": False,
        "conflict_count": 1,
        "conflicts": [
            {
                "category": "life_status",
                "subject": "方尘",
                "previous": "dead",
                "incoming": "alive",
                "message": "误判",
                "evidence": "这条路被堵死了。方尘转过身。",
            }
        ],
        "summary": "发现 1 条高风险硬事实冲突。",
        "checked_at": "2026-03-13T00:00:00Z",
    }
    review = {
        "decisions": [
            {
                "index": 0,
                "verdict": "reject",
                "confidence": "high",
                "reason": "‘堵死了’修饰的是道路，不是人物生死。",
            }
        ]
    }
    merged = hfg._apply_llm_review_to_report(report, review)
    assert merged["passed"] is True
    assert merged["conflict_count"] == 0
    assert merged["conflicts"] == []
    assert merged["llm_review"]["rejected_conflict_count"] == 1


def test_validate_and_register_chapter_uses_llm_review_to_clear_local_false_positive(monkeypatch) -> None:
    story_bible = {
        "hard_fact_guard": {
            "enabled": True,
            "protected_categories": ["life_status"],
            "published_state": {"realm": {}, "life_status": {"方尘": {"status": "dead", "chapter_no": 3}}, "injury_status": {}, "identity_exposure": {}, "item_ownership": {}},
            "stock_state": {"realm": {}, "life_status": {"方尘": {"status": "dead", "chapter_no": 3}}, "injury_status": {}, "identity_exposure": {}, "item_ownership": {}},
            "last_checked_chapter": 3,
            "last_conflict_report": None,
            "chapter_reports": [],
        }
    }

    def fake_check(reference_state, facts, *, chapter_no):
        return {
            "chapter_no": chapter_no,
            "passed": False,
            "conflict_count": 1,
            "conflicts": [
                {
                    "category": "life_status",
                    "subject": "方尘",
                    "previous": "dead",
                    "incoming": "alive",
                    "previous_chapter_no": 3,
                    "incoming_chapter_no": chapter_no,
                    "message": "误判",
                    "evidence": "这条路被堵死了。方尘转过身。",
                }
            ],
            "summary": "发现 1 条高风险硬事实冲突。",
            "checked_at": "2026-03-13T00:00:00Z",
        }

    def fake_review(**_kwargs):
        return {
            "decisions": [
                {
                    "index": 0,
                    "verdict": "reject",
                    "confidence": "high",
                    "reason": "证据不是人物死亡/复活，只是路径描述。",
                }
            ]
        }

    monkeypatch.setattr(hfg, "check_hard_fact_conflicts", fake_check)
    monkeypatch.setattr(hfg, "_review_hard_fact_conflicts_with_llm", fake_review)
    monkeypatch.setattr(hfg, "_should_use_llm_hard_fact_review", lambda: True)

    updated_story_bible, facts, report = hfg.validate_and_register_chapter(
        story_bible,
        protagonist_name="方尘",
        chapter_no=4,
        chapter_title="坊市寻药",
        content="只是这条路被堵死了。方尘转过身，继续往前走。",
        plan=None,
        summary=None,
        serial_stage="published",
        reference_mode="published",
        raise_on_conflict=False,
        use_llm_review=True,
    )

    assert facts["life_status"] == []
    assert report["passed"] is True
    assert report["conflict_count"] == 0
    assert updated_story_bible["hard_fact_guard"]["last_conflict_report"] is None
