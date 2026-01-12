from openai import AsyncOpenAI
from ..config import config
import logging

logger = logging.getLogger("grok.ai")

class AIService:
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.OPENROUTER_API_KEY,
        )
        self.model = config.OPENROUTER_MODEL
        
        # Define available tools
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": "Search the web for current information, news, or facts.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query, e.g. 'latest release of Python', 'weather in Tokyo'"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

    async def generate_response(self, system_prompt: str, user_message: str, history: list[dict] = None, tools: list = None) -> any:
        """
        Generates a response from the AI model.
        Returns the full response message object (which might contain tool_calls).
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            messages.extend(history)
            
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools if tools is not False else None,
                extra_headers={
                    "HTTP-Referer": "https://github.com/your-repo/grok",
                    "X-Title": "Grok Discord Bot",
                }
            )
            return response.choices[0].message
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            # Return a dummy object with content so the bot doesn't crash
            from types import SimpleNamespace
            return SimpleNamespace(content="I'm having trouble thinking right now. Please try again later.", tool_calls=None)

ai_service = AIService()
