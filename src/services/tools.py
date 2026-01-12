import json
import logging
import inspect
from typing import Callable, Any, Awaitable
from .search import search_service

logger = logging.getLogger("grok.tools")

class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(self, name: str, description: str, parameters: dict, func: Callable[..., Awaitable[Any]]):
        """
        Register a new tool.
        
        Args:
            name: The name of the tool (e.g. "web_search")
            description: Description for the LLM
            parameters: JSON schema for parameters
            func: Async function to execute
        """
        self._tools[name] = {
            "definition": {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters
                }
            },
            "func": func
        }
        logger.info(f"Registered tool: {name}")

    def get_definitions(self) -> list[dict]:
        """Returns the list of tool definitions for the LLM."""
        return [tool["definition"] for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict) -> str:
        """Executes a tool by name with the given arguments."""
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found.")
        
        func = self._tools[name]["func"]
        try:
            result = await func(**arguments)
            return str(result)
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return f"Error executing tool {name}: {str(e)}"

# Initialize registry
tool_registry = ToolRegistry()

# wrapper for web_search to match the signature expected or just usage
async def _web_search_wrapper(query: str) -> str:
    return await search_service.search(query)

# Register web_search
tool_registry.register(
    name="web_search",
    description="Search the web for current information, news, or facts.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query, e.g. 'latest release of Python', 'weather in Tokyo'"
            }
        },
        "required": ["query"]
    },
    func=_web_search_wrapper
)
