import discord
from discord.ext import commands
from typing import override
import logging
from ..services.db import db
from ..services.ai import ai_service
from ..services.emoji_manager import emoji_manager

logger = logging.getLogger("grok.settings")

class PersonaSelect(discord.ui.Select):
    def __init__(self, personas, author_id):
        self.author_id = author_id
        options = []
        for p in personas:
            desc = (p['description'][:97] + '...') if len(p['description']) > 100 else p['description']
            options.append(discord.SelectOption(
                label=p['name'],
                description=desc,
                value=str(p['id'])
            ))
        super().__init__(placeholder="Select a persona...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ You cannot control this menu.", ephemeral=True)
            return

        persona_id = int(self.values[0])
        name = next(opt.label for opt in self.options if opt.value == self.values[0])
        
        await db.conn.execute("""
            INSERT INTO guild_configs (guild_id, active_persona_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
        """, (interaction.guild.id, persona_id))
        await db.conn.commit()
        
        await interaction.response.send_message(f"✅ Switched persona to **{name}**!", ephemeral=False)

class PersonaView(discord.ui.View):
    def __init__(self, personas, author_id):
        super().__init__()
        self.add_item(PersonaSelect(personas, author_id))

class PersonaDeleteSelect(discord.ui.Select):
    def __init__(self, personas, author_id):
        self.author_id = author_id
        options = []
        for p in personas:
            options.append(discord.SelectOption(
                label=p['name'],
                description=f"ID: {p['id']}",
                value=str(p['id'])
            ))
        super().__init__(placeholder="Select a persona to DELETE...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ You cannot control this menu.", ephemeral=True)
            return

        persona_id = int(self.values[0])
        name = next(opt.label for opt in self.options if opt.value == self.values[0])
        
        await db.conn.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
        await db.conn.commit()
        
        self.disabled = True
        await interaction.response.edit_message(content=f"🗑️ Deleted persona **{name}**.", view=self.view)

class PersonaDeleteView(discord.ui.View):
    def __init__(self, personas, author_id):
        super().__init__()
        self.add_item(PersonaDeleteSelect(personas, author_id))


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
            await ctx.respond("No personas found!", ephemeral=False)
            return

        view = PersonaView(personas, ctx.author.id)
        await ctx.respond("🎭 **Choose a Persona**:", view=view)

    @persona.command(name="create", description="Create a new custom persona with AI assistance")
    @discord.default_permissions(administrator=True)
    async def create_persona(self, ctx: discord.ApplicationContext):
        modal = PersonaModal()
        await ctx.send_modal(modal)

    @persona.command(name="delete", description="Delete a custom persona")
    @discord.default_permissions(administrator=True)
    async def delete_persona(self, ctx: discord.ApplicationContext):
        # Fetch deletable personas (exclude Standard and globals if preferred, 
        # but for now assume admins can delete anything except 'Standard')
        async with db.conn.execute("SELECT id, name FROM personas WHERE name != 'Standard' ORDER BY name") as cursor:
            personas = await cursor.fetchall()
            
        if not personas:
            await ctx.respond("No custom personas found to delete.", ephemeral=False)
            return

        view = PersonaDeleteView(personas, ctx.author.id)
        await ctx.respond("🗑️ **Select a Persona to Delete**:", view=view, ephemeral=False)


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
