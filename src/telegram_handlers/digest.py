import logging
from datetime import datetime
from telegram import Bot, Update
from telegram.ext import ContextTypes

from ..services.db import db
from ..services.digest_service import digest_service
from ..utils.chunker import chunk_text
from ..utils.constants import TELEGRAM_CHUNK_SIZE

logger = logging.getLogger("grok.telegram.digest")


async def add_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_add <topic>")
        return

    topic = " ".join(context.args)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    success, message = await digest_service.add_topic(user_id, chat_id, topic)
    await update.message.reply_text(
        f"{'✅' if success else '❌'} {message}",
        parse_mode="Markdown"
    )


async def remove_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_remove <topic>")
        return

    topic = " ".join(context.args)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await digest_service.remove_topic(user_id, chat_id, topic)
    await update.message.reply_text(f"✅ Removed topic: *{topic}*", parse_mode="Markdown")


async def list_topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    topics = await digest_service.get_user_topics(user_id, chat_id)

    if not topics:
        await update.message.reply_text("You have no topics set. Use /digest_add to get started.")
        return

    topics_list = "\n".join([f"• {topic}" for topic in topics])
    await update.message.reply_text(f"*Your Digest Topics:*\n{topics_list}", parse_mode="Markdown")


async def set_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_time <HH:MM> (e.g., 09:00)")
        return

    time_str = context.args[0]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    success, message = await digest_service.set_daily_time(user_id, chat_id, time_str)
    await update.message.reply_text(
        f"{'✅' if success else '❌'} {message}",
        parse_mode="Markdown"
    )


async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_timezone <timezone> (e.g., UTC, America/New_York)")
        return

    timezone = context.args[0]
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    success, message = await digest_service.set_timezone(user_id, chat_id, timezone)
    await update.message.reply_text(
        f"{'✅' if success else '❌'} {message}",
        parse_mode="Markdown"
    )


async def trigger_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await update.message.reply_text("🔄 Generating your digest...")

    result = await send_digest(chat_id, user_id, context.bot)
    if result:
        await update.message.reply_text("✅ Digest sent!")
    else:
        await update.message.reply_text("❌ Could not send digest. Check if you have topics configured.")


async def send_digest(chat_id: int, user_id: int, bot: Bot) -> bool:
    """Generates and sends the digest for Telegram."""
    try:
        topics = await digest_service.get_prepared_topics(user_id, chat_id)

        if not topics:
            return False

        timezone_str = await digest_service.get_user_timezone(user_id, chat_id)
        user_tz = digest_service.get_user_timezone_safe(timezone_str)

        now_user = datetime.now(user_tz)
        date_str = now_user.strftime("%Y-%m-%d")

        greeting = digest_service.get_greeting(now_user.hour)

        await bot.send_message(
            chat_id=chat_id,
            text=f"📰 *{greeting}!* Here is your Daily Digest for {date_str}",
            parse_mode="Markdown"
        )

        for topic in topics:
            section_title, content = await digest_service.generate_topic_digest(user_id, chat_id, topic)
            
            header = f"*{section_title}*\n"

            for i, chunk in enumerate(chunk_text(content, chunk_size=TELEGRAM_CHUNK_SIZE)):
                text = f"{header}{chunk}" if i == 0 else chunk
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode="Markdown"
                )

        await digest_service.mark_digest_sent(user_id, chat_id)

        return True

    except Exception as e:
        logger.error(f"Failed to send digest to {user_id}: {e}")
        await db.log_error(e, {"context": "send_digest", "user_id": user_id})
        return False
