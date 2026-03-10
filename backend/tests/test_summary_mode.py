from app.services.generation_exceptions import GenerationError
from app.services.openai_story_engine import summarize_chapter


CONTENT = "林玄在河滩翻出一枚旧铜片。夜风里他听见石后有脚步声，却没有立刻回头。离开前，他发现铜片背面的刻痕像是一张残缺地图。"


def test_summary_auto_falls_back_to_heuristic(monkeypatch) -> None:
    monkeypatch.setattr("app.services.openai_story_engine.settings.chapter_summary_mode", "auto")

    def broken_call(**_: str):
        raise GenerationError(code="API_TIMEOUT", message="boom", stage="chapter_summary_generation")

    monkeypatch.setattr("app.services.openai_story_engine.call_text_response", broken_call)
    summary = summarize_chapter("第1章", CONTENT)
    assert "旧铜片" in summary.event_summary or "铜片" in summary.event_summary
    assert summary.open_hooks or summary.new_clues


def test_summary_heuristic_mode_skips_llm(monkeypatch) -> None:
    monkeypatch.setattr("app.services.openai_story_engine.settings.chapter_summary_mode", "heuristic")
    called = {"value": False}

    def should_not_run(**_: str):
        called["value"] = True
        return ""

    monkeypatch.setattr("app.services.openai_story_engine.call_text_response", should_not_run)
    summarize_chapter("第1章", CONTENT)
    assert called["value"] is False
