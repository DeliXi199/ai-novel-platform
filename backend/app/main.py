from fastapi import FastAPI

from app.api.routes.health import router as health_router
from app.api.routes.novels import router as novels_router
from app.core.config import settings

app = FastAPI(title=settings.app_name, debug=settings.app_debug)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(novels_router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {
        "message": settings.app_name,
        "docs": "/docs",
        "api_prefix": settings.api_v1_prefix,
    }
