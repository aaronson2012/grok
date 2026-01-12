import discord
from discord.ext import commands
from typing import override
import logging
from ..services.db import db
from ..services.emoji_manager import emoji_manager

logger = logging.getLogger("grok.settings")

class Settings(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    persona = discord.SlashCommandGroup("persona", "Manage Grok's personality")

    @persona.command(name="list", description="List available personas")
    async def list_personas(self, ctx: discord.ApplicationContext):
        # Fetch global personas + custom personas created by this guild (if implemented later)
        # For now, just global
        async with db.conn.execute("SELECT id, name, description FROM personas WHERE is_global = 1") as cursor:
            personas = await cursor.fetchall()
        
        embed = discord.Embed(title="🎭 Available Personas", color=discord.Color.blue())
        for p in personas:
            embed.add_field(name=f"{p['name']} (ID: {p['id']})", value=p['description'], inline=False)
        
        await ctx.respond(embed=embed)

    @persona.command(name="switch", description="Switch the server's active persona")
    @discord.default_permissions(administrator=True)
    async def switch_persona(self, ctx: discord.ApplicationContext, name: str):
        # Find persona by name
        async with db.conn.execute("SELECT id FROM personas WHERE name = ? COLLATE NOCASE", (name,)) as cursor:
            row = await cursor.fetchone()
        
        if not row:
            await ctx.respond(f"❌ Persona '{name}' not found. Use `/persona list` to see available options.", ephemeral=True)
            return

        persona_id = row['id']
        
        # Upsert into guild_configs
        await db.conn.execute("""
            INSERT INTO guild_configs (guild_id, active_persona_id) 
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET active_persona_id = excluded.active_persona_id
        """, (ctx.guild.id, persona_id))
        await db.conn.commit()
        
        await ctx.respond(f"✅ Switched persona to **{name}**!")

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

    @persona.command(name="analyze_emojis", description="Force re-analyze server emojis")
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
