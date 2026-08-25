from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import companies, upload, modules, memo

settings = get_settings()

app = FastAPI(
    title="VC Investment Intelligence Platform API",
    description=(
        "Extract -> Research -> Verify -> Challenge -> Benchmark -> Reason -> Conclude. "
        "Every module writes to a shared Evidence store; nothing reaches the memo without "
        "a traceable origin, source and confidence level."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "llm_mode": "live" if settings.llm_available else "mock",
        "search_mode": "live" if settings.search_available else "mock",
        "pappers_mode": "live" if settings.pappers_available else "mock",
    }


app.include_router(companies.router)
app.include_router(upload.router)
app.include_router(modules.router)
app.include_router(memo.router)
