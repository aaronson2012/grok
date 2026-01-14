import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..services.persona_service import persona_service
from ..utils.permissions import is_telegram_admin, require_telegram_admin

logger = logging.getLogger("grok.telegram.settings")


@require_telegram_admin
async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    personas = await persona_service.get_all_personas()

    if not personas:
        await update.message.reply_text("No personas found!")
        return

    keyboard = []
    for p in personas:
        desc = p["description"][:30] + "..." if len(p["description"]) > 30 else p["description"]
        keyboard.append([InlineKeyboardButton(
            f"{p['name']} - {desc}",
            callback_data=f"persona_{p['id']}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🎭 *Choose a Persona:*", reply_markup=reply_markup, parse_mode="Markdown")


async def persona_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not is_telegram_admin(query.from_user.id):
        await query.edit_message_text("❌ You cannot control this menu.")
        return

    persona_id = int(query.data.replace("persona_", ""))
    chat_id = query.message.chat_id

    name = await persona_service.get_persona_name(persona_id)
    await persona_service.set_guild_persona(chat_id, persona_id)

    await query.edit_message_text(f"✅ Switched persona to *{name}*!", parse_mode="Markdown")


@require_telegram_admin
async def persona_create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /persona_create <description>\nExample: /persona_create A sarcastic hacker")
        return

    user_input = " ".join(context.args)

    await update.message.reply_text("🔄 Creating persona...")

    success, result = await persona_service.create_persona(
        user_input=user_input,
        created_by=update.effective_user.id,
        collision_suffix=str(update.effective_user.id % 10000)
    )

    if success:
        await update.message.reply_text(
            f"✨ *Persona Created*\n\n"
            f"*Name:* {result['name']}\n"
            f"*Description:* {result['description']}\n"
            f"*System Prompt:* {result['system_prompt']}",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(f"❌ {result}")


@require_telegram_admin
async def persona_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    personas = await persona_service.get_deletable_personas()

    if not personas:
        await update.message.reply_text("No custom personas found to delete.")
        return

    keyboard = []
    for p in personas:
        keyboard.append([InlineKeyboardButton(
            f"🗑️ {p['name']}",
            callback_data=f"delete_persona_{p['id']}"
        )])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🗑️ *Select a Persona to Delete:*",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )


async def persona_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if not is_telegram_admin(query.from_user.id):
        await query.edit_message_text("❌ You cannot control this menu.")
        return

    persona_id = int(query.data.replace("delete_persona_", ""))
    name = await persona_service.delete_persona(persona_id)

    await query.edit_message_text(f"🗑️ Deleted persona *{name}*.", parse_mode="Markdown")


async def persona_current_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    row = await persona_service.get_current_persona(chat_id)

    if row:
        await update.message.reply_text(
            f"🎭 Current Persona: *{row['name']}*\n_{row['description']}_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🎭 Current Persona: *Standard* (Default)", parse_mode="Markdown")
