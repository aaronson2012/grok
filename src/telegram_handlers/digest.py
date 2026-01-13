import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ContextTypes

from ..services.db import db
from ..services.ai import ai_service
from ..services.search import search_service
from ..utils.chunker import chunk_text
from ..config import config

logger = logging.getLogger("grok.telegram.digest")


def is_admin(user_id: int) -> bool:
    return user_id in config.TELEGRAM_ADMIN_IDS


async def add_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_add <topic>")
        return

    topic = " ".join(context.args)[:100].strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await _ensure_user_settings(user_id, chat_id)

    async with db.conn.execute(
        "SELECT COUNT(*) FROM digest_topics WHERE user_id = ? AND guild_id = ?",
        (user_id, chat_id)
    ) as cursor:
        count = (await cursor.fetchone())[0]
        if count >= 10:
            await update.message.reply_text("❌ You can only have up to 10 topics.")
            return

    async with db.conn.execute(
        "SELECT 1 FROM digest_topics WHERE user_id = ? AND guild_id = ? AND topic = ? COLLATE NOCASE",
        (user_id, chat_id, topic)
    ) as cursor:
        if await cursor.fetchone():
            await update.message.reply_text(f"⚠️ You already have *{topic}* in your list.", parse_mode="Markdown")
            return

    await db.conn.execute(
        "INSERT INTO digest_topics (user_id, guild_id, topic) VALUES (?, ?, ?)",
        (user_id, chat_id, topic)
    )
    await db.conn.commit()
    await update.message.reply_text(f"✅ Added topic: *{topic}*", parse_mode="Markdown")


async def remove_topic_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_remove <topic>")
        return

    topic = " ".join(context.args)
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await db.conn.execute(
        "DELETE FROM digest_topics WHERE user_id = ? AND guild_id = ? AND topic = ?",
        (user_id, chat_id, topic)
    )
    await db.conn.commit()
    await update.message.reply_text(f"✅ Removed topic: *{topic}*", parse_mode="Markdown")


async def list_topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    async with db.conn.execute(
        "SELECT topic FROM digest_topics WHERE user_id = ? AND guild_id = ?",
        (user_id, chat_id)
    ) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("You have no topics set. Use /digest_add to get started.")
        return

    topics_list = "\n".join([f"• {row['topic']}" for row in rows])
    await update.message.reply_text(f"*Your Digest Topics:*\n{topics_list}", parse_mode="Markdown")


async def set_time_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_time <HH:MM> (e.g., 09:00)")
        return

    time_str = context.args[0]
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("❌ Invalid format. Please use HH:MM (e.g., 09:00 or 14:30).")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await _ensure_user_settings(user_id, chat_id)

    await db.conn.execute(
        "UPDATE user_digest_settings SET daily_time = ? WHERE user_id = ? AND guild_id = ?",
        (time_str, user_id, chat_id)
    )
    await db.conn.commit()

    await update.message.reply_text(f"✅ Daily digest time set to *{time_str}*.", parse_mode="Markdown")


async def set_timezone_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /digest_timezone <timezone> (e.g., UTC, America/New_York)")
        return

    timezone = context.args[0]
    try:
        ZoneInfo(timezone)
    except Exception:
        await update.message.reply_text("❌ Invalid timezone. Try 'UTC', 'America/New_York', 'Europe/London', etc.")
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await _ensure_user_settings(user_id, chat_id)

    await db.conn.execute(
        "UPDATE user_digest_settings SET timezone = ? WHERE user_id = ? AND guild_id = ?",
        (timezone, user_id, chat_id)
    )
    await db.conn.commit()

    await update.message.reply_text(f"✅ Timezone set to *{timezone}*.", parse_mode="Markdown")


async def trigger_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await update.message.reply_text("🔄 Generating your digest...")

    result = await send_digest(chat_id, user_id, context.bot)
    if result:
        await update.message.reply_text("✅ Digest sent!")
    else:
        await update.message.reply_text("❌ Could not send digest. Check if you have topics configured.")


async def _ensure_user_settings(user_id: int, chat_id: int):
    await db.conn.execute(
        "INSERT OR IGNORE INTO user_digest_settings (user_id, guild_id) VALUES (?, ?)",
        (user_id, chat_id)
    )
    await db.conn.commit()


async def send_digest(chat_id: int, user_id: int, bot) -> bool:
    try:
        async with db.conn.execute(
            "SELECT topic FROM digest_topics WHERE user_id = ? AND guild_id = ?",
            (user_id, chat_id)
        ) as cursor:
            raw_topics = [row["topic"] for row in await cursor.fetchall()]
            topics = sorted(list(set(raw_topics)), key=str.lower)

        if not topics:
            return False

        async with db.conn.execute(
            "SELECT timezone FROM user_digest_settings WHERE user_id = ? AND guild_id = ?",
            (user_id, chat_id)
        ) as cursor:
            row = await cursor.fetchone()
            timezone_str = row["timezone"] if row else "UTC"

        try:
            user_tz = ZoneInfo(timezone_str)
        except Exception:
            user_tz = ZoneInfo("UTC")

        now_user = datetime.now(user_tz)
        date_str = now_user.strftime("%Y-%m-%d")

        current_hour = now_user.hour
        if 5 <= current_hour < 12:
            greeting = "Good morning"
        elif 12 <= current_hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"

        await bot.send_message(
            chat_id=chat_id,
            text=f"📰 *{greeting}!* Here is your Daily Digest for {date_str}",
            parse_mode="Markdown"
        )

        for topic in topics:
            recent_headlines = await db.get_recent_digest_headlines(user_id, chat_id, topic)

            search_results = await search_service.search(f"{topic} news today", count=5)

            if "No results found" in search_results:
                await bot.send_message(chat_id=chat_id, text=f"*{topic}*\nNo recent news found.", parse_mode="Markdown")
                continue

            history_context = ""
            if recent_headlines:
                history_context = (
                    "\n\nPreviously reported stories (DO NOT repeat these):\n"
                    + "\n".join(f"- {h}" for h in recent_headlines[:20])
                )

            prompt = (
                f"Topic: {topic}\n"
                f"Search Results:\n{search_results}"
                f"{history_context}\n\n"
                "Task: Write a short, engaging summary of NEW news for this topic. "
                "Skip any stories similar to the previously reported ones. "
                "If ALL stories are repeats, respond with: NO_NEW_DEVELOPMENTS\n\n"
                "Otherwise, include 1-2 key links if available. "
                "Format with Markdown.\n\n"
                "At the end, list the headlines you covered in this format:\n"
                "HEADLINES_COVERED:\n- headline 1\n- headline 2"
            )

            ai_response = await ai_service.generate_response(
                system_prompt="You are a news anchor providing a daily digest. Jump straight into the news.",
                user_message=prompt
            )

            content = ai_response.content

            if "NO_NEW_DEVELOPMENTS" in content:
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"*{topic.title()}*\nNo new developments since the last update.",
                    parse_mode="Markdown"
                )
                continue

            display_content = content
            headlines_to_save = []

            if "HEADLINES_COVERED:" in display_content:
                parts = display_content.split("HEADLINES_COVERED:")
                display_content = parts[0].strip()
                if len(parts) > 1:
                    for line in parts[1].strip().split("\n"):
                        line = line.strip().lstrip("-").strip()
                        if line:
                            headlines_to_save.append(line)

            for headline in headlines_to_save:
                await db.save_digest_headline(user_id, chat_id, topic, headline)

            header = f"*{topic.title()}*\n"

            for chunk in chunk_text(display_content, chunk_size=3900):
                await bot.send_message(
                    chat_id=chat_id,
                    text=f"{header}{chunk}" if header else chunk,
                    parse_mode="Markdown"
                )
                header = ""

        await db.conn.execute(
            "UPDATE user_digest_settings SET last_sent_at = CURRENT_TIMESTAMP WHERE user_id = ? AND guild_id = ?",
            (user_id, chat_id)
        )
        await db.conn.commit()

        return True

    except Exception as e:
        logger.error(f"Failed to send digest to {user_id}: {e}")
        await db.log_error(e, {"context": "send_digest", "user_id": user_id})
        return False
