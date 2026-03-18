from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.services.ai_capability_audit import build_repo_ai_fallback_audit
from app.services.ai_capability_policy import build_llm_policy_report
from app.services.generation_exceptions import GenerationError
from app.services.llm_runtime import get_llm_runtime_config, ping_generation_provider

router = APIRouter()


def _safe_runtime_payload(payload: dict | None) -> dict:
    base = dict(payload or {})
    if settings.expose_diagnostic_runtime:
        return base
    base.pop("api_key_masked", None)
    base.pop("base_url", None)
    return base


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/health/llm")
def llm_health(
    ping: bool = Query(False, description="是否实际请求一次模型接口做连通性测试"),
    stage: str = Query("default", description="default 或 bootstrap；bootstrap 会按初始化阶段配置做测试"),
):
    effective_stage = "global_outline_generation" if stage == "bootstrap" else None
    base = _safe_runtime_payload(get_llm_runtime_config(effective_stage))
    if not ping:
        return {"status": "ok", "llm": base, "ping_performed": False}
    try:
        return {
            "status": "ok",
            "llm": _safe_runtime_payload(ping_generation_provider(effective_stage or "llm_ping")),
            "ping_performed": True,
        }
    except GenerationError as exc:
        payload = {
            "status": "error",
            "ping_performed": True,
            "llm": base,
            "error": {
                "code": exc.code,
                "stage": exc.stage,
                "message": exc.message,
                "provider": exc.provider,
                "retryable": exc.retryable,
                "details": exc.details,
            },
        }
        return JSONResponse(status_code=exc.http_status, content=payload)


@router.get("/health/llm/policy")
def llm_policy() -> dict:
    payload = build_llm_policy_report()
    if not settings.expose_diagnostic_runtime:
        runtime = payload.get("llm_runtime") or {}
        for key in list(runtime.keys()):
            runtime[key] = _safe_runtime_payload(runtime.get(key) or {})
        payload["llm_runtime"] = runtime
    return payload

@router.get("/health/llm/audit")
def llm_audit() -> dict:
    return {
        "policy": llm_policy(),
        "repo_audit": build_repo_ai_fallback_audit(),
    }

