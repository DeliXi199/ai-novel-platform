import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_normalize_and_validate() -> None:
    cfg = Settings(
        llm_provider="Groq",
        chapter_context_mode="FULL",
        chapter_summary_mode="LLM",
        openai_reasoning_effort="HIGH",
    )
    assert cfg.llm_provider == "groq"
    assert cfg.chapter_context_mode == "full"
    assert cfg.chapter_summary_mode == "llm"
    assert cfg.openai_reasoning_effort == "high"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("llm_provider", "mock"),
        ("chapter_summary_mode", "bad"),
        ("chapter_context_mode", "dense"),
    ],
)
def test_settings_reject_invalid_enums(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        Settings(**{field: value})


def test_settings_reject_invalid_ranges() -> None:
    with pytest.raises(ValidationError):
        Settings(chapter_hard_min_visible_chars=2000, chapter_min_visible_chars=1000)
