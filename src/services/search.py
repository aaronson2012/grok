import logging
import httpx
from ..config import config

logger = logging.getLogger("grok.search")

class SearchService:
    def __init__(self):
        self.api_key = config.BRAVE_SEARCH_API_KEY
        self.base_url = "https://api.search.brave.com/res/v1/web/search"

    def search(self, query: str, count: int = 5) -> str:
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
            
            # Using synchronous httpx for simplicity in this tool context, 
            # though async would be better if we refactored the whole chain.
            # Given the tool call wrapper in chat.py is synchronous in logic flow (awaiting the result),
            # but runs in an async function, we should ideally use async httpx.
            # However, to keep the interface simple and consistent with previous sync implementation:
            with httpx.Client() as client:
                response = client.get(self.base_url, headers=headers, params=params)
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
            return f"Search failed: {str(e)}"

search_service = SearchService()
