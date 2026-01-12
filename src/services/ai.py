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

    async def generate_response(self, system_prompt: str, user_message: str, history: list[dict] = None) -> str:
        """
        Generates a response from the AI model.
        
        Args:
            system_prompt: The persona/system instruction.
            user_message: The latest message from the user.
            history: List of previous message dicts {'role': 'user'|'assistant', 'content': '...'}
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if history:
            # simple validation/cleaning could go here
            messages.extend(history)
            
        messages.append({"role": "user", "content": user_message})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                # OpenRouter specific headers if needed, usually handled by base_url
                extra_headers={
                    "HTTP-Referer": "https://github.com/your-repo/grok", # Optional: for OpenRouter rankings
                    "X-Title": "Grok Discord Bot",
                }
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating AI response: {e}")
            return "I'm having trouble thinking right now. Please try again later."

ai_service = AIService()
