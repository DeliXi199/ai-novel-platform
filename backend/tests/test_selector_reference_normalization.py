from app.services.openai_story_engine_selection import (
    PayoffSelectionPayload,
    _focused_payoff_candidate_index,
    _normalize_payoff_selection_payload,
)


def _packet():
    return {
        "payoff_candidate_index": {
            "candidates": [
                {"card_id": "payoff_hidden_snatch", "name": "暗取成利"},
                {"card_id": "payoff_public_face_slap", "name": "当众打脸"},
                {"card_id": "payoff_hidden_edge", "name": "暗里占先"},
            ]
        }
    }


def test_focused_payoff_candidate_index_adds_selector_keys():
    focused = _focused_payoff_candidate_index(_packet(), None)
    candidates = focused["candidates"]
    assert candidates[0]["selector_key"] == "payoff_001"
    assert candidates[1]["selector_key"] == "payoff_002"
    assert candidates[2]["selector_key"] == "payoff_003"


def test_normalize_payoff_selection_accepts_selector_key_alias():
    payload = PayoffSelectionPayload(selected_card_id="payoff_003")
    result = _normalize_payoff_selection_payload(payload, _packet(), None)
    assert result.selected_card_id == "payoff_hidden_edge"


def test_normalize_payoff_selection_accepts_unique_name():
    payload = PayoffSelectionPayload(selected_card_id="当众打脸")
    result = _normalize_payoff_selection_payload(payload, _packet(), None)
    assert result.selected_card_id == "payoff_public_face_slap"


def test_single_payoff_candidate_falls_back_when_model_returns_blank():
    payload = PayoffSelectionPayload(selected_card_id="")
    result = _normalize_payoff_selection_payload(
        payload,
        {
            "payoff_candidate_index": {
                "candidates": [
                    {"card_id": "payoff_hidden_snatch", "name": "暗取成利"}
                ]
            }
        },
        None,
    )
    assert result.selected_card_id == "payoff_hidden_snatch"
