import re
from datetime import datetime, timedelta, timezone

import aiosqlite
import discord
from discord.ext import bridge, commands

import common

WARN_MUTE_THRESHOLD = 3
WARN_MUTE_SECONDS = 600

DURATION_RE = re.compile(r"(\d+)([smhd])")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def parse_duration(text):
    matches = DURATION_RE.findall(text.lower())
    if not matches:
        return None
    return sum(int(n) * UNITS[u] for n, u in matches)


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @bridge.bridge_command(name="clear")
    @commands.has_permissions(manage_messages=True)
    async def clear(self, ctx, amount: int = 5):
        amount = min(amount, 100)

        if ctx.is_app:
            deleted = await ctx.channel.purge(limit=amount)
            await ctx.respond(
                f"Deleted {len(deleted)} messages.", ephemeral=True, delete_after=5
            )
        else:
            deleted = await ctx.channel.purge(limit=amount + 1)
            msg = await ctx.channel.send(f"Deleted {len(deleted) - 1} messages.")
            await msg.delete(delay=5)

        await common.post_mod_log(
            ctx,
            title="Messages Cleared",
            color=0x99AAB5,
            fields=[
                ("Channel", ctx.channel.mention),
                ("Amount", str(amount)),
                ("Cleared by", ctx.author.mention),
            ],
        )

    @bridge.bridge_command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason="No reason provided"):
        if member == ctx.author:
            await ctx.respond("I refuse")
            return
        try:
            await member.kick(reason=reason)
            await ctx.respond(f"kicked {member.mention}. Reason: {reason}")
        except discord.Forbidden:
            await ctx.respond("no perms to kick that user")
            return

        await common.post_mod_log(
            ctx,
            title="Member Kicked",
            color=0xFF9900,
            fields=[
                ("Member", f"{member.mention} ({member})"),
                ("Kicked by", ctx.author.mention),
                ("Reason", reason),
            ],
        )

    @bridge.bridge_command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx, member: discord.Member, *, reason="No reason provided"):
        try:
            await member.ban(reason=reason, delete_message_seconds=0)
            await ctx.respond(f"banned {member.mention}. Reason: {reason}")
        except discord.Forbidden:
            await ctx.respond("no perms to ban that user")
            return

        await common.post_mod_log(
            ctx,
            title="Member Banned",
            color=0xFF0000,
            fields=[
                ("Member", f"{member.mention} ({member})"),
                ("Banned by", ctx.author.mention),
                ("Reason", reason),
            ],
        )

    @bridge.bridge_command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute(
        self, ctx, member: discord.Member, duration: str, *, reason="No reason provided"
    ):
        if member == ctx.author:
            await ctx.respond("I refuse")
            return

        seconds = parse_duration(duration)
        if not seconds:
            await ctx.respond("couldn't parse that, try `10m` or `1h30m`")
            return
        seconds = min(seconds, 2419200)  # discord cap

        try:
            until = discord.utils.utcnow() + timedelta(seconds=seconds)
            await member.timeout(until, reason=reason)
            await ctx.respond(f"Muted {member.mention} for {duration}. Reason: {reason}")
        except discord.Forbidden:
            await ctx.respond("No perms to timeout that user")
            return

        await common.post_mod_log(
            ctx,
            title="Member Muted",
            color=0xFFCC00,
            fields=[
                ("Member", f"{member.mention} ({member})"),
                ("Duration", duration),
                ("Muted by", ctx.author.mention),
                ("Reason", reason),
            ],
        )

    @bridge.bridge_command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member):
        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
            await ctx.respond(f"Unmuted {member.mention}.")
        except discord.Forbidden:
            await ctx.respond("No perms to unmute that user")
            return

        await common.post_mod_log(
            ctx,
            title="Member Unmuted",
            color=0x00CC66,
            fields=[
                ("Member", f"{member.mention} ({member})"),
                ("Unmuted by", ctx.author.mention),
            ],
        )

    @bridge.bridge_command(name="unban")  # TODO: Optimize this
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, *, user: str):
        banned = [entry async for entry in ctx.guild.bans()]
        user = user.strip()

        match = None
        mention_match = re.match(r"<@!?(\d+)>$", user)

        if mention_match:
            uid = int(mention_match.group(1))
            match = next((e for e in banned if e.user.id == uid), None)
        elif user.isdigit():
            uid = int(user)
            match = next((e for e in banned if e.user.id == uid), None)
        elif "#" in user:
            name, disc = user.rsplit("#", 1)
            match = next(
                (e for e in banned if e.user.name == name and e.user.discriminator == disc),
                None,
            )
        else:
            match = next((e for e in banned if e.user.name.lower() == user.lower()), None)

        if match is None:
            await ctx.respond(f"couldn't find `{user}` in the ban list")
            return

        await ctx.guild.unban(match.user, reason=f"Unbanned by {ctx.author}")
        await ctx.respond(f"Unbanned {match.user}.")

        await common.post_mod_log(
            ctx,
            title="Member Unbanned",
            color=0x00CC66,
            fields=[
                ("Member", str(match.user)),
                ("Unbanned by", ctx.author.mention),
            ],
        )

    @bridge.bridge_command(name="setlogchannel")
    @commands.has_permissions(manage_guild=True)
    async def setlogchannel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        common.log_channels[str(ctx.guild.id)] = channel.id
        await common.upsert_guild_setting(ctx.guild.id, log_channel_id=channel.id)
        await ctx.respond(f"modlogs will be posted in {channel.mention}")

    @bridge.bridge_command(name="warn")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx, member: discord.Member, *, reason="No reason provided"):
        log_channel = common.get_log_channel(ctx)
        if not log_channel:
            return await ctx.respond("no log channel set use {prefix}setlogchannel")

        async with aiosqlite.connect(common.DB_FILE) as db:
            await db.execute(
                """INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    ctx.guild.id,
                    member.id,
                    ctx.author.id,
                    reason,
                    discord.utils.utcnow().timestamp(),
                ),
            )
            await db.commit()

            async with db.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
                (ctx.guild.id, member.id),
            ) as cursor:
                (warning_count,) = await cursor.fetchone()

        await common.post_mod_log(
            ctx,
            title="user Warned",
            color=0xFFCC00,
            fields=[
                ("user", f"{member.mention} ({member})"),
                ("Warned by", ctx.author.mention),
                ("Reason", reason),
                ("Total Warnings", str(warning_count)),
            ],
        )

        response = f"warned {member.mention} ({warning_count} total)."

        if warning_count >= WARN_MUTE_THRESHOLD and member != ctx.author:
            try:
                until = discord.utils.utcnow() + timedelta(seconds=WARN_MUTE_SECONDS)
                await member.timeout(
                    until, reason=f"Auto-mute: reached {warning_count} warnings"
                )
                response += f"\nAuto-muted for {WARN_MUTE_SECONDS // 60}m."
                await common.post_mod_log(
                    ctx,
                    title="user automuted",
                    color=0xFF6600,
                    fields=[
                        ("user", f"{member.mention} ({member})"),
                        ("Reason", f"Reached {warning_count} warnings"),
                    ],
                )
            except discord.Forbidden:
                response += "\n*failed to automute check perms.*"

        await ctx.respond(response)

    @bridge.bridge_command(name="warnings")
    @commands.has_permissions(moderate_members=True)
    async def warnings_cmd(self, ctx, member: discord.Member):
        async with aiosqlite.connect(common.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, moderator_id, reason, created_at FROM warnings "
                "WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 10",
                (ctx.guild.id, member.id),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.respond(f"{member.mention} has no warnings.")
            return

        embed = discord.Embed(title=f"Warnings for {member}", color=0xFFCC00)
        for row in rows:
            mod = ctx.guild.get_member(row["moderator_id"])
            mod_name = mod.mention if mod else f"<@{row['moderator_id']}>"
            when = discord.utils.format_dt(
                datetime.fromtimestamp(row["created_at"], tz=timezone.utc), style="R"
            )
            embed.add_field(
                name=f"#{row['id']} — {when}",
                value=f"By {mod_name}: {row['reason']}",
                inline=False,
            )
        await ctx.respond(embed=embed)

    @bridge.bridge_command(name="delwarning")
    @commands.has_permissions(manage_guild=True)
    async def delwarning(self, ctx, warning_id: int):
        async with aiosqlite.connect(common.DB_FILE) as db:
            cursor = await db.execute(
                "DELETE FROM warnings WHERE id = ? AND guild_id = ?",
                (warning_id, ctx.guild.id),
            )
            await db.commit()

        if cursor.rowcount == 0:
            await ctx.respond(f"no warning with id `{warning_id}` in this server")
            return

        await ctx.respond(f"Deleted warning `{warning_id}`.")

    @bridge.bridge_command(name="slowmode")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx, seconds: int = 10):
        channel = ctx.channel

        if channel.slowmode_delay > 0:
            await channel.edit(slowmode_delay=0)
            await ctx.respond("Slowmode disabled.")
            return

        seconds = max(0, min(seconds, 21600))
        await channel.edit(slowmode_delay=seconds)
        await ctx.respond(f"Slowmode set to {seconds}s. Run again to disable.")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild:
            return
        if message.author and message.author.bot:
            return

        log_channel_id = common.log_channels.get(str(message.guild.id))
        if not log_channel_id:
            return
        log_channel = message.guild.get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(
            title="Message Deleted", color=0xFF0000, timestamp=discord.utils.utcnow()
        )
        embed.set_footer(
            text=f"Author ID: {message.author.id if message.author else 'Unknown'}"
        )

        if message.content or message.attachments:
            embed.set_author(
                name=str(message.author), icon_url=message.author.display_avatar.url
            )
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.add_field(name="Author", value=message.author.mention, inline=True)

            if message.content:
                content = (
                    message.content[:1000] + "..."
                    if len(message.content) > 1000
                    else message.content
                )
                embed.add_field(name="Content", value=content, inline=False)

            if message.attachments:
                filenames = ", ".join(a.filename for a in message.attachments)
                embed.add_field(name="Attachments", value=filenames, inline=False)
        else:
            embed.description = (
                "message was deleted but it was sent before bot was on "
                "or pushed out of the temp message cache"
            )
            embed.add_field(name="channel", value=message.channel.mention, inline=False)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or (before.author and before.author.bot):
            return
        if before.content == after.content:
            return

        log_channel_id = common.log_channels.get(str(before.guild.id))
        if not log_channel_id:
            return
        log_channel = before.guild.get_channel(log_channel_id)
        if not log_channel:
            return

        embed = discord.Embed(
            title="Message Edited", color=0xFFAA00, timestamp=discord.utils.utcnow()
        )
        embed.set_author(
            name=str(before.author), icon_url=before.author.display_avatar.url
        )
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Author", value=before.author.mention, inline=True)
        embed.add_field(name="Jump", value=f"[link]({after.jump_url})", inline=True)

        old_content = before.content[:1000] if before.content else "*(none)*"
        new_content = after.content[:1000] if after.content else "*(none)*"
        embed.add_field(name="Before", value=old_content, inline=False)
        embed.add_field(name="After", value=new_content, inline=False)

        try:
            await log_channel.send(embed=embed)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"missing perms: {', '.join(error.missing_permissions)}")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"missing argument: {error.param.name}")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("couldn't find that user/role")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"slow down, try again in {error.retry_after:.1f}s")
        elif isinstance(error, commands.CommandNotFound):
            pass
        elif isinstance(error, commands.CheckFailure):
            pass  # admin.py handles its own
        else:
            print(error)
            await ctx.send("something broke")

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.respond(
                f"missing perms: {', '.join(error.missing_permissions)}", ephemeral=True
            )
        elif isinstance(error, commands.BadArgument):
            await ctx.respond("couldn't find that user/role", ephemeral=True)
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.respond(
                f"slow down, try again in {error.retry_after:.1f}s", ephemeral=True
            )
        elif isinstance(error, commands.CheckFailure):
            pass
        else:
            print(error)
            await ctx.respond("something broke", ephemeral=True)


def setup(bot):
    bot.add_cog(Moderation(bot))