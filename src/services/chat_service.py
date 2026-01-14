"""
Unified chat service for both Discord and Telegram platforms.
Handles message history building, AI response generation, tool execution, and summarization.
"""
import asyncio
import base64
import io
import json
import logging
from datetime import datetime
from typing import Any, Callable, Awaitable

from PIL import Image

from .ai import ai_service
from .db import db
from .tools import tool_registry
from ..types import ChatMessage, AIResponse
from ..utils.constants import (
    CONTEXT_RESET_THRESHOLD,
    MAX_HISTORY_MESSAGES,
    DISCORD_RESPONSE_LIMIT,
    TELEGRAM_RESPONSE_LIMIT,
    Platform,
)

logger = logging.getLogger("grok.chat_service")


class ChatService:
    """
    Platform-agnostic chat service that handles the core chat logic.
    Discord and Telegram handlers should use this service instead of duplicating logic.
    """

    async def build_system_prompt(
        self,
        base_persona: str,
        platform: Platform,
        current_summary: str | None = None,
        emoji_context: str | None = None,
    ) -> str:
        """Build the full system prompt with context."""
        current_date = datetime.now().strftime("%Y-%m-%d")
        memory_block = f"\n[PREVIOUS CONVERSATION SUMMARY]:\n{current_summary}\n" if current_summary else ""
        
        # Platform-specific limits
        if platform == Platform.DISCORD:
            char_limit = DISCORD_RESPONSE_LIMIT
            platform_note = "Discord message"
            emoji_instruction = (
                "Use emojis naturally (about once every 2-3 sentences). "
                "Use a mix of standard Unicode emojis and the provided Custom Server Emojis. "
                "Prefer the Custom Emojis when they fit the specific context or emotion perfectly."
            ) if emoji_context else ""
        else:
            char_limit = TELEGRAM_RESPONSE_LIMIT
            platform_note = "Telegram message"
            emoji_instruction = ""

        emoji_block = f"\n{emoji_context}" if emoji_context else ""
        
        system_prompt = (
            f"Current Date: {current_date}\n{base_persona}{emoji_block}\n{memory_block}\n"
            "INSTRUCTION: Focus primarily on the user's latest message. "
            "Use the chat history ONLY for context if relevant. "
            "If the latest request is unrelated to previous messages, treat it as a new topic. "
            "Users are identified by [User ID] at the start of their messages. "
            f"IMPORTANT: Keep your response concise and under {char_limit} characters to fit in a {platform_note}."
        )
        
        if platform == Platform.DISCORD:
            system_prompt += (
                " To address a user, use the format <@User ID>. Do NOT use their display name in brackets. "
                "Example: If you see '[12345]: Hello', reply with 'Hi <@12345>!'. "
                f"{emoji_instruction}"
            )
        
        return system_prompt

    async def build_message_history(
        self,
        messages: list[ChatMessage],
        bot_id: int,
        max_messages: int = MAX_HISTORY_MESSAGES,
    ) -> list[dict]:
        """
        Build message history for AI context.
        
        Args:
            messages: List of ChatMessage objects, ordered oldest to newest
            bot_id: The bot's user ID to identify assistant messages
            max_messages: Maximum number of messages to include
            
        Returns:
            List of message dicts in OpenAI format
        """
        history = []
        last_msg_time = None
        
        for msg in reversed(messages[:max_messages]):
            # Check for time gap (context reset)
            if last_msg_time and msg.timestamp:
                time_diff = (last_msg_time - msg.timestamp).total_seconds()
                if time_diff > CONTEXT_RESET_THRESHOLD:
                    break
            
            last_msg_time = msg.timestamp
            role = "assistant" if msg.author_id == bot_id else "user"
            content = msg.content
            
            if role == "user" and msg.author_id:
                content = f"[{msg.author_id}]: {content}"
            
            if content:
                history.insert(0, {"role": role, "content": content, "id": msg.id})
        
        return history

    async def process_image_to_base64(self, image_data: bytes) -> str:
        """
        Process image data to base64 data URL.
        Uses asyncio.to_thread to avoid blocking the event loop.
        """
        def _process_image(data: bytes) -> str:
            with Image.open(io.BytesIO(data)) as img:
                # Handle animated GIFs - extract middle frame
                if getattr(img, "is_animated", False):
                    middle_frame = img.n_frames // 2
                    img.seek(middle_frame)
                
                output_buffer = io.BytesIO()
                img.convert("RGB").save(output_buffer, format="JPEG")
                output_buffer.seek(0)
                
                base64_image = base64.b64encode(output_buffer.getvalue()).decode('utf-8')
                return f"data:image/jpeg;base64,{base64_image}"
        
        return await asyncio.to_thread(_process_image, image_data)

    async def build_user_content(
        self,
        text: str,
        user_id: int,
        images: list[tuple[bytes, str]] | None = None,
    ) -> list[dict]:
        """
        Build multimodal user content for AI.
        
        Args:
            text: The text message
            user_id: User's ID
            images: List of (image_bytes, content_type) tuples
            
        Returns:
            List of content parts for OpenAI API
        """
        user_content = [{"type": "text", "text": f"[{user_id}]: {text}"}]
        
        if images:
            for image_data, content_type in images:
                try:
                    if "gif" in content_type:
                        # Process GIF to extract frame
                        data_url = await self.process_image_to_base64(image_data)
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": data_url}
                        })
                    elif content_type.startswith("image/"):
                        data_url = await self.process_image_to_base64(image_data)
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": data_url}
                        })
                except Exception as e:
                    logger.error(f"Failed to process image: {e}")
        
        return user_content

    async def handle_tool_calls(
        self,
        ai_msg: Any,
        system_prompt: str,
        user_message: str,
        history: list[dict],
        send_status: Callable[[str], Awaitable[None]],
        context: dict | None = None,
    ) -> str:
        """
        Handle AI tool calls and return final response.
        
        Args:
            ai_msg: The AI response with tool_calls
            system_prompt: System prompt for follow-up
            user_message: Original user message
            history: Message history
            send_status: Async function to send status messages
            context: Additional context for error logging
            
        Returns:
            Final response text after tool execution
        """
        tool_call = ai_msg.tool_calls[0]
        func_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)
        
        # Send status message
        if func_name == "web_search":
            query = args.get("query", "something")
            await send_status(f"🔎 Searching for: *{query}*...")
        elif func_name == "calculator":
            expr = args.get("expression", "math")
            await send_status(f"🧮 Calculating: *{expr}*...")
        else:
            await send_status(f"🤖 Using tool: *{func_name}*...")
        
        # Execute tool
        try:
            tool_result = await tool_registry.execute(func_name, args)
        except Exception as e:
            tool_result = "Tool execution failed. Please try again."
            await db.log_error(e, {
                "context": "Tool Execution",
                "tool": func_name,
                "args": args,
                **(context or {})
            })
        
        # Add tool result to history and get final response
        context_injection = f"Tool Output for '{func_name}':\n{tool_result}"
        history_with_tool = history + [{"role": "system", "content": context_injection}]
        
        final_msg = await ai_service.generate_response(
            system_prompt=system_prompt,
            user_message=user_message,
            history=history_with_tool,
            tools=False  # Prevent infinite loops
        )
        
        return final_msg.content

    async def update_summary(
        self,
        channel_id: int,
        current_summary: str,
        messages: list[dict],
    ) -> None:
        """
        Update the conversation summary for a channel.
        
        Args:
            channel_id: The channel/chat ID
            current_summary: Existing summary content
            messages: New messages to summarize
        """
        try:
            if not messages:
                return
            
            # Format messages for the summarizer
            to_summarize = []
            for msg in messages:
                role = msg['role']
                content = msg['content']
                to_summarize.append(f"{role}: {content}")
            
            new_summary = await ai_service.summarize_conversation(current_summary, to_summarize)
            
            # The last message in the list is the newest one we just summarized
            last_msg_id = messages[-1].get('id', 0)
            
            await db.update_channel_summary(channel_id, new_summary, last_msg_id)
            logger.info(f"Updated summary for channel {channel_id} (up to msg {last_msg_id})")
            
        except Exception as e:
            logger.error(f"Failed to update summary: {e}")

    async def check_and_reset_persona(
        self,
        channel_id: int,
        guild_id: int,
        last_message_time: datetime,
        current_message_time: datetime,
    ) -> bool:
        """
        Check if persona should be reset due to time gap.
        
        Returns:
            True if persona was reset, False otherwise
        """
        if last_message_time:
            gap = (current_message_time - last_message_time).total_seconds()
            if gap > CONTEXT_RESET_THRESHOLD:
                async with db.conn.execute(
                    "SELECT id FROM personas WHERE name = 'Standard'"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        await db.conn.execute("""
                            INSERT INTO guild_configs (guild_id, active_persona_id) 
                            VALUES (?, ?)
                            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
                        """, (guild_id, row['id']))
                        await db.conn.commit()
                        return True
        return False


# Singleton instance
chat_service = ChatService()
