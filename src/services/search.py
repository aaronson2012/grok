import logging
import httpx
from ..config import config
from ..utils.decorators import async_retry

logger = logging.getLogger("grok.search")

class SearchService:
    def __init__(self):
        self.api_key = config.BRAVE_SEARCH_API_KEY
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    @async_retry(retries=2, delay=1.0, exceptions=(httpx.HTTPError, httpx.TimeoutException))
    async def search(self, query: str, count: int = 5) -> str:
        """
        Performs a web search using Brave Search API and returns a formatted string.
        """
        if not self.api_key:
            return "Error: Brave Search API key is not configured."

        try:
            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self.api_key
            }
            params = {
                "q": query,
                "count": count
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

            results = data.get("web", {}).get("results", [])
            
            if not results:
                return "No results found."

            formatted = []
            for r in results:
                title = r.get("title", "No Title")
                desc = r.get("description", "No description")
                url = r.get("url", "")
                formatted.append(f"- **{title}**\n  {desc}\n  <{url}>")
            
            return "\n\n".join(formatted)

        except Exception as e:
            logger.error(f"Brave Search failed: {e}")
            # If retry fails (or other exception), return error message
            # But raise HTTP errors so retry catches them!
            if isinstance(e, (httpx.HTTPError, httpx.TimeoutException)):
                raise e
            return f"Search failed: {str(e)}"


search_service = SearchService()
