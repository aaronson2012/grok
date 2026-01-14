import logging
from typing import Callable, Any, Awaitable
from .search import search_service
from ..utils.calculator import calculate

logger = logging.getLogger("grok.tools")

class ToolRegistry:
    """
    Registry for managing available tools for the AI model.
    Allows registering tools with definitions and callbacks.
    """
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
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' not found.")
        
        func = self._tools[name]["func"]
        try:
            result = await func(**arguments)
            return str(result)
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}")
            return f"Tool execution failed. Please try again."

# Initialize registry
tool_registry = ToolRegistry()

# wrapper for web_search to match the signature expected or just usage
async def _web_search_wrapper(query: str) -> str:
    return await search_service.search(query)

async def _calculate_wrapper(expression: str) -> str:
    return calculate(expression)

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

tool_registry.register(
    name="calculator",
    description="Perform mathematical calculations. Supports basic arithmetic (+, -, *, /, **, %, //) and functions (sin, cos, sqrt, etc.).",
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The mathematical expression to evaluate, e.g. '2 + 2 * 5' or 'sqrt(16)'"
            }
        },
        "required": ["expression"]
    },
    func=_calculate_wrapper
)
