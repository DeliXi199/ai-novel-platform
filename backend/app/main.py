from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.health import router as health_router
from app.api.routes.novels import router as novels_router
from app.core.config import settings
from app.db.init_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    settings.media_root_path.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.app_name, debug=settings.app_debug, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix)
app.include_router(novels_router, prefix=settings.api_v1_prefix)

_FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
_ASSETS_DIR = _FRONTEND_DIR / "assets"
if _ASSETS_DIR.exists():
    app.mount("/app/assets", StaticFiles(directory=_ASSETS_DIR), name="frontend-assets")

_media_dir = settings.media_root_path
app.mount("/app/media", StaticFiles(directory=_media_dir, check_dir=False), name="frontend-media")


@app.get("/")
def root() -> dict:
    return {
        "message": settings.app_name,
        "docs": "/docs",
        "api_prefix": settings.api_v1_prefix,
        "studio": "/app",
    }


@app.get("/app", include_in_schema=False)
@app.get("/app/reader", include_in_schema=False)
def studio_index():
    index_file = _FRONTEND_DIR / "index.html"
    if not index_file.exists():
        return {"message": "Frontend not found", "expected": str(index_file)}
    return FileResponse(index_file)
