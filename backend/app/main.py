from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers.document import router as document_router
from .routers.translate import router as translate_router
from .schemas import HealthResponse
from .services.model_service import get_model_service


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
