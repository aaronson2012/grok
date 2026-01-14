import discord
from discord.ext import commands
from typing import override
import logging
from ..services.db import db
from ..services.persona_service import persona_service
from ..services.emoji_manager import emoji_manager

logger = logging.getLogger("grok.settings")


class PersonaSelect(discord.ui.Select):
    def __init__(self, personas: list, author_id: int):
        self.author_id = author_id
        options = []
        for p in personas:
            desc = p['description']
            if len(desc) > 50:
                desc = desc[:47] + "..."
            
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
        
        await persona_service.set_guild_persona(interaction.guild.id, persona_id)
        
        self.disabled = True
        await interaction.response.edit_message(content=f"✅ Switched persona to **{name}**!", view=self.view)


class PersonaView(discord.ui.View):
    def __init__(self, personas: list, author_id: int):
        super().__init__(timeout=60)
        self.add_item(PersonaSelect(personas, author_id))
        self.message = None

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                await self.message.edit(content="❌ Menu timed out.", view=self)
            except discord.NotFound:
                pass


class PersonaDeleteSelect(discord.ui.Select):
    def __init__(self, personas: list, author_id: int):
        self.author_id = author_id
        options = []
        for p in personas:
            options.append(discord.SelectOption(
                label=p['name'],
                description=p['description'][:97] + '...' if len(p['description']) > 100 else p['description'],
                value=str(p['id'])
            ))
        super().__init__(placeholder="Select a persona to DELETE...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ You cannot control this menu.", ephemeral=True)
            return

        persona_id = int(self.values[0])
        name = await persona_service.delete_persona(persona_id)
        
        self.disabled = True
        await interaction.response.edit_message(content=f"🗑️ Deleted persona **{name}**.", view=self.view)


class PersonaDeleteView(discord.ui.View):
    def __init__(self, personas: list, author_id: int):
        super().__init__(timeout=60)
        self.add_item(PersonaDeleteSelect(personas, author_id))
        self.message = None

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        
        if self.message:
            try:
                await self.message.edit(content="❌ Menu timed out.", view=self)
            except discord.NotFound:
                pass


class PersonaModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Create New Persona")
        self.add_item(discord.ui.InputText(
            label="Describe the Persona",
            placeholder="e.g. Batman, or 'A sarcastic hacker'...",
            style=discord.InputTextStyle.paragraph,
            min_length=3,
            max_length=1000
        ))

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_input = self.children[0].value
        
        success, result = await persona_service.create_persona(
            user_input=user_input,
            created_by=interaction.user.id,
            collision_suffix=interaction.user.discriminator
        )
        
        if success:
            embed = discord.Embed(title="✨ Persona Created", color=discord.Color.green())
            embed.add_field(name="Name", value=result["name"], inline=True)
            embed.add_field(name="Description", value=result["description"], inline=True)
            embed.add_field(name="System Prompt", value=result["system_prompt"], inline=False)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"❌ {result}")


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
        personas = await persona_service.get_all_personas()
            
        if not personas:
            await ctx.respond("No personas found!", ephemeral=False)
            return

        view = PersonaView(personas, ctx.author.id)
        interaction = await ctx.respond("🎭 **Choose a Persona**:", view=view)
        msg = await interaction.original_response()
        view.message = msg

    @persona.command(name="create", description="Create a new custom persona with AI assistance")
    @discord.default_permissions(administrator=True)
    @commands.cooldown(1, 60, commands.BucketType.user)
    async def create_persona(self, ctx: discord.ApplicationContext):
        modal = PersonaModal()
        await ctx.send_modal(modal)

    @persona.command(name="delete", description="Delete a custom persona")
    @discord.default_permissions(administrator=True)
    async def delete_persona(self, ctx: discord.ApplicationContext):
        personas = await persona_service.get_deletable_personas()
            
        if not personas:
            await ctx.respond("No custom personas found to delete.", ephemeral=False)
            return

        view = PersonaDeleteView(personas, ctx.author.id)
        interaction = await ctx.respond("🗑️ **Select a Persona to Delete**:", view=view, ephemeral=False)
        msg = await interaction.original_response()
        view.message = msg

    @persona.command(name="current", description="Show the current active persona")
    async def current_persona(self, ctx: discord.ApplicationContext):
        row = await persona_service.get_current_persona(ctx.guild.id)
        
        if row:
            await ctx.respond(f"🎭 Current Persona: **{row['name']}**\n*{row['description']}*")
        else:
            await ctx.respond("🎭 Current Persona: **Standard** (Default)")

    @discord.slash_command(name="analyze_emojis", description="Force re-analyze server emojis")
    @discord.default_permissions(administrator=True)
    @commands.cooldown(1, 300, commands.BucketType.guild)
    async def analyze_emojis(self, ctx: discord.ApplicationContext):
        await ctx.defer()
        try:
            count = await emoji_manager.analyze_guild_emojis(ctx.guild)
            await ctx.followup.send(f"✅ Analysis complete! Processed **{count}** new/updated emojis.")
        except Exception as e:
            logger.error(f"Emoji analysis failed: {e}")
            await ctx.followup.send("❌ Analysis failed. Please try again.")


def setup(bot: commands.Bot) -> None:
    bot.add_cog(Settings(bot))
