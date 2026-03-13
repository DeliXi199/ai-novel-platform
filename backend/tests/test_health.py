from fastapi.testclient import TestClient

from app.main import app
from app.services.generation_exceptions import GenerationError

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_llm_health_without_ping() -> None:
    response = client.get("/api/v1/health/llm")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["ping_performed"] is False
    assert "llm" in payload


def test_llm_health_ping_returns_http_error(monkeypatch) -> None:
    def _boom(*_args, **_kwargs):
        raise GenerationError(
            code="API_TIMEOUT",
            message="ping failed",
            stage="llm_ping",
            retryable=True,
            http_status=503,
            provider="openai",
            details={"trace_id": "test-trace"},
        )

    monkeypatch.setattr("app.api.routes.health.ping_generation_provider", _boom)
    response = client.get("/api/v1/health/llm?ping=true")
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "error"
    assert payload["error"]["code"] == "API_TIMEOUT"
    assert payload["error"]["details"]["trace_id"] == "test-trace"
