from fastapi import APIRouter

from .novel_chapters import router as chapters_router
from .novel_interventions import router as interventions_router
from .novel_management import router as management_router
from .novel_runtime import router as runtime_router

router = APIRouter()
router.include_router(management_router)
router.include_router(runtime_router)
router.include_router(chapters_router)
router.include_router(interventions_router)
