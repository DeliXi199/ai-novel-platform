from app.services.llm_runtime import current_api_key, require_generation_provider


def test_current_api_key_respects_bootstrap_stage(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_runtime.OpenAI", object(), raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.llm_provider", "openai", raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.bootstrap_llm_provider", "deepseek", raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.openai_api_key", "openai-key", raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.deepseek_api_key", "deepseek-key", raising=False)

    assert current_api_key() == "openai-key"
    assert current_api_key("global_outline_generation") == "deepseek-key"


def test_require_generation_provider_uses_stage_specific_key(monkeypatch) -> None:
    monkeypatch.setattr("app.services.llm_runtime.OpenAI", object(), raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.llm_provider", "openai", raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.bootstrap_llm_provider", "deepseek", raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.openai_api_key", None, raising=False)
    monkeypatch.setattr("app.services.llm_runtime.settings.deepseek_api_key", "deepseek-key", raising=False)

    require_generation_provider("global_outline_generation")
