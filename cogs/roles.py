import aiosqlite
import discord
from discord.ext import bridge, commands

import common


async def get_reaction_role(message_id: int, emoji: str):
    async with (
        aiosqlite.connect(common.DB_FILE) as db,
        db.execute(
            "SELECT role_id FROM reaction_roles WHERE message_id = ? AND emoji = ?",
            (message_id, emoji),
        ) as cursor,
    ):
        row = await cursor.fetchone()
        return row[0] if row else None


class Roles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @bridge.bridge_command(name="reactionrole")
    @commands.has_permissions(manage_roles=True)
    async def reactionrole(self, ctx, message_id: str, emoji: str, role: discord.Role):
        try:
            message_id = int(message_id)
        except ValueError:
            await ctx.respond("that doesn't look like a message id")
            return

        if role >= ctx.guild.me.top_role:
            await ctx.respond("that role is above my highest role")
            return

        target = None
        for channel in ctx.guild.text_channels:
            try:
                target = await channel.fetch_message(message_id)
                break
            except (discord.NotFound, discord.Forbidden):
                continue

        if target is None:
            await ctx.respond("couldn't find a message with that id")
            return

        try:
            await target.add_reaction(emoji)
        except discord.HTTPException:
            await ctx.respond("that isnt an emoji")
            return

        async with aiosqlite.connect(common.DB_FILE) as db:
            await db.execute(
                "INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT(message_id, emoji) DO UPDATE SET role_id = excluded.role_id",
                (ctx.guild.id, message_id, emoji, role.id),
            )
            await db.commit()

        await ctx.respond(
            f"reacting with {emoji} on that message now grants {role.mention}."
        )

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.member is None or payload.member.bot:
            return

        role_id = await get_reaction_role(payload.message_id, str(payload.emoji))
        if role_id is None:
            return

        role = payload.member.guild.get_role(role_id)
        if role is None:
            return

        try:
            await payload.member.add_roles(role, reason="Reaction role")
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        guild = self.bot.get_guild(payload.guild_id) if payload.guild_id else None
        if guild is None:
            return

        role_id = await get_reaction_role(payload.message_id, str(payload.emoji))
        if role_id is None:
            return

        role = guild.get_role(role_id)
        member = guild.get_member(payload.user_id)
        if role is None or member is None:
            return

        try:
            await member.remove_roles(role, reason="Reaction role removed")
        except discord.Forbidden:
            pass


def setup(bot):
    bot.add_cog(Roles(bot))