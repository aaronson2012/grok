import discord
from discord.ext import commands
from typing import override
import logging
from ..services.ai import ai_service

logger = logging.getLogger("grok.chat")

class Chat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.default_system_prompt = (
            "You are Grok, a witty and helpful AI companion in a Discord server. "
            "You respond naturally, use emojis where appropriate, and keep the conversation engaging. "
            "You are not the xAI Grok, but a unique assistant."
        )

    @commands.Cog.listener()
    @override
    async def on_ready(self) -> None:
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        # Ignore own messages and other bots
        if message.author.bot:
            return

        # Check if mentioned
        # Note: process_commands in bot.py runs BEFORE this listener.
        # If a command was executed, we might not want to chat?
        # But commonly, if you mention the bot, you expect a chat unless it's a specific command syntax.
        # If the user says "@Grok help", it triggers the help command AND this listener?
        # To prevent double response, we can check if the message starts with the command prefix.
        
        # Since we removed the manual prefix check in bot.py due to the 'function' error,
        # we can use 'await self.bot.get_prefix(message)' to check here if needed.
        # But a simpler way is: if the message triggers a command, Context is created.
        # However, checking context here is hard.
        
        # Simple heuristic: If it's a mention, we chat.
        # If the user intentionally uses a command, they usually don't ONLY mention the bot.
        # e.g. "!ping" vs "@Grok hello".
        # Exception: "@Grok ping" (if mention is a prefix).
        
        if self.bot.user.mentioned_in(message) and not message.mention_everyone:
            # Avoid replying to itself or if it's a reply to someone else where the bot is just mentioned in passing?
            # Ideally, we only reply if the bot is mentioned at the START or is the primary subject.
            
            clean_content = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
            
            # If the content is empty (just a ping), maybe ignore or say "What's up?"
            if not clean_content:
                clean_content = "Hello!"

            async with message.channel.typing():
                # Retrieve history
                history = []
                async for msg in message.channel.history(limit=10, before=message):
                    if msg.author.bot and msg.author != self.bot.user:
                        continue
                    
                    role = "assistant" if msg.author == self.bot.user else "user"
                    content = msg.content.replace(f"<@{self.bot.user.id}>", "").strip()
                    if content:
                        history.insert(0, {"role": role, "content": content})

                response = await ai_service.generate_response(
                    system_prompt=self.default_system_prompt,
                    user_message=clean_content,
                    history=history
                )
                
                await message.reply(response, mention_author=False)

    @discord.slash_command(name="chat", description="Start a new chat thread with Grok")
    async def chat(self, ctx: discord.ApplicationContext, prompt: str) -> None:
        await ctx.defer()
        response = await ai_service.generate_response(
            system_prompt=self.default_system_prompt,
            user_message=prompt
        )
        await ctx.respond(response)

def setup(bot: commands.Bot) -> None:
    bot.add_cog(Chat(bot))
