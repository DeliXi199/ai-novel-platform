from __future__ import annotations

import pytest

from app.api.routes import novel_chapters

from .test_ui_and_novels import client, seed_data


@pytest.fixture()
def novel_id() -> int:
    return seed_data()


def test_get_chapter_tts_status_returns_payload(novel_id: int, monkeypatch) -> None:
    def fake_status(chapter, payload=None):
        return {
            "novel_id": chapter.novel_id,
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "enabled": True,
            "ready": False,
            "generating": False,
            "stale": False,
            "voice": "zh-CN-YunxiNeural",
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz",
            "audio_url": None,
            "subtitle_url": None,
            "file_size_bytes": None,
            "subtitle_file_size_bytes": None,
            "generated_at": None,
            "reason": "还没有生成本章朗读音频。",
            "voice_options": [{"value": "zh-CN-YunxiNeural", "label": "云希（男声，沉稳）"}],
            "generated_variants": [],
        }

    monkeypatch.setattr(novel_chapters, "get_chapter_tts_status", fake_status)
    response = client.get(f"/api/v1/novels/{novel_id}/chapters/2/tts")
    assert response.status_code == 200
    payload = response.json()
    assert payload["chapter_no"] == 2
    assert payload["ready"] is False
    assert payload["voice"] == "zh-CN-YunxiNeural"
    assert payload["voice_options"]


def test_generate_chapter_tts_route_returns_audio_payload(novel_id: int, monkeypatch) -> None:
    def fake_generate(chapter, payload=None, *, force_regenerate=False):
        chapter.generation_meta = {
            **(chapter.generation_meta or {}),
            "tts": {"voice": payload.get("voice") or "zh-CN-YunxiNeural"},
        }
        return {
            "novel_id": chapter.novel_id,
            "chapter_no": chapter.chapter_no,
            "title": chapter.title,
            "enabled": True,
            "ready": True,
            "generating": False,
            "stale": False,
            "voice": payload.get("voice") or "zh-CN-YunxiNeural",
            "rate": "+0%",
            "volume": "+0%",
            "pitch": "+0Hz",
            "audio_url": "/app/media/tts/test.mp3",
            "subtitle_url": "/app/media/tts/test.vtt",
            "file_size_bytes": 1234,
            "subtitle_file_size_bytes": 256,
            "generated_at": None,
            "reason": None,
            "voice_options": [{"value": "zh-CN-YunxiNeural", "label": "云希（男声，沉稳）"}],
            "generated_variants": [{"voice": "zh-CN-YunxiNeural", "voice_label": "云希（男声，沉稳）", "rate": "+0%", "volume": "+0%", "pitch": "+0Hz", "audio_url": "/app/media/tts/test.mp3", "subtitle_url": "/app/media/tts/test.vtt", "file_size_bytes": 1234, "subtitle_file_size_bytes": 256, "generated_at": None}],
        }

    monkeypatch.setattr(novel_chapters, "generate_chapter_tts", fake_generate)
    response = client.post(
        f"/api/v1/novels/{novel_id}/chapters/2/tts/generate",
        json={"voice": "zh-CN-YunxiNeural", "force_regenerate": True},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["audio_url"] == "/app/media/tts/test.mp3"
    chapter = client.get(f"/api/v1/novels/{novel_id}/chapters/2").json()
    assert chapter["generation_meta"]["tts"]["voice"] == "zh-CN-YunxiNeural"
