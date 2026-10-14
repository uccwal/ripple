"""RIPPLE 백엔드 진입점.

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request
from starlette.responses import FileResponse

from . import collect, runner
from .api.routes import router
from .config import REPO_ROOT, settings
from .db import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("ripple")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    runner.set_loop(asyncio.get_running_loop())
    collect.start_scheduler()
    log.info("RIPPLE 시작 · LLM 모드 %s · 모델 %s", settings.llm_mode, settings.model_default)
    yield


app = FastAPI(title="RIPPLE API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)


@app.get("/healthz")
def healthz():
    return {"ok": True, "llm_mode": settings.llm_mode}


# 프론트엔드 빌드(frontend/dist)가 있으면 같은 서버에서 서빙한다 (단일 데모 URL).
_dist = REPO_ROOT / "frontend" / "dist"
if not _dist.exists():
    # API만 배포했을 때 루트 안내
    @app.get("/", include_in_schema=False)
    def root():
        return {"service": "RIPPLE API", "docs": "/docs", "meta": "/api/meta", "frontend": "https://uccwal.github.io/ripple/"}
else:
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(request: Request, path: str):
        candidate = _dist / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html")
