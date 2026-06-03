from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

try:
    from .config import get_settings
    from .routers.document import router as document_router
    from .routers.translate import router as translate_router
    from .schemas import HealthResponse
    from .services.model_service import get_model_service
except ImportError:
    # Support direct script execution: `python backend\app\main.py`.
    BACKEND_ROOT = Path(__file__).resolve().parents[1]
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))

    from app.config import get_settings
    from app.routers.document import router as document_router
    from app.routers.translate import router as translate_router
    from app.schemas import HealthResponse
    from app.services.model_service import get_model_service


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.scratch_dir.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(translate_router, prefix=settings.api_prefix)
app.include_router(document_router, prefix=settings.api_prefix)


@app.get("/health", response_model=HealthResponse)
def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok", backend=get_model_service().describe_backend())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000)
