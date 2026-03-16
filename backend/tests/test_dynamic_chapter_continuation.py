from __future__ import annotations

from app.services import openai_story_engine as ose
from app.services.openai_story_engine import generate_chapter_from_plan


def _base_plan() -> dict:
    return {
        "chapter_no": 3,
        "title": "废料区试手",
        "goal": "验证镜子的反应",
        "conflict": "废料区里有人可能在暗中观察",
        "progress_kind": "信息推进",
        "event_type": "发现类",
        "proactive_move": "主动验证镜面反应",
        "payoff_or_pressure": "确认镜子并非死物，同时留下被人注意到的风险",
        "ending_hook": "有人在暗处盯上了方尘",
        "hook_style": "危险逼近",
        "opening_beat": "方尘先拿镜子做试验",
        "mid_turn": "第一次试验没有反应，方尘临时换法",
        "discovery": "镜面终于出现细微变化",
        "closing_image": "脚步声从废铁堆后传来",
    }


def test_generate_chapter_continues_body_before_closing(monkeypatch) -> None:
    stages: list[str] = []

    def fake_call_text_response(*, stage, system_prompt, user_prompt, max_output_tokens, timeout_seconds):
        stages.append(stage)
        if stage == "chapter_generation_body":
            return "方尘没有急着离开，而是把镜子按在掌心细看。第一次灌入灵力，镜面毫无反应。"
        if stage == "chapter_generation_continue":
            return "他换了个角度，再把灵力压成更细的一线，镜面终于浮出一圈极浅的纹路。与此同时，废铁堆后传来一声压得很低的咳嗽。"
        if stage == "chapter_generation_closing":
            return "方尘指尖一顿，没有回头，只把镜子收入袖中，顺手踢乱脚边铁片，借着杂声慢慢退开。那道藏在暗处的呼吸，却始终没有散。"
        raise AssertionError(stage)

    monkeypatch.setattr(ose, "call_text_response", fake_call_text_response)
    monkeypatch.setattr(ose.settings, "chapter_dynamic_continuation_enabled", True, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_max_segments", 3, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_continuation_min_growth_chars", 20, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_total_visible_chars_cap", 800, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_continuation_target_min_visible_chars", 120, raising=False)

    draft = generate_chapter_from_plan(
        novel_context={},
        chapter_plan=_base_plan(),
        last_chapter={},
        recent_summaries=[],
        active_interventions=[],
        target_words=120,
        target_visible_chars_min=80,
        target_visible_chars_max=160,
        request_timeout_seconds=120,
    )

    assert stages == ["chapter_generation_body", "chapter_generation_continue", "chapter_generation_closing"]
    assert draft.body_segments == 2
    assert draft.continuation_rounds == 1
    assert "镜面终于浮出一圈极浅的纹路" in draft.content
    assert "那道藏在暗处的呼吸" in draft.content



def test_generate_chapter_stops_continuation_at_segment_cap(monkeypatch) -> None:
    stages: list[str] = []

    def fake_call_text_response(*, stage, system_prompt, user_prompt, max_output_tokens, timeout_seconds):
        stages.append(stage)
        if stage == "chapter_generation_body":
            return "方尘把镜子放在膝上，反复调整角度，先记下镜面每一次黯淡与反光。"
        if stage == "chapter_generation_continue":
            return "他又试了第二种灌注法，镜面这才浮出一点像水波一样的灰纹，边缘还微微颤了一下，像是要把更深处的东西翻出来。"
        if stage == "chapter_generation_closing":
            return "他把那道灰纹死死记住，收起镜子，决定今晚不在这里做第三次尝试。"
        raise AssertionError(stage)

    monkeypatch.setattr(ose, "call_text_response", fake_call_text_response)
    monkeypatch.setattr(ose.settings, "chapter_dynamic_continuation_enabled", True, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_max_segments", 2, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_continuation_min_growth_chars", 10, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_total_visible_chars_cap", 900, raising=False)
    monkeypatch.setattr(ose.settings, "chapter_body_continuation_target_min_visible_chars", 80, raising=False)

    draft = generate_chapter_from_plan(
        novel_context={},
        chapter_plan=_base_plan(),
        last_chapter={},
        recent_summaries=[],
        active_interventions=[],
        target_words=140,
        target_visible_chars_min=220,
        target_visible_chars_max=320,
        request_timeout_seconds=120,
    )

    assert stages.count("chapter_generation_continue") == 1
    assert draft.body_segments == 2
    assert draft.body_stop_reason == "segment_cap_reached"
