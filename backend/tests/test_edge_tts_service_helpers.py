from __future__ import annotations

from app.services.edge_tts_service import _format_vtt_timestamp_from_100ns, _render_webvtt


def test_format_vtt_timestamp_from_100ns() -> None:
    assert _format_vtt_timestamp_from_100ns(0) == "00:00:00.000"
    assert _format_vtt_timestamp_from_100ns(12_345_678) == "00:00:01.234"


def test_render_webvtt_from_boundary_events() -> None:
    payload = _render_webvtt(
        [
            {"offset": 0, "duration": 10_000_000, "text": "你好"},
            {"offset": 10_000_000, "duration": 5_000_000, "text": "世界"},
        ],
        "你好 世界",
    )
    assert payload.startswith("WEBVTT\n\n1\n00:00:00.000 --> 00:00:01.000\n你好")
    assert "2\n00:00:01.000 --> 00:00:01.500\n世界" in payload


def test_render_webvtt_falls_back_when_no_events() -> None:
    payload = _render_webvtt([], "测试 文本")
    assert payload.startswith("WEBVTT")
    assert "00:00:00.000 --> 00:00:10.000" in payload
    assert "测试 文本" in payload
