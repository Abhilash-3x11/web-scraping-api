from fastapi import APIRouter, HTTPException
from models.schemas import LiveDataRequest, LiveDataResponse
from services.scraper import fetch_news_results, get_timestamp

router = APIRouter()


@router.post("/news", response_model=LiveDataResponse)
async def live_news(request: LiveDataRequest):
    """
    Live news search.
    Use for: latest news, breaking news, today's headlines,
    current events, recent announcements.
    """
    try:
        results = await fetch_news_results(
            query=request.query,
            max_results=request.max_results
        )

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No news found for: {request.query}"
            )

        return LiveDataResponse(
            query=request.query,
            type="news",
            data=results,
            summary=f"Found {len(results)} news articles for '{request.query}'",
            timestamp=get_timestamp(),
            source_urls=[r["url"] for r in results]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))