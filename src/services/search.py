import logging
from duckduckgo_search import DDGS

logger = logging.getLogger("grok.search")

class SearchService:
    def search(self, query: str, max_results: int = 5) -> str:
        """
        Performs a web search and returns a formatted string of results.
        """
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
                
            if not results:
                return "No results found."

            formatted = []
            for r in results:
                formatted.append(f"- **{r['title']}**\n  {r['body']}\n  <{r['href']}>")
            
            return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return f"Search failed: {str(e)}"

search_service = SearchService()
