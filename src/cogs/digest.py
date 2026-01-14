import discord
from discord.ext import commands, tasks
from discord.commands import SlashCommandGroup
import asyncio
import logging
from datetime import datetime

from ..services.db import db
from ..services.digest_service import digest_service
from ..utils.chunker import chunk_text
from ..utils.constants import MAX_TOPICS_LIMIT, THREAD_ARCHIVE_DURATION_MINUTES

logger = logging.getLogger("grok.digest")


class Digest(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._user_locks: dict[int, asyncio.Lock] = {}
        self.digest_loop.start()

    def cog_unload(self):
        self.digest_loop.cancel()

    @commands.Cog.listener()
    async def on_ready(self):
        logger.info(f'Cog {self.__class__.__name__} is ready.')

    digest = SlashCommandGroup("digest", "Manage your daily news digest")
    topics = digest.create_subgroup("topics", "Manage your digest topics")
    config = digest.create_subgroup("config", "Configure digest settings")

    # --- Configuration Commands ---

    @config.command(name="max_topics", description="Set the maximum number of digest topics per user (Admin only)")
    @discord.default_permissions(administrator=True)
    async def set_max_topics(self, ctx: discord.ApplicationContext, limit: int):
        if limit < 1 or limit > MAX_TOPICS_LIMIT:
            await ctx.respond(f"❌ Limit must be between 1 and {MAX_TOPICS_LIMIT}.", ephemeral=True)
            return

        await digest_service.set_max_topics(ctx.guild.id, limit)
        await ctx.respond(f"✅ Max topics per user set to **{limit}**.")

    @config.command(name="channel", description="Set the channel where digests will be posted (Admin only)")
    @discord.default_permissions(administrator=True)
    async def set_channel(self, ctx: discord.ApplicationContext, channel: discord.TextChannel):
        await digest_service.set_digest_channel(ctx.guild.id, channel.id)
        await ctx.respond(f"✅ Digest channel set to {channel.mention}")

    @config.command(name="time", description="Set your daily digest time (24h format, e.g., 09:00)")
    async def set_time(self, ctx: discord.ApplicationContext, time_str: str):
        success, message = await digest_service.set_daily_time(ctx.user.id, ctx.guild.id, time_str)
        await ctx.respond(f"{'✅' if success else '❌'} {message}", ephemeral=not success)

    @config.command(name="timezone", description="Set your timezone (e.g., UTC, America/New_York)")
    async def set_timezone(self, ctx: discord.ApplicationContext, timezone: str):
        success, message = await digest_service.set_timezone(ctx.user.id, ctx.guild.id, timezone)
        await ctx.respond(f"{'✅' if success else '❌'} {message}", ephemeral=not success)

    # --- Topic Commands ---

    @topics.command(name="add", description="Add a topic to your digest")
    async def add_topic(self, ctx: discord.ApplicationContext, topic: str):
        success, message = await digest_service.add_topic(ctx.user.id, ctx.guild.id, topic)
        await ctx.respond(f"{'✅' if success else '❌'} {message}", ephemeral=not success)

    @topics.command(name="remove", description="Remove a topic from your digest")
    async def remove_topic(self, ctx: discord.ApplicationContext, topic: str):
        await digest_service.remove_topic(ctx.user.id, ctx.guild.id, topic)
        await ctx.respond(f"✅ Removed topic: **{topic}**")

    @topics.command(name="list", description="List your digest topics")
    async def list_topics(self, ctx: discord.ApplicationContext):
        topics_list = await digest_service.get_user_topics(ctx.user.id, ctx.guild.id)
        
        if not topics_list:
            await ctx.respond("You have no topics set. Use `/digest topics add` to get started.")
            return

        formatted = "\n".join([f"• {topic}" for topic in topics_list])
        await ctx.respond(f"**Your Digest Topics:**\n{formatted}")

    @digest.command(name="now", description="Trigger your daily digest immediately (for testing)")
    @commands.cooldown(1, 300, commands.BucketType.user)
    async def trigger_now(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        
        lock = self._get_user_lock(ctx.user.id)
        if lock.locked():
            await ctx.followup.send("⏳ Your digest is already being generated! Please wait.")
            return

        result = await self.send_digest(ctx.guild.id, ctx.user.id)
        if result:
            await ctx.followup.send("✅ Digest sent!")
        else:
            await ctx.followup.send("❌ Could not send digest. Check if you have topics and a configured channel.")

    # --- Background Loop ---

    @tasks.loop(minutes=1)
    async def digest_loop(self):
        """Checks every minute for users due for a digest."""
        try:
            guild_ids = await digest_service.get_guilds_with_digest_config()

            for guild_id in guild_ids:
                users = await digest_service.get_users_for_digest_check(guild_id)
                    
                for user in users:
                    if await digest_service.is_due(user):
                        await self.send_digest(guild_id, user['user_id'])
                        
        except Exception as e:
            logger.error(f"Error in digest loop: {e}")
            await db.log_error(e, {"context": "digest_loop"})

    @digest_loop.before_loop
    async def before_digest_loop(self):
        await self.bot.wait_until_ready()

    # --- Digest Sending ---

    def _get_user_lock(self, user_id: int) -> asyncio.Lock:
        """Get or create a lock for a user."""
        if user_id not in self._user_locks:
            self._user_locks[user_id] = asyncio.Lock()
        return self._user_locks[user_id]

    async def send_digest(self, guild_id: int, user_id: int) -> bool:
        """Generates and sends the digest."""
        lock = self._get_user_lock(user_id)
        
        if lock.locked():
            logger.info(f"Skipping digest for {user_id} - already processing")
            return False
        
        async with lock:
            try:
                channel_id = await digest_service.get_digest_channel_id(guild_id)
                if not channel_id:
                    return False

                channel = self.bot.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except discord.NotFound:
                        return False
                
                if not isinstance(channel, discord.TextChannel):
                    return False

                topics = await digest_service.get_prepared_topics(user_id, guild_id)
                
                if not topics:
                    return False

                user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
                
                timezone_str = await digest_service.get_user_timezone(user_id, guild_id)
                user_tz = digest_service.get_user_timezone_safe(timezone_str)
                
                now_user = datetime.now(user_tz)
                date_str = now_user.strftime("%Y-%m-%d")
                thread_name = f"Daily Digest for {user.display_name} - {date_str}"
                
                greeting = digest_service.get_greeting(now_user.hour)

                try:
                    start_msg = await channel.send(f"📰 **{greeting}, {user.mention}!** Here is your Daily Digest for {date_str}")
                    thread = await start_msg.create_thread(name=thread_name, auto_archive_duration=THREAD_ARCHIVE_DURATION_MINUTES)
                except Exception as e:
                    logger.error(f"Failed to create thread: {e}")
                    return False

                for topic in topics:
                    section_title, content = await digest_service.generate_topic_digest(user_id, guild_id, topic)
                    
                    header = f"### {section_title}\n"
                    first_chunk_limit = 1900 - len(header)
                    
                    if len(content) <= first_chunk_limit:
                        await thread.send(f"{header}{content}")
                    else:
                        chunks = chunk_text(content, chunk_size=1900)
                        for i, chunk in enumerate(chunks):
                            if i == 0:
                                await thread.send(f"{header}{chunk}")
                            else:
                                await thread.send(chunk)

                await digest_service.mark_digest_sent(user_id, guild_id)
                
                return True

            except Exception as e:
                logger.error(f"Failed to send digest to {user_id}: {e}")
                await db.log_error(e, {"context": "send_digest", "user_id": user_id})
                return False


def setup(bot: commands.Bot):
    bot.add_cog(Digest(bot))
