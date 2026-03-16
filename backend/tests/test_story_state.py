from __future__ import annotations

from app.services.story_state import (
    clone_story_state_domains,
    ensure_story_state_domains,
    ensure_workflow_state,
    get_chapter_card_queue,
    get_current_pipeline,
    get_live_runtime,
    get_planning_status,
    update_story_state_bucket,
    workflow_bootstrap_view,
)



def test_ensure_story_state_domains_backfills_missing_sections() -> None:
    payload = {"active_arc": {"arc_no": 1}}

    def workflow_factory(active_arc):
        return {"source_arc_no": (active_arc or {}).get("arc_no", 0)}

    ensure_story_state_domains(payload, workflow_factory=workflow_factory)

    assert payload["control_console"] == {}
    assert payload["planning_layers"] == {}
    assert payload["story_state"] == {}
    assert payload["workflow_state"]["source_arc_no"] == 1
    assert payload["serial_runtime"]["delivery_mode"]
    assert payload["long_term_state"]["chapter_release_state"]["delivery_mode"]
    assert "story_domains" in payload and "characters" in payload["story_domains"]
    assert "power_system" in payload and "realm_system" in payload["power_system"]
    assert "opening_constraints" in payload
    assert "template_library" in payload
    assert "planner_state" in payload
    assert "retrospective_state" in payload
    assert "flow_control" in payload



def test_clone_story_state_domains_does_not_mutate_source() -> None:
    source = {"workflow_state": {"live_runtime": {"stage": "draft"}}}
    cloned = clone_story_state_domains(source)
    cloned["workflow_state"]["live_runtime"]["stage"] = "summary"
    assert source["workflow_state"]["live_runtime"]["stage"] == "draft"



def test_story_state_accessors_read_nested_sections() -> None:
    payload = {
        "workflow_state": {
            "live_runtime": {"stage": "chapter_draft"},
            "current_pipeline": {"target_chapter_no": 7},
            "bootstrap_state": {"status": "running"},
            "bootstrap_retry_count": 2,
        },
        "control_console": {
            "planning_status": {"planned_until": 9},
            "chapter_card_queue": [{"chapter_no": 7}, {"chapter_no": 8}, "bad"],
        },
    }

    assert get_live_runtime(payload)["stage"] == "chapter_draft"
    assert get_current_pipeline(payload)["target_chapter_no"] == 7
    assert get_planning_status(payload)["planned_until"] == 9
    assert get_chapter_card_queue(payload, limit=2) == [{"chapter_no": 7}, {"chapter_no": 8}]
    assert workflow_bootstrap_view(payload)["bootstrap_retry_count"] == 2



def test_update_story_state_bucket_merges_high_level_runtime_notes() -> None:
    payload = {}
    ensure_workflow_state(payload)
    update_story_state_bucket(payload, planning_window={"planned_until": 12}, last_chapter_update={"chapter_no": 6})
    assert payload["story_state"]["planning_window"]["planned_until"] == 12
    assert payload["story_state"]["last_chapter_update"]["chapter_no"] == 6
