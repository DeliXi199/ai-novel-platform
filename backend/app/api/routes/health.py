from fastapi import APIRouter, Query

from app.services.generation_exceptions import GenerationError
from app.services.openai_story_engine import get_llm_runtime_config, ping_generation_provider

router = APIRouter()


@router.get("/health")
def health_check() -> dict:
    return {"status": "ok"}


@router.get("/health/llm")
def llm_health(ping: bool = Query(False, description="是否实际请求一次模型接口做连通性测试")) -> dict:
    base = get_llm_runtime_config()
    if not ping:
        return {"status": "ok", "llm": base, "ping_performed": False}
    try:
        return {"status": "ok", "llm": ping_generation_provider(), "ping_performed": True}
    except GenerationError as exc:
        return {
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
