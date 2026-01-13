import logging
import json
import base64
import io
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from PIL import Image

from ..services.ai import ai_service
from ..services.db import db
from ..services.tools import tool_registry
from ..utils.chunker import chunk_text

logger = logging.getLogger("grok.telegram.chat")

HELP_TEXT = r"""
*Grok Telegram Bot*

Talk to me by replying to my messages or mentioning me\!

*Commands:*
/start \- Start the bot
/help \- Show this help message
/chat <prompt> \- Chat with AI directly

*Admin Commands:*
/memory\_view \- View channel memory
/memory\_clear \- Clear channel memory
/logs\_view \- View error logs
/logs\_clear \- Clear error logs

*Persona Commands:*
/persona \- Switch persona
/persona\_create <description> \- Create new persona
/persona\_delete \- Delete a persona
/persona\_current \- Show current persona

*Digest Commands:*
/digest\_add <topic> \- Add a news topic
/digest\_remove <topic> \- Remove a topic
/digest\_list \- List your topics
/digest\_time <HH:MM> \- Set delivery time
/digest\_timezone <tz> \- Set timezone
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
        response_text = await _handle_tool_calls(ai_msg, system_prompt, user_message, update)
    else:
        response_text = ai_msg.content

    for chunk in chunk_text(response_text, chunk_size=4000):
        await update.message.reply_text(chunk)


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

    current_date = datetime.now().strftime("%Y-%m-%d")
    memory_block = f"\n[PREVIOUS CONVERSATION SUMMARY]:\n{current_summary}\n" if current_summary else ""

    system_prompt = (
        f"Current Date: {current_date}\n{base_persona}\n{memory_block}\n"
        "INSTRUCTION: Focus primarily on the user's latest message. "
        "Use the chat history ONLY for context if relevant. "
        "If the latest request is unrelated to previous messages, treat it as a new topic. "
        "Users are identified by [User ID] at the start of their messages. "
        "IMPORTANT: Keep your response concise and under 3900 characters to fit in a Telegram message."
    )

    user_content = await _build_user_message_content(message, text, user_id)

    ai_msg = await ai_service.generate_response(
        system_prompt=system_prompt,
        user_message=user_content,
        history=history
    )

    if ai_msg.tool_calls:
        response_text = await _handle_tool_calls(ai_msg, system_prompt, f"[{user_id}]: {text}", update, history)
    else:
        response_text = ai_msg.content

    for chunk in chunk_text(response_text, chunk_size=4000):
        await message.reply_text(chunk)

    if summary_data:
        last_summarized_id = summary_data.get("last_msg_id", 0)
        unsummarized_msgs = [m for m in history if m.get("id", 0) > last_summarized_id]

        if len(unsummarized_msgs) >= 10:
            await _update_summary(chat_id, current_summary, unsummarized_msgs)


async def _build_message_history(message, context) -> list[dict]:
    history = []
    last_msg_time = None

    if not message.reply_to_message:
        return history

    reply_chain = []
    current = message.reply_to_message

    for _ in range(20):
        if not current:
            break

        if last_msg_time:
            time_diff = (last_msg_time - current.date).total_seconds()
            if time_diff > 3600:
                break

        last_msg_time = current.date

        if current.from_user.id == context.bot.id:
            role = "assistant"
            content = current.text or ""
        else:
            role = "user"
            content = f"[{current.from_user.id}]: {current.text or ''}"

        if content:
            reply_chain.append({"role": role, "content": content, "id": current.message_id})

        current = current.reply_to_message

    history = list(reversed(reply_chain))
    return history


async def _build_user_message_content(message, text: str, user_id: int) -> list[dict]:
    user_content = [{"type": "text", "text": f"[{user_id}]: {text}"}]

    if message.photo:
        try:
            photo = message.photo[-1]
            file = await photo.get_file()
            image_bytes = await file.download_as_bytearray()

            with Image.open(io.BytesIO(image_bytes)) as img:
                output_buffer = io.BytesIO()
                img.convert("RGB").save(output_buffer, format="JPEG")
                output_buffer.seek(0)

                base64_image = base64.b64encode(output_buffer.getvalue()).decode("utf-8")
                data_url = f"data:image/jpeg;base64,{base64_image}"

                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": data_url}
                })
        except Exception as e:
            logger.error(f"Failed to process image: {e}")

    return user_content


async def _handle_tool_calls(ai_msg, system_prompt: str, user_message: str, update: Update, history: list = None) -> str:
    tool_call = ai_msg.tool_calls[0]
    func_name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    if func_name == "web_search":
        query = args.get("query", "something")
        await update.message.reply_text(f"🔎 Searching for: _{query}_...", parse_mode="Markdown")
    elif func_name == "calculator":
        expr = args.get("expression", "math")
        await update.message.reply_text(f"🧮 Calculating: _{expr}_...", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"🤖 Using tool: _{func_name}_...", parse_mode="Markdown")

    try:
        tool_result = await tool_registry.execute(func_name, args)
    except Exception as e:
        tool_result = "Tool execution failed. Please try again."
        await db.log_error(e, {
            "context": "Tool Execution",
            "tool": func_name,
            "args": args,
            "chat_id": update.effective_chat.id
        })

    if history is None:
        history = []

    context_injection = f"Tool Output for '{func_name}':\n{tool_result}"
    history.append({"role": "system", "content": context_injection})

    final_msg = await ai_service.generate_response(
        system_prompt=system_prompt,
        user_message=user_message,
        history=history,
        tools=False
    )

    return final_msg.content


async def _update_summary(chat_id: int, current_summary: str, messages: list):
    try:
        if not messages:
            return

        to_summarize = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            to_summarize.append(f"{role}: {content}")

        new_summary = await ai_service.summarize_conversation(current_summary, to_summarize)
        last_msg_id = messages[-1]["id"]

        await db.update_channel_summary(chat_id, new_summary, last_msg_id)
        logger.info(f"Updated summary for chat {chat_id} (up to msg {last_msg_id})")

    except Exception as e:
        logger.error(f"Failed to update summary: {e}")
