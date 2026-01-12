import discord
from discord.ext import commands
from typing import override
import logging
from ..services.db import db
from ..services.ai import ai_service
from ..services.emoji_manager import emoji_manager

logger = logging.getLogger("grok.settings")

class PersonaSelect(discord.ui.Select):
    def __init__(self, personas):
        options = []
        for p in personas:
            # Truncate description to 100 chars
            desc = (p['description'][:97] + '...') if len(p['description']) > 100 else p['description']
            options.append(discord.SelectOption(
                label=p['name'],
                description=desc,
                value=str(p['id'])
            ))
        super().__init__(placeholder="Select a persona...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        persona_id = int(self.values[0])
        # Find name for response
        name = next(opt.label for opt in self.options if opt.value == self.values[0])
        
        await db.conn.execute("""
            INSERT INTO guild_configs (guild_id, active_persona_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
        """, (interaction.guild.id, persona_id))
        await db.conn.commit()
        
        await interaction.response.send_message(f"✅ Switched persona to **{name}**!", ephemeral=False)

class PersonaModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Create New Persona")
        self.add_item(discord.ui.InputText(
            label="Describe the Persona",
            placeholder="e.g. A sarcastic 1990s hacker who loves coffee...",
            style=discord.InputTextStyle.paragraph,
            min_length=10,
            max_length=1000
        ))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_input = self.children[0].value
        
        try:
            # Generate Name and Prompt in one go
            ai_prompt = (
                f"Based on this description: '{user_input}', generate:\n"
                "1. A short, unique name (max 15 chars, no spaces).\n"
                "2. A system prompt (2-3 sentences) for a Discord bot.\n"
                "Format output strictly as: NAME: <name>\nPROMPT: <prompt>"
            )
            
            ai_msg = await ai_service.generate_response(
                system_prompt="You are a configuration generator.",
                user_message=ai_prompt
            )
            
            # Parse output
            content = ai_msg.content.strip()
            name = "Unknown"
            prompt = "You are a helpful assistant."
            
            for line in content.split('\n'):
                if line.startswith("NAME:"):
                    name = line.replace("NAME:", "").strip()
                elif line.startswith("PROMPT:"):
                    prompt = line.replace("PROMPT:", "").strip()
            
            # Fallback if parsing fails
            if name == "Unknown":
                name = user_input.split()[0][:15]
            
            # Check uniqueness
            async with db.conn.execute("SELECT 1 FROM personas WHERE name = ? COLLATE NOCASE", (name,)) as cursor:
                if await cursor.fetchone():
                    name = f"{name}_{interaction.user.discriminator}" # collision fallback

            await db.conn.execute("""
                INSERT INTO personas (name, description, system_prompt, is_global, created_by)
                VALUES (?, ?, ?, 0, ?)
            """, (name, user_input, prompt, interaction.user.id))
            await db.conn.commit()
            
            embed = discord.Embed(title="✨ Persona Created", color=discord.Color.green())
            embed.add_field(name="Name", value=name, inline=True)
            embed.add_field(name="Description", value=user_input, inline=False)
            embed.add_field(name="System Prompt", value=prompt, inline=False)
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Creation failed: {e}")

class PersonaView(discord.ui.View):
    def __init__(self, personas):
        super().__init__()
        self.add_item(PersonaSelect(personas))

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    persona = discord.SlashCommandGroup("persona", "Manage Grok's personality")

    @persona.command(name="switch", description="Switch the server's active persona")
    @discord.default_permissions(administrator=True)
    async def switch_persona(self, ctx: discord.ApplicationContext):
        # Fetch available personas
        async with db.conn.execute("SELECT id, name, description FROM personas ORDER BY name") as cursor:
            personas = await cursor.fetchall()
            
        if not personas:
            await ctx.respond("No personas found!", ephemeral=True)
            return

        view = PersonaView(personas)
        await ctx.respond("🎭 **Choose a Persona**:", view=view)

    @persona.command(name="create", description="Create a new custom persona")
    @discord.default_permissions(administrator=True)
    async def create_persona(self, ctx: discord.ApplicationContext):
        modal = PersonaModal()
        await ctx.send_modal(modal)

    @persona.command(name="delete", description="Delete a custom persona")
    @discord.default_permissions(administrator=True)
    async def delete_persona(self, ctx: discord.ApplicationContext, name: str):
        # Prevent deleting Standard
        if name.lower() == "standard":
            await ctx.respond("❌ You cannot delete the default 'Standard' persona.", ephemeral=True)
            return

        async with db.conn.execute("SELECT id FROM personas WHERE name = ? COLLATE NOCASE", (name,)) as cursor:
            row = await cursor.fetchone()
        
        if not row:
            await ctx.respond(f"❌ Persona '{name}' not found.", ephemeral=True)
            return
            
        await db.conn.execute("DELETE FROM personas WHERE id = ?", (row['id'],))
        await db.conn.commit()
        
        await ctx.respond(f"🗑️ Deleted persona **{name}**.")

    @persona.command(name="current", description="Show the current active persona")
    async def current_persona(self, ctx: discord.ApplicationContext):
        query = """
        SELECT p.name, p.description 
        FROM guild_configs g
        JOIN personas p ON g.active_persona_id = p.id
        WHERE g.guild_id = ?
        """
        async with db.conn.execute(query, (ctx.guild.id,)) as cursor:
            row = await cursor.fetchone()
        
        if row:
            await ctx.respond(f"🎭 Current Persona: **{row['name']}**\n*{row['description']}*")
        else:
            await ctx.respond("🎭 Current Persona: **Standard** (Default)")

    @discord.slash_command(name="analyze_emojis", description="Force re-analyze server emojis")
    @discord.default_permissions(administrator=True)
    async def analyze_emojis(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        try:
            count = await emoji_manager.analyze_guild_emojis(ctx.guild)
            await ctx.followup.send(f"✅ Analysis complete! Processed **{count}** new/updated emojis.")
        except Exception as e:
            await ctx.followup.send(f"❌ Analysis failed: {e}")

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Settings(bot))
