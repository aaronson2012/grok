import discord
import os
import logging
from discord.ext import commands
from .config import config
from .services.db import db

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("grok.bot")

class GrokBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
            help_command=None,
            debug_guilds=config.DEBUG_GUILD_IDS or None
        )
    
    async def on_ready(self):
        logger.info(f"Logged in as {self.user} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} guilds")
        
        # Initialize Database
        await db.connect()
        
        # Load extensions
        await self.load_extensions()
        
        # Sync commands
        try:
            # sync_commands returns a list of commands, or raises error
            await self.sync_commands()
            logger.info(f"Synced commands successfully")
        except Exception as e:
            logger.error(f"Failed to sync commands: {e}")

    async def load_extensions(self):
        for filename in os.listdir("./src/cogs"):
            if filename.endswith(".py") and not filename.startswith("_"):
                try:
                    self.load_extension(f"src.cogs.{filename[:-3]}")
                    logger.info(f"Loaded extension: {filename}")
                except Exception as e:
                    logger.error(f"Failed to load extension {filename}: {e}")

    async def on_message(self, message):
        if message.author.bot:
            return
        
        # Process commands first
        await self.process_commands(message)
        
        # If it's a direct mention and not a command, trigger AI (logic will be in a cog)
        pass

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return # Ignore unknown commands
        logger.error(f"Command error: {error}")
        await db.log_error(error, {"context": "Discord command", "command": ctx.command.name if ctx.command else "unknown", "guild_id": ctx.guild.id if ctx.guild else None})

bot = GrokBot()
