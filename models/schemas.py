from pydantic import BaseModel
from typing import Optional, List


class LiveDataRequest(BaseModel):
    query: str
    max_results: Optional[int] = 5


class SearchResult(BaseModel):
    title:   str
    url:     str
    snippet: Optional[str] = ""
    content: Optional[str] = ""
    source:  Optional[str] = ""


class NewsResult(BaseModel):
    title:        str
    url:          str
    published_at: Optional[str] = ""
    source:       Optional[str] = ""
    snippet:      Optional[str] = ""
    content:      Optional[str] = ""


class LiveDataResponse(BaseModel):
    query:         str
    type:          str
    results_count: int
    data:          List[dict]
    summary:       Optional[str] = None
    timestamp:     str
    source_urls:   List[str]