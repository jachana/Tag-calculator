"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api import router
from src.config import PROJECT_ROOT

app = FastAPI(
    title="Santiago TAG Calculator",
    description="Estimate toll (TAG) fees on Santiago's urban highways",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Serve frontend static files
frontend_dir = PROJECT_ROOT / "frontend"
if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
