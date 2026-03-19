from app.services.chapter_preparation_selection_execution import normalize_preselection_payload
from app.services.openai_story_engine_selection import (
    ChapterPreparationShortlistPayload,
    _focused_foreshadowing_candidate_index,
    _focused_payoff_candidate_index,
    _focused_prompt_bundle_index,
)


def _packet() -> dict:
    return {
        "book_execution_profile": {
            "positioning_summary": "低位求生，优先探查与误判翻盘。",
            "flow_family_priority": {"high": ["探查"], "medium": ["成长"], "low": ["关系"]},
            "payoff_priority": {"high": ["误判翻盘"], "medium": ["捡漏反压"], "low": ["公开打脸"]},
            "foreshadowing_priority": {"primary": ["身份真相型"], "secondary": ["规则异常型"], "hold_back": ["关系失衡型"]},
            "writing_strategy_priority": {"high": ["danger_pressure"], "medium": ["goal_chain_clarity"], "low": ["emotional_undertow"]},
            "rhythm_bias": {"opening_pace": "稳推", "hook_strength": "中强"},
            "demotion_rules": ["不要连续重复同一试探结构"],
        },
        "payoff_candidate_index": {
            "candidates": [
                {"card_id": "p_face", "name": "公开打脸", "payoff_mode": "借势立威", "family": "public"},
                {"card_id": "p_flip", "name": "误判翻盘", "payoff_mode": "误判翻盘", "family": "reverse"},
                {"card_id": "p_snatch", "name": "捡漏反压", "payoff_mode": "捡漏反压", "family": "quiet"},
            ]
        },
        "foreshadowing_candidate_index": {
            "parent_cards": [
                {"card_id": "fp_relation", "name": "关系失衡型"},
                {"card_id": "fp_identity", "name": "身份真相型"},
            ],
            "child_cards": [
                {"child_id": "fc_identity", "parent_id": "fp_identity", "name": "只露异常不露答案"},
                {"child_id": "fc_relation", "parent_id": "fp_relation", "name": "轻碰关系失衡"},
            ],
            "candidates": [
                {"candidate_id": "cand_relation", "parent_card_id": "fp_relation", "child_card_id": "fc_relation", "action_type": "touch", "summary": "轻碰关系裂缝"},
                {"candidate_id": "cand_identity", "parent_card_id": "fp_identity", "child_card_id": "fc_identity", "action_type": "plant", "summary": "埋身份异常"},
            ],
        },
        "prompt_bundle_index": {
            "flow_templates": [
                {"flow_id": "flow_rel", "card_id": "flow_rel", "family": "关系", "name": "关系拉扯", "title": "关系拉扯"},
                {"flow_id": "flow_probe", "card_id": "flow_probe", "family": "探查", "name": "秘密验证", "title": "秘密验证"},
                {"flow_id": "flow_growth", "card_id": "flow_growth", "family": "成长", "name": "资源成长", "title": "资源成长"},
            ],
            "prompt_strategies": [
                {"strategy_id": "emotional_undertow", "card_id": "emotional_undertow", "name": "情绪潜流", "title": "情绪潜流"},
                {"strategy_id": "danger_pressure", "card_id": "danger_pressure", "name": "危险压力", "title": "危险压力"},
                {"strategy_id": "goal_chain_clarity", "card_id": "goal_chain_clarity", "name": "目标链清晰", "title": "目标链清晰"},
            ],
            "flow_child_cards": [
                {"child_id": "flow_probe__direct", "parent_flow_id": "flow_probe", "title": "秘密验证·直推"},
                {"child_id": "flow_rel__soft", "parent_flow_id": "flow_rel", "title": "关系拉扯·缓推"},
            ],
            "writing_child_cards": [
                {"child_id": "danger_pressure__clock", "parent_strategy_id": "danger_pressure", "title": "危险压力·时限压近"},
                {"child_id": "emotional_undertow__light", "parent_strategy_id": "emotional_undertow", "title": "情绪潜流·轻压"},
            ],
        },
        "prompt_strategy_index": [
            {"strategy_id": "emotional_undertow"},
            {"strategy_id": "danger_pressure"},
            {"strategy_id": "goal_chain_clarity"},
        ],
        "flow_template_index": [
            {"flow_id": "flow_rel"},
            {"flow_id": "flow_probe"},
            {"flow_id": "flow_growth"},
        ],
        "schedule_candidate_index": {"appearance_candidates": [], "relation_candidates": []},
        "card_index": {"characters": [], "resources": [], "factions": [], "relations": []},
    }



def test_book_execution_profile_keeps_candidate_order_and_exposes_prompt_only_guidance() -> None:
    packet = _packet()
    focused = _focused_payoff_candidate_index(packet, None)
    ordered_ids = [item["card_id"] for item in focused["candidates"]]
    assert ordered_ids == ["p_face", "p_flip", "p_snatch"]
    assert focused["book_bias"]["mode"] == "prompt_only"
    assert focused["book_bias"]["applied"] is False
    assert focused["book_bias"]["payoff_priority"]["high"] == ["误判翻盘"]



def test_book_execution_profile_keeps_prompt_bundle_order_and_exposes_guidance() -> None:
    packet = _packet()
    focused = _focused_prompt_bundle_index(packet, None)
    flow_ids = [item["flow_id"] for item in focused["flow_templates"]]
    strategy_ids = [item["strategy_id"] for item in focused["prompt_strategies"]]
    assert flow_ids == ["flow_rel", "flow_probe", "flow_growth"]
    assert strategy_ids == ["emotional_undertow", "danger_pressure", "goal_chain_clarity"]
    assert focused["book_bias"]["flow_family_priority"]["high"] == ["探查"]



def test_normalize_preselection_payload_only_validates_without_book_bias_backfill() -> None:
    packet = _packet()
    payload = ChapterPreparationShortlistPayload(
        payoff_candidate_ids=["p_flip", "unknown"],
        foreshadowing_parent_card_ids=["fp_identity", "bad_parent"],
        foreshadowing_child_card_ids=["fc_identity", "bad_child"],
        foreshadowing_candidate_ids=["cand_identity", "bad_candidate"],
        flow_template_ids=["flow_probe", "bad_flow"],
        flow_child_card_ids=["flow_probe__direct", "bad_flow_child"],
        prompt_strategy_ids=["danger_pressure", "bad_prompt"],
        writing_child_card_ids=["danger_pressure__clock", "bad_writing_child"],
    )
    normalized = normalize_preselection_payload(payload, packet)
    assert normalized.payoff_candidate_ids == ["p_flip"]
    assert normalized.foreshadowing_parent_card_ids == ["fp_identity"]
    assert normalized.foreshadowing_child_card_ids == ["fc_identity"]
    assert normalized.foreshadowing_candidate_ids == ["cand_identity"]
    assert normalized.flow_template_ids == ["flow_probe"]
    assert normalized.flow_child_card_ids == ["flow_probe__direct"]
    assert normalized.prompt_strategy_ids == ["danger_pressure"]
    assert normalized.writing_child_card_ids == ["danger_pressure__clock"]
    assert "execution profile" not in (normalized.shortlist_note or "")



def test_focused_foreshadowing_preserves_source_order_until_ai_selects() -> None:
    packet = _packet()
    focused = _focused_foreshadowing_candidate_index(packet, None)
    assert [item["card_id"] for item in focused["parent_cards"]] == ["fp_relation", "fp_identity"]
    assert [item["candidate_id"] for item in focused["candidates"]] == ["cand_relation", "cand_identity"]
    assert focused["book_bias"]["foreshadowing_priority"]["high"] == ["身份真相型"]


def test_normalize_preselection_payload_accepts_foreshadowing_selector_aliases() -> None:
    packet = _packet()
    # simulate new stable foreshadowing ids with display labels
    packet["foreshadowing_candidate_index"]["candidates"] = [
        {
            "candidate_id": "fcand_001",
            "selector_key": "foreshadow_001",
            "legacy_candidate_id": "plant::埋身份异常",
            "display_label": "新埋：埋身份异常",
            "parent_card_id": "fp_identity",
            "child_card_id": "fc_identity",
            "source_hook": "埋身份异常",
        },
        {
            "candidate_id": "fcand_002",
            "selector_key": "foreshadow_002",
            "legacy_candidate_id": "touch::轻碰关系裂缝",
            "display_label": "轻碰：轻碰关系裂缝",
            "parent_card_id": "fp_relation",
            "child_card_id": "fc_relation",
            "source_hook": "轻碰关系裂缝",
        },
    ]
    payload = ChapterPreparationShortlistPayload(
        payoff_candidate_ids=["option_2"],
        foreshadowing_candidate_ids=["candidate_2", "轻碰关系裂缝"],
    )
    normalized = normalize_preselection_payload(payload, packet)
    assert normalized.payoff_candidate_ids == ["p_flip"]
    assert normalized.foreshadowing_candidate_ids == ["fcand_002"]
