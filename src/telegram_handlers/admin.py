import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..services.db import db
from ..config import config

logger = logging.getLogger("grok.telegram.admin")


def is_admin(user_id: int) -> bool:
    return user_id in config.TELEGRAM_ADMIN_IDS


async def memory_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    chat_id = update.effective_chat.id

    async with db.conn.execute(
        "SELECT content, updated_at FROM summaries WHERE channel_id = ?",
        (chat_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if not row:
        await update.message.reply_text("🧠 No memory stored for this chat.")
        return

    content = row["content"]
    if len(content) > 3500:
        content = content[:3497] + "..."

    await update.message.reply_text(
        f"🧠 *Memory for this chat:*\n\n{content}\n\n_Last updated: {row['updated_at']}_",
        parse_mode="Markdown"
    )


async def memory_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    chat_id = update.effective_chat.id

    await db.conn.execute("DELETE FROM summaries WHERE channel_id = ?", (chat_id,))
    await db.conn.commit()

    await update.message.reply_text("🧹 Memory cleared for this chat.")


async def logs_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    limit = 5
    if context.args:
        try:
            limit = min(max(int(context.args[0]), 1), 20)
        except ValueError:
            pass

    async with db.conn.execute(
        "SELECT id, error_type, message, created_at FROM error_logs ORDER BY id DESC LIMIT ?",
        (limit,)
    ) as cursor:
        rows = await cursor.fetchall()

    if not rows:
        await update.message.reply_text("✅ No errors logged.")
        return

    lines = [f"📋 *Recent Error Logs (Last {len(rows)}):*\n"]
    for row in rows:
        lines.append(
            f"\n*Error #{row['id']}*\n"
            f"Type: `{row['error_type']}`\n"
            f"Msg: {row['message'][:100]}\n"
            f"Time: {row['created_at']}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def logs_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    await db.conn.execute("DELETE FROM error_logs")
    await db.conn.commit()

    await update.message.reply_text("🔥 All error logs have been cleared.")
