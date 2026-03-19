from app.services import chapter_preparation_selection_runner as runner
from app.services import openai_story_engine_selection as selection_engine


def test_runner_autolocks_single_payoff_and_foreshadowing_candidates(monkeypatch):
    chapter_plan = {"chapter_no": 1}
    planning_packet = {
        "schedule_candidate_index": {"appearance_candidates": [], "relation_candidates": []},
        "card_index": {"characters": [{"card_id": "char_a"}]},
        "payoff_candidate_index": {"candidates": [{"card_id": "payoff_only", "name": "唯一爽点"}]},
        "foreshadowing_candidate_index": {
            "parent_cards": [],
            "child_cards": [],
            "candidates": [{"candidate_id": "plant::唯一伏笔", "summary": "唯一伏笔"}],
        },
        "prompt_bundle_index": {
            "flow_cards": [{"flow_id": "flow_a"}],
            "writing_cards": [{"strategy_id": "strategy_a"}],
            "flow_child_cards": [],
            "writing_child_cards": [],
        },
    }

    shortlist_payload = selection_engine.ChapterPreparationShortlistPayload(
        card_candidate_ids=["char_a"],
        payoff_candidate_ids=["payoff_only"],
        foreshadowing_candidate_ids=["plant::唯一伏笔"],
        prompt_strategy_ids=["strategy_a"],
        flow_template_ids=["flow_a"],
    )

    def fake_shortlist(**kwargs):
        return shortlist_payload, {"trace": []}

    def fake_parallel(**kwargs):
        assert kwargs["precomputed_selector_payloads"].keys() >= {"payoff", "foreshadowing"}
        return {
            "results": {
                "schedule": selection_engine.CharacterRelationScheduleReviewPayload(),
                "cards": selection_engine.ChapterCardSelectionPayload(selected_card_ids=["char_a"]),
                "payoff": selection_engine._normalize_payoff_selection_payload(kwargs["precomputed_selector_payloads"]["payoff"], planning_packet, kwargs["shortlist"]),
                "foreshadowing": selection_engine._normalize_foreshadowing_selection_payload(kwargs["precomputed_selector_payloads"]["foreshadowing"], planning_packet, kwargs["shortlist"]),
                "prompt": selection_engine.PromptStrategySelectionPayload(selected_flow_template_id="flow_a", selected_strategy_ids=["strategy_a"]),
            },
            "trace": {"selectors": {"payoff": {"skipped": True}, "foreshadowing": {"skipped": True}}},
        }

    def fake_merge(**kwargs):
        outputs = kwargs["selector_outputs"]
        return selection_engine.ChapterPreparationSelectionResult(
            schedule_review=outputs["schedule"],
            card_selection=outputs["cards"],
            payoff_selection=outputs["payoff"],
            foreshadowing_selection=outputs["foreshadowing"],
            prompt_strategy_selection=outputs["prompt"],
            selection_trace={},
        ), {"merge_trace": {}}

    monkeypatch.setattr(runner.selection_engine, "is_openai_enabled", lambda: True)
    monkeypatch.setattr(runner, "run_preparation_shortlist", fake_shortlist)
    monkeypatch.setattr(runner, "run_parallel_preparation_selectors", fake_parallel)
    monkeypatch.setattr(runner, "merge_parallel_preparation_selection", fake_merge)

    result = runner.run_chapter_preparation_selection(chapter_plan=chapter_plan, planning_packet=planning_packet)

    assert result.payoff_selection.selected_card_id == "payoff_only"
    assert result.foreshadowing_selection.selected_primary_candidate_id == "plant::唯一伏笔"
    overview = result.selection_trace.get("candidate_overview") or {}
    assert overview.get("payoff", {}).get("candidate_count") == 1
    assert overview.get("payoff", {}).get("auto_selected") is True
    assert overview.get("foreshadowing", {}).get("candidate_count") == 1
    assert overview.get("foreshadowing", {}).get("auto_selected") is True
