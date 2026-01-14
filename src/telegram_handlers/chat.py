import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from ..services.ai import ai_service
from ..services.db import db
from ..services.chat_service import chat_service
from ..types import ChatMessage
from ..utils.chunker import chunk_text
from ..utils.telegram_format import markdown_to_telegram_html
from ..utils.constants import Platform, SUMMARIZATION_THRESHOLD_TELEGRAM, TELEGRAM_CHUNK_SIZE

logger = logging.getLogger("grok.telegram.chat")

HELP_TEXT = r"""
*Grok Telegram Bot*

Talk to me by replying to my messages or mentioning me\!

*Commands:*
/start \- Start the bot
/help \- Show this help message
/chat \<prompt\> \- Chat with AI directly

*Admin Commands:*
/memory\_view \- View channel memory
/memory\_clear \- Clear channel memory
/logs\_view \- View error logs
/logs\_clear \- Clear error logs

*Persona Commands:*
/persona \- Switch persona
/persona\_create \<description\> \- Create new persona
/persona\_delete \- Delete a persona
/persona\_current \- Show current persona

*Digest Commands:*
/digest\_add \<topic\> \- Add a news topic
/digest\_remove \<topic\> \- Remove a topic
/digest\_list \- List your topics
/digest\_time \<HH:MM\> \- Set delivery time
/digest\_timezone \<tz\> \- Set timezone
/digest\_now \- Trigger digest now
"""


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! I'm Grok, your AI assistant. Reply to my messages or mention me to chat!\n\n"
        "Use /help to see available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(HELP_TEXT, parse_mode="MarkdownV2")


async def chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /chat <your message>")
        return

    prompt = " ".join(context.args)
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    system_prompt = await db.get_guild_persona(chat_id)
    user_message = f"[{user_id}]: {prompt}"

    ai_msg = await ai_service.generate_response(
        system_prompt=system_prompt,
        user_message=user_message
    )

    if ai_msg.tool_calls:
        async def send_status(text: str) -> None:
            await update.message.reply_text(text.replace("*", "_"), parse_mode="Markdown")
        
        response_text = await chat_service.handle_tool_calls(
            ai_msg=ai_msg,
            system_prompt=system_prompt,
            user_message=user_message,
            history=[],
            send_status=send_status,
            context={"chat_id": chat_id}
        )
    else:
        response_text = ai_msg.content

    for chunk in chunk_text(response_text, chunk_size=TELEGRAM_CHUNK_SIZE):
        html_chunk = markdown_to_telegram_html(chunk)
        await update.message.reply_text(html_chunk, parse_mode="HTML")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.text:
        return

    chat_id = message.chat_id
    user_id = message.from_user.id
    text = message.text

    if message.reply_to_message:
        if message.reply_to_message.from_user.id != context.bot.id:
            return

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    history = await _build_message_history(message, context)

    summary_data = await db.get_channel_summary(chat_id)
    current_summary = summary_data["content"] if summary_data else ""

    base_persona = await db.get_guild_persona(chat_id)

    system_prompt = await chat_service.build_system_prompt(
        base_persona=base_persona,
        platform=Platform.TELEGRAM,
        current_summary=current_summary
    )

    user_content = await _build_user_message_content(message, text, user_id)

    ai_msg = await ai_service.generate_response(
        system_prompt=system_prompt,
        user_message=user_content,
        history=history
    )

    if ai_msg.tool_calls:
        async def send_status(text: str) -> None:
            await update.message.reply_text(text.replace("*", "_"), parse_mode="Markdown")
        
        response_text = await chat_service.handle_tool_calls(
            ai_msg=ai_msg,
            system_prompt=system_prompt,
            user_message=f"[{user_id}]: {text}",
            history=history,
            send_status=send_status,
            context={"chat_id": chat_id}
        )
    else:
        response_text = ai_msg.content

    for chunk in chunk_text(response_text, chunk_size=TELEGRAM_CHUNK_SIZE):
        html_chunk = markdown_to_telegram_html(chunk)
        await message.reply_text(html_chunk, parse_mode="HTML")

    # Include current exchange for summarization
    current_exchange = [
        {"role": "user", "content": f"[{user_id}]: {text}", "id": message.message_id},
        {"role": "assistant", "content": response_text, "id": message.message_id},
    ]
    messages_to_check = history + current_exchange

    last_summarized_id = summary_data["last_msg_id"] if summary_data else 0
    unsummarized_msgs = [m for m in messages_to_check if m.get("id", 0) > last_summarized_id]

    if len(unsummarized_msgs) >= SUMMARIZATION_THRESHOLD_TELEGRAM:
        await chat_service.update_summary(chat_id, current_summary, unsummarized_msgs)


async def _build_message_history(message, context) -> list[dict]:
    """Build message history from reply chain using chat_service."""
    if not message.reply_to_message:
        return []

    messages = []
    current = message.reply_to_message
    last_msg_time = None

    for _ in range(300):
        if not current:
            break

        messages.append(ChatMessage(
            id=current.message_id,
            role="assistant" if current.from_user.id == context.bot.id else "user",
            content=current.text or "",
            author_id=current.from_user.id,
            timestamp=current.date
        ))

        current = current.reply_to_message

    return await chat_service.build_message_history(
        messages=messages,
        bot_id=context.bot.id
    )


async def _build_user_message_content(message, text: str, user_id: int) -> list[dict]:
    """Build multimodal user content using chat_service."""
    images = []
    
    if message.photo:
        try:
            photo = message.photo[-1]
            file = await photo.get_file()
            image_bytes = await file.download_as_bytearray()
            images.append((bytes(image_bytes), "image/jpeg"))
        except Exception as e:
            logger.error(f"Failed to process image: {e}")

    return await chat_service.build_user_content(
        text=text,
        user_id=user_id,
        images=images if images else None
    )
