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
        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=discord.Intents.all(),
            help_command=None,
            debug_guilds=[691837132981141615, 1415186232404742177]
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
        # Optionally report other errors to the user
        # await ctx.send(f"An error occurred: {error}")

bot = GrokBot()
