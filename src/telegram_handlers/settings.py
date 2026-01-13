import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from ..services.db import db
from ..services.ai import ai_service
from ..config import config

logger = logging.getLogger("grok.telegram.settings")


def is_admin(user_id: int) -> bool:
    return user_id in config.TELEGRAM_ADMIN_IDS


async def persona_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    async with db.conn.execute(
        "SELECT id, name, description FROM personas ORDER BY name"
    ) as cursor:
        personas = await cursor.fetchall()

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

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ You cannot control this menu.")
        return

    persona_id = int(query.data.replace("persona_", ""))
    chat_id = query.message.chat_id

    async with db.conn.execute("SELECT name FROM personas WHERE id = ?", (persona_id,)) as cursor:
        row = await cursor.fetchone()
        name = row["name"] if row else "Unknown"

    await db.conn.execute(
        """
        INSERT INTO guild_configs (guild_id, active_persona_id)
        VALUES (?, ?)
        ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
        """,
        (chat_id, persona_id)
    )
    await db.conn.commit()

    await query.edit_message_text(f"✅ Switched persona to *{name}*!", parse_mode="Markdown")


async def persona_create_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /persona_create <description>\nExample: /persona_create A sarcastic hacker")
        return

    user_input = " ".join(context.args)

    await update.message.reply_text("🔄 Creating persona...")

    try:
        ai_prompt = (
            f"User Input: '{user_input}'\n\n"
            "Task: Create a Discord bot persona based on this input.\n"
            "Output strictly in this format:\n"
            "NAME: <The direct character name or simple title. Max 15 chars. No spaces.>\n"
            "DESCRIPTION: <A short 1-sentence summary of who this is>\n"
            "PROMPT: <A 2-3 sentence system instruction. Start with 'You are...'>"
        )

        ai_msg = await ai_service.generate_response(
            system_prompt="You are a configuration generator.",
            user_message=ai_prompt
        )

        content = ai_msg.content.strip()
        name = "Unknown"
        description = "Custom Persona"
        prompt = "You are a helpful assistant."

        for line in content.split("\n"):
            if line.startswith("NAME:"):
                name = line.replace("NAME:", "").strip()[:50]
            elif line.startswith("DESCRIPTION:"):
                description = line.replace("DESCRIPTION:", "").strip()[:200]
            elif line.startswith("PROMPT:"):
                prompt = line.replace("PROMPT:", "").strip()

        if name == "Unknown":
            name = user_input.split()[0][:15]
            description = user_input[:50]

        async with db.conn.execute(
            "SELECT 1 FROM personas WHERE name = ? COLLATE NOCASE", (name,)
        ) as cursor:
            if await cursor.fetchone():
                name = f"{name}_{update.effective_user.id % 10000}"

        await db.conn.execute(
            """
            INSERT INTO personas (name, description, system_prompt, is_global, created_by)
            VALUES (?, ?, ?, 0, ?)
            """,
            (name, description, prompt, update.effective_user.id)
        )
        await db.conn.commit()

        await update.message.reply_text(
            f"✨ *Persona Created*\n\n"
            f"*Name:* {name}\n"
            f"*Description:* {description}\n"
            f"*System Prompt:* {prompt}",
            parse_mode="Markdown"
        )

    except Exception as e:
        logger.error(f"Persona creation failed: {e}")
        await update.message.reply_text("❌ Creation failed. Please try again.")


async def persona_delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ This command requires admin permissions.")
        return

    async with db.conn.execute(
        "SELECT id, name, description FROM personas WHERE name != 'Standard' ORDER BY name"
    ) as cursor:
        personas = await cursor.fetchall()

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

    if not is_admin(query.from_user.id):
        await query.edit_message_text("❌ You cannot control this menu.")
        return

    persona_id = int(query.data.replace("delete_persona_", ""))

    async with db.conn.execute("SELECT name FROM personas WHERE id = ?", (persona_id,)) as cursor:
        row = await cursor.fetchone()
        name = row["name"] if row else "Unknown"

    await db.conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
    await db.conn.commit()

    await query.edit_message_text(f"🗑️ Deleted persona *{name}*.", parse_mode="Markdown")


async def persona_current_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id

    query = """
    SELECT p.name, p.description
    FROM guild_configs g
    JOIN personas p ON g.active_persona_id = p.id
    WHERE g.guild_id = ?
    """
    async with db.conn.execute(query, (chat_id,)) as cursor:
        row = await cursor.fetchone()

    if row:
        await update.message.reply_text(
            f"🎭 Current Persona: *{row['name']}*\n_{row['description']}_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("🎭 Current Persona: *Standard* (Default)", parse_mode="Markdown")
