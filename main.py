import sys
import asyncio

# Fix for Windows — MUST be before any asyncio usage
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import search, news, trends
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


app = FastAPI(
    title="VGen Live Data API",
    description=(
        "Real-time web scraping API using Playwright. "
        "Provides live search, news, and trend data "
        "for GPT-4.1 powered assistants."
    ),
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search.router,  prefix="/api/v1", tags=["Live Search"])
app.include_router(news.router,    prefix="/api/v1", tags=["Live News"])
app.include_router(trends.router,  prefix="/api/v1", tags=["Live Trends"])


@app.get("/")
async def root():
    return {
        "service":   "VGen Live Data API",
        "status":    "running",
        "version":   "1.0.0",
        "timestamp": now_iso(),
        "endpoints": {
            "search": "POST /api/v1/search",
            "news":   "POST /api/v1/news",
            "trends": "POST /api/v1/trends",
            "docs":   "GET  /docs"
        }
    }


@app.get("/health")
async def health():
    return {
        "status":    "healthy",
        "timestamp": now_iso()
    }