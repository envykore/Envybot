import discord
from discord.ext import bridge, commands

import common


class Admin(commands.Cog):
    """everything main.py used to do lives here now"""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"logged in as {self.bot.user}")
        await common.init_db()
        await common.load_guild_settings()
        print("db ready, guild settings loaded")

    @bridge.bridge_command(name="cogs")
    @common.is_admin()
    async def cogs(self, ctx):
        loaded = sorted(self.bot.extensions.keys())
        listing = "\n".join(f"- {c}" for c in loaded) or "none loaded, ggs"
        await ctx.respond(f"```\n{listing}\n```")

    @bridge.bridge_command(name="cogload")
    @common.is_admin()
    async def cogload(self, ctx, name: str):
        name = _normalize(name)
        try:
            self.bot.load_extension(name)
        except commands.ExtensionAlreadyLoaded:
            await ctx.respond(f"`{name}` is already loaded")
            return
        except commands.ExtensionError as e:
            await ctx.respond(f"failed to load `{name}`: {e}")
            return
        await ctx.respond(f"loaded `{name}`")

    @bridge.bridge_command(name="cogunload")
    @common.is_admin()
    async def cogunload(self, ctx, name: str):
        name = _normalize(name)
        if name == "cogs.admin":
            await ctx.respond("nuh uh")
            return
        try:
            self.bot.unload_extension(name)
        except commands.ExtensionNotLoaded:
            await ctx.respond(f"`{name}` isn't loaded")
            return
        await ctx.respond(f"unloaded `{name}`")

    @bridge.bridge_command(name="cogreload")
    @common.is_admin()
    async def cogreload(self, ctx, name: str):
        name = _normalize(name)
        try:
            self.bot.reload_extension(name)
        except commands.ExtensionNotLoaded:
            try:
                self.bot.load_extension(name)
            except commands.ExtensionError as e:
                await ctx.respond(f"failed to load `{name}`: {e}")
                return
        except commands.ExtensionError as e:
            await ctx.respond(f"failed to reload `{name}`: {e}")
            return
        await ctx.respond(f"reloaded `{name}`")

    @cogload.error
    @cogunload.error
    @cogreload.error
    @cogs.error
    async def admin_cmd_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.respond("you are not a sigma")
            return
        print(error)
        await ctx.respond("something broke")


def _normalize(name: str) -> str:
    """lets people type just 'moderation' instead of 'cogs.moderation'"""
    return name if name.startswith("cogs.") else f"cogs.{name}"


def setup(bot):
    bot.add_cog(Admin(bot))