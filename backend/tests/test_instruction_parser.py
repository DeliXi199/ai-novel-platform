from app.services.generation_exceptions import GenerationError
from app.services.instruction_parser import heuristic_parse_instruction, parse_reader_instruction
from app.services.llm_types import ParsedInstructionPayload


def test_heuristic_parse_instruction_extracts_multiple_constraints() -> None:
    parsed = heuristic_parse_instruction("后面几章轻松一点，节奏快一点，多写阿青，别让阿青出事，关系再暧昧一点")
    assert parsed["tone"] == "lighter"
    assert parsed["pace"] == "faster"
    assert parsed["character_focus"]["阿青"] >= 0.75
    assert "阿青" in parsed["protected_characters"]
    assert parsed["relationship_direction"] == "closer"


def test_parse_reader_instruction_merges_model_result(monkeypatch) -> None:
    def fake_model_parse(_: str) -> ParsedInstructionPayload:
        return ParsedInstructionPayload(
            character_focus={"林玄": 0.9},
            tone="darker",
            pace=None,
            protected_characters=["师姐"],
            relationship_direction=None,
        )

    monkeypatch.setattr("app.services.instruction_parser.parse_instruction_with_openai", fake_model_parse)
    parsed = parse_reader_instruction("节奏快一点，别让师姐出事")
    assert parsed["tone"] == "darker"
    assert parsed["pace"] == "faster"
    assert parsed["character_focus"]["林玄"] == 0.9
    assert "师姐" in parsed["protected_characters"]


def test_parse_reader_instruction_falls_back_to_heuristic(monkeypatch) -> None:
    def broken_parse(_: str):
        raise GenerationError(code="X", message="boom", stage="instruction_parse")

    monkeypatch.setattr("app.services.instruction_parser.parse_instruction_with_openai", broken_parse)
    parsed = parse_reader_instruction("黑暗一点，慢一点，多写白河")
    assert parsed["tone"] == "darker"
    assert parsed["pace"] == "slower"
    assert parsed["character_focus"]["白河"] >= 0.75
