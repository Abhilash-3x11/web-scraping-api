from fastapi import APIRouter, HTTPException
from services.scraper import (
    fetch_google_results,
    fetch_news_results,
    fetch_trends_results,
    get_timestamp
)
from models.schemas import LiveDataRequest, LiveDataResponse

router = APIRouter()


@router.post("/search", response_model=LiveDataResponse)
async def search(request: LiveDataRequest):
    try:
        print(f"[ROUTER] Search: '{request.query}' max={request.max_results}")
        results = await fetch_google_results(request.query, request.max_results)
        print(f"[ROUTER] Results count: {len(results) if results else 0}")

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No results found for: {request.query}"
            )

        return LiveDataResponse(
            query         = request.query,
            type          = "general",
            results_count = len(results),
            data          = results,
            summary       = f"Found {len(results)} live results for '{request.query}'",
            timestamp     = get_timestamp(),
            source_urls   = [r.get("url", "") for r in results]
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ROUTER] Error:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/news", response_model=LiveDataResponse)
async def news(request: LiveDataRequest):
    try:
        print(f"[ROUTER] News: '{request.query}' max={request.max_results}")
        results = await fetch_news_results(request.query, request.max_results)
        print(f"[ROUTER] News count: {len(results) if results else 0}")

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No news found for: {request.query}"
            )

        return LiveDataResponse(
            query         = request.query,
            type          = "news",
            results_count = len(results),
            data          = results,
            summary       = f"Found {len(results)} live news for '{request.query}'",
            timestamp     = get_timestamp(),
            source_urls   = [r.get("url", "") for r in results]
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ROUTER] Error:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/trends", response_model=LiveDataResponse)
async def trends(request: LiveDataRequest):
    try:
        print(f"[ROUTER] Trends: '{request.query}' max={request.max_results}")
        results = await fetch_trends_results(request.query, request.max_results)
        print(f"[ROUTER] Trends count: {len(results) if results else 0}")

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No trends found for: {request.query}"
            )

        return LiveDataResponse(
            query         = request.query,
            type          = "trends",
            results_count = len(results),
            data          = results,
            summary       = f"Found {len(results)} trend results for '{request.query}'",
            timestamp     = get_timestamp(),
            source_urls   = [r.get("url", "") for r in results]
        )

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[ROUTER] Error:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))