from fastapi import APIRouter, HTTPException
from models.schemas import LiveDataRequest, LiveDataResponse
from services.scraper import fetch_trends_results, get_timestamp

router = APIRouter()


@router.post("/trends", response_model=LiveDataResponse)
async def live_trends(request: LiveDataRequest):
    """
    Live trends search.
    Use for: current trends, what's popular now,
    industry trends, market trends, technology trends.
    """
    try:
        results = await fetch_trends_results(
            query=request.query,
            max_results=request.max_results
        )

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No trends found for: {request.query}"
            )

        return LiveDataResponse(
            query=request.query,
            type="trends",
            data=results,
            summary=f"Found {len(results)} trend results for '{request.query}'",
            timestamp=get_timestamp(),
            source_urls=[r["url"] for r in results]
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))