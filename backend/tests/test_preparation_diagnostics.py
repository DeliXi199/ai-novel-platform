from app.services.preparation_diagnostics import build_preparation_diagnostics, build_preparation_runtime_extra


def test_build_preparation_diagnostics_summarizes_pipeline() -> None:
    planning_packet = {
        "schedule_candidate_index": {
            "appearance_candidates": [{"name": "林霄"}, {"name": "苏晚"}, {"name": "周执"}],
            "relation_candidates": [{"relation_id": "r1"}, {"relation_id": "r2"}],
        },
        "card_index": {
            "characters": [{"card_id": "c1"}, {"card_id": "c2"}],
            "resources": [{"card_id": "r1"}],
            "factions": [{"card_id": "f1"}],
            "relations": [{"card_id": "rr1"}],
        },
        "payoff_candidate_index": {"candidates": [{"card_id": "p1"}, {"card_id": "p2"}]},
        "scene_template_index": {"scene_templates": [{"scene_template_id": "s1"}, {"scene_template_id": "s2"}]},
        "prompt_strategy_index": [{"strategy_id": "ps1"}, {"strategy_id": "ps2"}, {"strategy_id": "ps3"}],
        "flow_template_index": [{"flow_id": "flow1"}, {"flow_id": "flow2"}],
    }
    selection_trace = {
        "shortlist_stage": {
            "attempt": 1,
            "compact_mode": False,
            "timeout_seconds": 22,
            "prompt_chars": 3200,
            "trace": [{"duration_ms": 500, "waited_ms": 100, "response_chars": 220}],
            "result": {
                "focus_characters": ["林霄", "苏晚"],
                "main_relation_ids": ["r1"],
                "card_candidate_ids": ["c1", "r1", "f1"],
                "payoff_candidate_ids": ["p1"],
                "scene_template_ids": ["s1"],
                "flow_template_ids": ["flow1"],
                "prompt_strategy_ids": ["ps1", "ps2"],
                "shortlist_note": "先聚焦林霄与苏晚。",
            },
        },
        "selection_scope": {
            "stats": {
                "schedule": {"appearance_candidates": 2, "relation_candidates": 1},
                "cards": {"characters": 1, "resources": 1, "factions": 1, "relations": 0},
                "payoff": {"candidates": 1},
                "scene": {"scene_templates": 1},
                "prompt": {"flow_templates": 1, "prompt_strategies": 2},
            }
        },
        "schedule_trace": {"attempt": 1, "timeout_seconds": 18, "prompt_chars": 1200, "trace": [{"duration_ms": 300, "waited_ms": 50, "response_chars": 100}]},
        "cards_trace": {"attempt": 1, "timeout_seconds": 18, "prompt_chars": 1400, "trace": [{"duration_ms": 350, "waited_ms": 60, "response_chars": 110}]},
        "payoff_trace": {"attempt": 1, "timeout_seconds": 18, "prompt_chars": 900, "trace": [{"duration_ms": 260, "waited_ms": 20, "response_chars": 80}]},
        "scene_trace": {"attempt": 1, "timeout_seconds": 18, "prompt_chars": 1000, "trace": [{"duration_ms": 280, "waited_ms": 30, "response_chars": 90}]},
        "prompt_trace": {"attempt": 1, "timeout_seconds": 18, "prompt_chars": 1100, "trace": [{"duration_ms": 290, "waited_ms": 40, "response_chars": 95}]},
        "merge_trace": {"attempt": 1, "timeout_seconds": 24, "prompt_chars": 1800, "trace": [{"duration_ms": 420, "waited_ms": 70, "response_chars": 130}]},
        "selector_outputs": {
            "schedule": {"focus_characters": ["林霄", "苏晚"], "main_relations": [{"relation_id": "r1"}]},
            "cards": {"selected_card_ids": ["c1", "r1", "f1"]},
            "payoff": {"selected_card_id": "p1"},
            "scene": {"selected_scene_template_ids": ["s1"]},
            "prompt": {"selected_strategy_ids": ["ps1", "ps2"], "selected_flow_template_id": "flow1"},
        },
    }

    diagnostics = build_preparation_diagnostics(planning_packet=planning_packet, selection_trace=selection_trace)

    assert diagnostics["full_input_counts"]["schedule"]["appearance_candidates"] == 3
    assert diagnostics["shortlisted_counts"]["card_candidate_ids"] == 3
    assert diagnostics["selected_outputs"]["selected_cards"] == 3
    assert diagnostics["pipeline_totals"]["llm_calls"] == 7
    assert diagnostics["pipeline_totals"]["duration_ms"] == 2400
    assert len(diagnostics["readable_lines"]) == 3

    runtime_extra = build_preparation_runtime_extra(diagnostics)
    assert runtime_extra["preparation_llm_calls"] == 7
    assert runtime_extra["preparation_selected_payoff_card"] == "p1"
