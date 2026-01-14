import discord
from discord.ext import commands
from typing import override
import logging
import aiofiles
import tempfile
import os
from ..services.admin_service import admin_service
from ..utils.constants import DISCORD_EMBED_FIELD_LIMIT

logger = logging.getLogger("grok.admin")

class Admin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    # Create a slash command group for admin tools
    admin = discord.SlashCommandGroup("admin", "Administrative and debugging tools")

    # --- Memory Management ---
    
    memory = admin.create_subgroup("memory", "Manage AI memory and context")

    @memory.command(name="view", description="View the current long-term memory for a channel")
    @discord.default_permissions(administrator=True)
    async def memory_view(self, ctx: discord.ApplicationContext, channel: discord.TextChannel = None):
        await ctx.defer(ephemeral=True)
        target_channel = channel or ctx.channel
        
        summary = await admin_service.get_channel_summary(target_channel.id)
            
        if not summary:
            await ctx.respond(f"🧠 No memory stored for {target_channel.mention}.", ephemeral=True)
            return
            
        embed = discord.Embed(title=f"🧠 Memory for #{target_channel.name}", color=discord.Color.blue())
        content = summary['content']
        if len(content) > DISCORD_EMBED_FIELD_LIMIT:
            content = content[:DISCORD_EMBED_FIELD_LIMIT - 3] + "..."
            
        embed.add_field(name="Summary", value=content, inline=False)
        embed.set_footer(text=f"Last updated: {summary['updated_at']}")
        
        await ctx.respond(embed=embed, ephemeral=True)

    @memory.command(name="clear", description="Clear the long-term memory for a channel")
    @discord.default_permissions(administrator=True)
    async def memory_clear(self, ctx: discord.ApplicationContext, channel: discord.TextChannel = None):
        await ctx.defer(ephemeral=True)
        target_channel = channel or ctx.channel
        
        await admin_service.clear_channel_summary(target_channel.id)
        
        await ctx.respond(f"🧹 Memory cleared for {target_channel.mention}.", ephemeral=True)

    # --- Error Logging ---
    
    logs = admin.create_subgroup("logs", "Inspect and manage error logs")

    @logs.command(name="view", description="View recent error logs")
    @discord.default_permissions(administrator=True)
    async def logs_view(self, ctx: discord.ApplicationContext, limit: int = 5):
        await ctx.defer(ephemeral=True)
        if limit < 1 or limit > 20:
            limit = 5
            
        rows = await admin_service.get_recent_errors(limit)
            
        if not rows:
            await ctx.respond("✅ No errors logged.", ephemeral=True)
            return
            
        embed = discord.Embed(title=f"📋 Recent Error Logs (Last {len(rows)})", color=discord.Color.red())
        
        for row in rows:
            value = f"**Type:** `{row['error_type']}`\n**Msg:** {row['message']}\n**Time:** {row['created_at']}"
            embed.add_field(name=f"Error #{row['id']}", value=value, inline=False)
            
        await ctx.respond(embed=embed, ephemeral=True)

    @logs.command(name="clear", description="Clear all error logs")
    @discord.default_permissions(administrator=True)
    async def logs_clear(self, ctx: discord.ApplicationContext):
        await ctx.defer(ephemeral=True)
        await admin_service.clear_all_errors()
        
        await ctx.respond("🔥 All error logs have been cleared.", ephemeral=True)
        
    @logs.command(name="details", description="View full details for a specific error ID")
    @discord.default_permissions(administrator=True)
    async def logs_details(self, ctx: discord.ApplicationContext, error_id: int):
        await ctx.defer(ephemeral=True)
        error_details = await admin_service.get_error_details(error_id)
            
        if not error_details:
            await ctx.respond(f"❌ Error #{error_id} not found.", ephemeral=True)
            return
            
        full_report = (
            f"Error ID: {error_details['id']}\n"
            f"Type: {error_details['error_type']}\n"
            f"Message: {error_details['message']}\n"
            f"Time: {error_details['created_at']}\n"
            f"{'-'*40}\n"
            f"CONTEXT:\n{error_details['context']}\n"
            f"{'-'*40}\n"
            f"TRACEBACK:\n{error_details['traceback']}\n"
        )
        
        if len(full_report) < 1900:
            await ctx.respond(f"```\n{full_report}\n```", ephemeral=True)
        else:
            fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="error_details_")
            try:
                async with aiofiles.open(temp_path, "w") as f:
                    await f.write(full_report)
                await ctx.respond(
                    f"📄 Error #{error_id} Details:", 
                    file=discord.File(temp_path, filename="error_details.txt"),
                    ephemeral=True
                )
            finally:
                os.close(fd)
                os.unlink(temp_path)

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Admin(bot))
