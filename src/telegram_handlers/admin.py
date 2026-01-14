import logging
from telegram import Update
from telegram.ext import ContextTypes

from ..services.admin_service import admin_service
from ..utils.permissions import require_telegram_admin

logger = logging.getLogger("grok.telegram.admin")


@require_telegram_admin
async def memory_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    summary = await admin_service.get_channel_summary(chat_id)

    if not summary:
        await update.message.reply_text("🧠 No memory stored for this chat.")
        return

    content = summary["content"]
    if len(content) > 3500:
        content = content[:3497] + "..."

    await update.message.reply_text(
        f"🧠 *Memory for this chat:*\n\n{content}\n\n_Last updated: {summary['updated_at']}_",
        parse_mode="Markdown"
    )


@require_telegram_admin
async def memory_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    await admin_service.clear_channel_summary(chat_id)

    await update.message.reply_text("🧹 Memory cleared for this chat.")


@require_telegram_admin
async def logs_view_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    limit = 5
    if context.args:
        try:
            limit = min(max(int(context.args[0]), 1), 20)
        except ValueError:
            pass

    rows = await admin_service.get_recent_errors(limit)

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


@require_telegram_admin
async def logs_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await admin_service.clear_all_errors()

    await update.message.reply_text("🔥 All error logs have been cleared.")
