from app.services import openai_story_engine_selection as selection_engine


def _packet(candidate_rows):
    return {
        "foreshadowing_candidate_index": {
            "parent_cards": [],
            "child_cards": [],
            "candidates": candidate_rows,
        }
    }


def test_single_foreshadowing_candidate_falls_back_when_model_returns_blank():
    payload = selection_engine.ForeshadowingSelectionPayload(
        selected_primary_candidate_id="",
        selected_supporting_candidate_ids=[],
        selection_note="",
    )
    result = selection_engine._normalize_foreshadowing_selection_payload(
        payload,
        _packet([
            {
                "candidate_id": "fcand_001",
                "selector_key": "foreshadow_001",
                "legacy_candidate_id": "plant::发现宗门藏经阁内有一份残缺的渡劫阵图记录",
                "display_label": "新埋：在藏经阁发现残缺阵图记录",
                "summary": "在藏经阁发现残缺阵图记录",
            }
        ]),
        None,
    )
    assert result.selected_primary_candidate_id == "fcand_001"


def test_foreshadowing_selector_key_resolves_to_real_candidate_id():
    payload = selection_engine.ForeshadowingSelectionPayload(
        selected_primary_candidate_id="foreshadow_002",
        selected_supporting_candidate_ids=["foreshadow_001", "missing"],
    )
    result = selection_engine._normalize_foreshadowing_selection_payload(
        payload,
        _packet([
            {
                "candidate_id": "fcand_001",
                "selector_key": "foreshadow_001",
                "legacy_candidate_id": "plant::A",
                "display_label": "新埋：A",
                "summary": "A",
            },
            {
                "candidate_id": "fcand_002",
                "selector_key": "foreshadow_002",
                "legacy_candidate_id": "touch::B",
                "display_label": "轻碰：B",
                "summary": "B",
            },
        ]),
        None,
    )
    assert result.selected_primary_candidate_id == "fcand_002"
    assert result.selected_supporting_candidate_ids == ["fcand_001"]


def test_foreshadowing_display_label_resolves_to_stable_candidate_id():
    payload = selection_engine.ForeshadowingSelectionPayload(
        selected_primary_candidate_id="矿坑深处发现残破玉简",
        selected_supporting_candidate_ids=[],
    )
    result = selection_engine._normalize_foreshadowing_selection_payload(
        payload,
        _packet([
            {
                "candidate_id": "fcand_001",
                "selector_key": "foreshadow_001",
                "legacy_candidate_id": "plant::在矿坑深处发现一块残破玉简",
                "display_label": "新埋：在矿坑深处发现一块残破玉简",
                "source_hook": "在矿坑深处发现一块残破玉简",
            }
        ]),
        None,
    )
    assert result.selected_primary_candidate_id == "fcand_001"
