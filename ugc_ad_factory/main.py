"""
UGC Ad Factory - FastAPI Application Entry Point

Run with: uvicorn ugc_ad_factory.main:app --host 0.0.0.0 --port 8090 --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.routes import router
from .config import settings
from . import __version__


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup/shutdown."""
    # Startup
    print(f"Starting UGC Ad Factory v{__version__}")
    print(f"ComfyUI: {settings.comfyui_url}")
    print(f"KeyAI API: {settings.keyai_api_url}")
    print(f"GCS Bucket: {settings.gcs_bucket}")

    yield

    # Shutdown
    print("Shutting down UGC Ad Factory")


app = FastAPI(
    title="UGC Ad Factory",
    description="AI-powered UGC video ad generation pipeline",
    version=__version__,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint with service info."""
    return {
        "service": "UGC Ad Factory",
        "version": __version__,
        "docs": "/docs",
        "health": "/api/ugc/health",
    }


@app.get("/health")
async def health():
    """Simple health check."""
    return {"status": "ok", "version": __version__}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ugc_ad_factory.main:app",
        host=settings.ugc_service_host,
        port=settings.ugc_service_port,
        reload=True,
    )
