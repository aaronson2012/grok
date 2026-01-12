from openai import AsyncOpenAI, APIError, APITimeoutError, RateLimitError
from ..config import config
from .tools import tool_registry
from ..utils.decorators import async_retry
import logging

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

    @async_retry(retries=3, delay=1.0, exceptions=(APIError, APITimeoutError, RateLimitError))
    async def generate_response(self, system_prompt: str, user_message: str | list, history: list[dict] = None, tools: list | bool = None) -> any:
        """
        Generates a response from the AI model.
        Returns the full response message object (which might contain tool_calls).
        Args:
            system_prompt: The system instruction.
            user_message: String (text only) or List (multimodal content blocks).
            history: Previous messages.
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
            
            if not response or not response.choices:
                raise ValueError(f"Invalid response from API: {response}")
                
            return response.choices[0].message
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            # If retry failed, re-raise so the retry decorator handles it or the caller
            # But wait, we want to return a fallback for user-facing errors?
            # Ideally the decorator handles the retries, and if it still fails, we want to return a fallback
            # UNLESS we are in a background task (like summarization).
            
            # Let's keep the fallback for chat responses, but we need to know context.
            # For now, simplistic approach:
            from types import SimpleNamespace
            return SimpleNamespace(content="I'm having trouble thinking right now. Please try again later.", tool_calls=None)

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
