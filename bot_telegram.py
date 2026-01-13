import sys
import logging
import asyncio
from telegram import BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from src.config import config
from src.services.db import db
from src.telegram_handlers import chat, admin, settings, digest

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("grok.telegram")


async def post_init(application: Application) -> None:
    await db.connect()
    logger.info("Database connected")
    
    # Register commands for autocomplete menu
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("help", "Show help message"),
        BotCommand("chat", "Chat with AI directly"),
        BotCommand("persona", "Switch persona"),
        BotCommand("persona_create", "Create new persona"),
        BotCommand("persona_delete", "Delete a persona"),
        BotCommand("persona_current", "Show current persona"),
        BotCommand("digest_add", "Add a news topic"),
        BotCommand("digest_remove", "Remove a topic"),
        BotCommand("digest_list", "List your topics"),
        BotCommand("digest_time", "Set delivery time"),
        BotCommand("digest_timezone", "Set timezone"),
        BotCommand("digest_now", "Trigger digest now"),
        BotCommand("memory_view", "View channel memory"),
        BotCommand("memory_clear", "Clear channel memory"),
        BotCommand("logs_view", "View error logs"),
        BotCommand("logs_clear", "Clear error logs"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered")
    
    # Register message handler here after bot is initialized
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & (filters.REPLY | filters.Mention(application.bot.username or "")),
        chat.handle_message
    ))


async def post_shutdown(application: Application) -> None:
    await db.close()
    logger.info("Database connection closed")


def main():
    try:
        config.validate_telegram()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)

    application = (
        Application.builder()
        .token(config.TELEGRAM_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    application.add_handler(CommandHandler("start", chat.start_command))
    application.add_handler(CommandHandler("help", chat.help_command))
    application.add_handler(CommandHandler("chat", chat.chat_command))

    application.add_handler(CommandHandler("memory_view", admin.memory_view_command))
    application.add_handler(CommandHandler("memory_clear", admin.memory_clear_command))
    application.add_handler(CommandHandler("logs_view", admin.logs_view_command))
    application.add_handler(CommandHandler("logs_clear", admin.logs_clear_command))

    application.add_handler(CommandHandler("persona", settings.persona_command))
    application.add_handler(CommandHandler("persona_create", settings.persona_create_command))
    application.add_handler(CommandHandler("persona_delete", settings.persona_delete_command))
    application.add_handler(CommandHandler("persona_current", settings.persona_current_command))
    application.add_handler(CallbackQueryHandler(settings.persona_callback, pattern=r"^persona_"))
    application.add_handler(CallbackQueryHandler(settings.persona_delete_callback, pattern=r"^delete_persona_"))

    application.add_handler(CommandHandler("digest_add", digest.add_topic_command))
    application.add_handler(CommandHandler("digest_remove", digest.remove_topic_command))
    application.add_handler(CommandHandler("digest_list", digest.list_topics_command))
    application.add_handler(CommandHandler("digest_time", digest.set_time_command))
    application.add_handler(CommandHandler("digest_timezone", digest.set_timezone_command))
    application.add_handler(CommandHandler("digest_now", digest.trigger_now_command))

    application.add_error_handler(error_handler)

    logger.info("Starting Telegram bot...")
    application.run_polling(allowed_updates=["message", "callback_query"])


async def error_handler(update, context):
    logger.error(f"Exception while handling an update: {context.error}")
    await db.log_error(context.error, {"context": "Telegram error_handler", "update": str(update)})


if __name__ == "__main__":
    main()
