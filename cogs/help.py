import discord
from discord.ext import bridge, commands

import common
from cogs.moderation import WARN_MUTE_THRESHOLD
from cogs.bump import BUMPER_ROLE_NAME


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @bridge.bridge_command(name="cmds")
    async def cmds(self, ctx):
        prefix = (
            common.prefixes.get(str(ctx.guild.id), common.DEFAULT_PREFIX)
            if ctx.guild
            else common.DEFAULT_PREFIX
        )

        embed = discord.Embed(
            title="Commands",
            description="also all work as /slash commands",
            color=0x5865F2,
        )
        embed.add_field(name=f"{prefix}ping", value="latency check", inline=False)
        embed.add_field(
            name=f"{prefix}setprefix [new]",
            value="Manage Server required, 5 chars max",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}resetprefix", value="Manage Server required", inline=False
        )
        embed.add_field(
            name=f"{prefix}clear [amount]",
            value="Manage Messages required, max 100",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}kick @member [reason]",
            value="Kick Members required",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}ban @member [reason]",
            value="Ban Members required",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}unban <name/id/name#0000>",
            value="Ban Members required",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}mute @member <10m/2h/1d> [reason]",
            value="Moderate Members required, 28 day max",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}unmute @member",
            value="Moderate Members required",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}warn @member [reason]",
            value="Moderate Members required, logged + stored, auto-mutes at "
            f"{WARN_MUTE_THRESHOLD} warnings",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}warnings @member",
            value="Moderate Members required, shows a member's last 10 warnings",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}delwarning <id>",
            value="Manage Server required, deletes a single warning",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}setlogchannel [#channel]",
            value="Manage Server required, sets where mod actions are logged",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}slowmode [seconds]",
            value="Manage Channels required, run again to disable, default 10s",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}userinfo [@member]",
            value="yourself if nothing tagged",
            inline=False,
        )
        embed.add_field(name=f"{prefix}serverinfo", value="", inline=False)
        embed.add_field(name=f"{prefix}roleinfo <role>", value="", inline=False)
        embed.add_field(
            name=f"{prefix}reactionrole <message_id> <emoji> <role>",
            value="Manage Roles required, sets up self-assignable roles via reactions",
            inline=False,
        )
        embed.add_field(
            name=f'{prefix}poll "q" ["opt"...]',
            value="no options = thumbs up/down, up to 10 options, 15s cooldown",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}reminder <10m/2h/1d> <msg>",
            value="30 day max, 10s cooldown",
            inline=False,
        )
        embed.add_field(
            name=f"{prefix}reminders", value="lists your pending reminders", inline=False
        )
        embed.add_field(
            name=f"{prefix}delreminder <id>",
            value="cancels one of your reminders",
            inline=False,
        )
        embed.add_field(
            name="Bump reminders",
            value=(
                "Automatic. detects successful `/bump` from Disboard (2h) and "
                f"Carl-bot (5h), then pings the `{BUMPER_ROLE_NAME}` role when "
                "the cooldown is up."
            ),
            inline=False,
        )

        if ctx.author.id in common.ADMIN_IDS:
            embed.add_field(
                name=f"{prefix}cogs / cogload / cogunload / cogreload",
                value="bot admin only, not a mod perm",
                inline=False,
            )

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Help(bot))