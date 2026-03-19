from app.services.prompt_strategy_library import apply_prompt_strategy_selection_to_packet


def test_writing_card_selection_adds_card_aliases_and_child_cards() -> None:
    packet = {
        "flow_template_index": [{"flow_id": "probe_gain", "name": "试探获益", "quick_tag": "试探"}],
        "flow_child_card_index": [
            {"child_id": "probe_gain__direct_push", "parent_flow_id": "probe_gain", "name": "试探获益·先手直推", "opening_move": "开场先试", "mid_shift": "中段变招", "ending_drop": "结尾留后患"}
        ],
        "writing_child_card_index": [
            {"child_id": "continuity_guard__tail_carry", "parent_strategy_id": "continuity_guard", "name": "连续性优先·尾钩续接", "directive_focus": "先续尾钩"},
            {"child_id": "proactive_drive__visible_first_move", "parent_strategy_id": "proactive_drive", "name": "主角先手·先手显形", "directive_focus": "前两段就先手"},
        ],
        "chapter_identity": {"chapter_no": 5, "goal": "拿到消息", "main_scene": "侧殿"},
    }
    enriched = apply_prompt_strategy_selection_to_packet(
        packet,
        ["continuity_guard", "proactive_drive"],
        selected_flow_template_id="probe_gain",
        selected_flow_child_card_id="probe_gain__direct_push",
        selected_writing_child_card_ids=["continuity_guard__tail_carry", "proactive_drive__visible_first_move"],
        selection_note="测试",
    )
    assert enriched["writing_card_selection"]["selected_flow_card_id"] == "probe_gain"
    assert enriched["writing_card_selection"]["selected_flow_child_card_id"] == "probe_gain__direct_push"
    assert enriched["writing_card_selection"]["selected_writing_card_ids"] == ["continuity_guard", "proactive_drive"]
    assert enriched["writing_card_selection"]["selected_writing_child_card_ids"] == ["continuity_guard__tail_carry", "proactive_drive__visible_first_move"]
    assert enriched["selected_flow_card"]["flow_id"] == "probe_gain"
    assert enriched["selected_flow_child_card"]["child_id"] == "probe_gain__direct_push"
    assert len(enriched["selected_writing_cards"]) == 2
    assert len(enriched["selected_writing_child_cards"]) == 2
    assert enriched["selected_flow_instance_card"]["title"].endswith("本章实例卡")
    assert len(enriched["selected_writing_instance_cards"]) == 2
