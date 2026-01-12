from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError
from ..config import config
from .tools import tool_registry
from ..utils.decorators import async_retry
from .db import db
import logging
from types import SimpleNamespace

logger = logging.getLogger("grok.ai")

class AIService:
    """
    Service for interacting with OpenRouter API (OpenAI-compatible).
    Handles message generation and tool definition.
    """
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=config.OPENROUTER_API_KEY,
        )
        self.model = config.OPENROUTER_MODEL
        
        # Define available tools
        self.tools = tool_registry.get_definitions()

    async def generate_response(self, system_prompt: str, user_message: str | list, history: list[dict] | None = None, tools: list | bool | None = None) -> any:
        """
        Public wrapper for response generation that handles errors and returns a fallback.
        """
        try:
            return await self._generate_response_internal(system_prompt, user_message, history, tools)
        except Exception as e:
            logger.error(f"Error generating AI response (after retries): {e}")
            
            # Log to DB for debugging
            await db.log_error(e, {"context": "AIService.generate_response", "system_prompt": system_prompt[:100], "user_message_len": len(str(user_message))})
            
            # Return fallback object
            return SimpleNamespace(content="I'm having trouble thinking right now. Please try again later.", tool_calls=None)

    @async_retry(retries=3, delay=1.0, exceptions=(APIError, APITimeoutError, RateLimitError))
    async def _generate_response_internal(self, system_prompt: str, user_message: str | list, history: list[dict] | None = None, tools: list | bool | None = None) -> any:
        """
        Internal method for generating responses with retry logic.
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            messages.extend(history)
            
        messages.append({"role": "user", "content": user_message})

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self.tools if tools is not False else None,
            extra_headers={
                "HTTP-Referer": "https://github.com/your-repo/grok",
                "X-Title": "Grok Discord Bot",
            }
        )
        
        if not response or not response.choices:
            raise ValueError(f"Invalid response from API: {response}")
            
        return response.choices[0].message

    @async_retry(retries=2, delay=2.0)
    async def summarize_conversation(self, current_summary: str, new_messages: list[str]) -> str:
        """
        Generates a concise summary of the conversation.
        """
        prompt = (
            "Update the conversation summary with the new messages.\n"
            "Keep it concise (max 3 sentences) and focus on key facts/decisions.\n"
            f"Current Summary: {current_summary or 'None'}\n"
            f"New Messages:\n" + "\n".join(new_messages)
        )
        
        messages = [
            {"role": "system", "content": "You are a conversation summarizer."},
            {"role": "user", "content": prompt}
        ]
        
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages
        )
        
        return response.choices[0].message.content

ai_service = AIService()
