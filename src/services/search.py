import logging
import httpx
from ..config import config
from ..utils.decorators import async_retry
from .db import db

logger = logging.getLogger("grok.search")

class SearchService:
    def __init__(self):
        self.api_key = config.PERPLEXITY_API_KEY
        self.base_url = config.PERPLEXITY_BASE_URL

    @async_retry(retries=2, delay=1.0, exceptions=(httpx.HTTPError, httpx.TimeoutException))
    async def search(self, query: str, count: int = 5) -> str:
        if not self.api_key:
            return "Error: Perplexity API key is not configured."

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "query": query,
                "max_results": count
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(self.base_url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()

            results = data.get("results", [])
            
            if not results:
                return "No results found."

            formatted = []
            for r in results:
                title = r.get("title", "No Title")
                desc = r.get("snippet", "No description")
                url = r.get("url", "")
                formatted.append(f"- **{title}**\n  {desc}\n  <{url}>")
            
            return "\n\n".join(formatted)

        except Exception as e:
            logger.error(f"Perplexity Search failed: {e}")
            
            if isinstance(e, (httpx.HTTPError, httpx.TimeoutException)):
                raise e
                
            await db.log_error(e, {"context": "SearchService.search", "query": query})
            
            return "Search failed. Please try again."


search_service = SearchService()
