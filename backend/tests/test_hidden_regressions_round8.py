import asyncio

from app.main import app
from app.services import llm_runtime


def test_app_startup_initializes_db(monkeypatch):
    calls = []

    def _fake_init_db():
        calls.append(True)

    monkeypatch.setattr("app.main.init_db", _fake_init_db)
    async def _run():
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(_run())
    assert calls == [True]


def test_groq_uses_chat_completions(monkeypatch):
    captured = {}

    class _ChatCompletions:
        def create(self, **kwargs):
            captured["path"] = "chat"
            captured["kwargs"] = kwargs
            return type("Resp", (), {"choices": [type("Choice", (), {"message": type("Msg", (), {"content": "pong"})()})()]})()

    class _Responses:
        def create(self, **kwargs):
            captured["path"] = "responses"
            captured["kwargs"] = kwargs
            return type("Resp", (), {"output_text": "pong"})()

    class _Client:
        def __init__(self):
            self.chat = type("Chat", (), {"completions": _ChatCompletions()})()
            self.responses = _Responses()

    monkeypatch.setattr(llm_runtime, "OpenAI", object(), raising=False)
    monkeypatch.setattr(llm_runtime.settings, "llm_provider", "groq", raising=False)
    monkeypatch.setattr(llm_runtime.settings, "groq_api_key", "test-key", raising=False)
    monkeypatch.setattr(llm_runtime.settings, "groq_model", "test-model", raising=False)
    monkeypatch.setattr(llm_runtime, "get_client", lambda **kwargs: _Client())
    monkeypatch.setattr(llm_runtime, "throttle_llm_calls", lambda stage: 0)

    text = llm_runtime.call_text_response(stage="chapter_generation", system_prompt="sys", user_prompt="usr", max_output_tokens=12)

    assert text == "pong"
    assert captured["path"] == "chat"
    assert "messages" in captured["kwargs"]
    assert "input" not in captured["kwargs"]
    assert captured["kwargs"]["max_tokens"] == 12
