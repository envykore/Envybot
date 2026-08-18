from datetime import datetime, timezone

import aiosqlite
import discord
from discord.ext import bridge, commands, tasks

import common
from cogs.moderation import parse_duration


class Reminders(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    def cog_unload(self):
        self.check_reminders.cancel()

    @bridge.bridge_command(name="setprefix")
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx, new_prefix: str | None = None):
        if new_prefix is None:
            cur = common.prefixes.get(str(ctx.guild.id), common.DEFAULT_PREFIX)
            await ctx.respond(
                f"prefix is currently `{cur}`, do `{cur}setprefix <new>` to change it"
            )
            return

        if len(new_prefix) > 5:
            await ctx.respond("5 chars max")
            return

        common.prefixes[str(ctx.guild.id)] = new_prefix
        await common.upsert_guild_setting(ctx.guild.id, prefix=new_prefix)
        await ctx.respond(f"prefix is now `{new_prefix}`")

    @bridge.bridge_command(name="resetprefix")
    @commands.has_permissions(manage_guild=True)
    async def resetprefix(self, ctx):
        common.prefixes.pop(str(ctx.guild.id), None)
        await common.clear_guild_prefix(ctx.guild.id)
        await ctx.respond(f"back to default (`{common.DEFAULT_PREFIX}`)")

    @bridge.bridge_command(name="reminder", aliases=["remindme"])
    @commands.cooldown(1, 10, commands.BucketType.user)
    async def reminder(self, ctx, duration: str, *, message: str = "Reminder!"):
        seconds = parse_duration(duration)
        if not seconds:
            await ctx.respond("couldn't parse that, try `10m` or `1h30m`")
            return
        if seconds > 2592000:
            await ctx.respond("30 days max")
            return

        fire_at = discord.utils.utcnow().timestamp() + seconds

        async with aiosqlite.connect(common.DB_FILE) as db:
            cursor = await db.execute(
                "INSERT INTO reminders (user_id, channel_id, fire_at, message) "
                "VALUES (?, ?, ?, ?)",
                (ctx.author.id, ctx.channel.id, fire_at, message),
            )
            await db.commit()
            reminder_id = cursor.lastrowid

        prefix = (
            common.prefixes.get(str(ctx.guild.id), common.DEFAULT_PREFIX)
            if ctx.guild
            else common.DEFAULT_PREFIX
        )
        await ctx.respond(
            f"ok, reminding you in {duration} (id `{reminder_id}`, "
            f"`{prefix}delreminder {reminder_id}` to cancel)"
        )

    @bridge.bridge_command(name="reminders")
    async def list_reminders(self, ctx):
        async with aiosqlite.connect(common.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, fire_at, message FROM reminders WHERE user_id = ? "
                "ORDER BY fire_at ASC",
                (ctx.author.id,),
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            await ctx.respond("you have no pending reminders")
            return

        lines = [
            f"`{r['id']}` — "
            f"{discord.utils.format_dt(datetime.fromtimestamp(r['fire_at'], tz=timezone.utc), style='R')}: "
            f"{r['message']}"
            for r in rows
        ]
        embed = discord.Embed(
            title="Your Reminders", description="\n".join(lines), color=0x5865F2
        )
        await ctx.respond(embed=embed)

    @bridge.bridge_command(name="delreminder")
    async def delreminder(self, ctx, reminder_id: int):
        async with aiosqlite.connect(common.DB_FILE) as db:
            cursor = await db.execute(
                "DELETE FROM reminders WHERE id = ? AND user_id = ?",
                (reminder_id, ctx.author.id),
            )
            await db.commit()

        if cursor.rowcount == 0:
            await ctx.respond(f"no reminder with id `{reminder_id}` belonging to you")
            return

        await ctx.respond(f"cancelled reminder `{reminder_id}`.")

    @tasks.loop(seconds=10)
    async def check_reminders(self):
        now = discord.utils.utcnow().timestamp()

        async with aiosqlite.connect(common.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM reminders WHERE fire_at <= ?", (now,)
            ) as cursor:
                expired = await cursor.fetchall()

            for row in expired:
                channel = self.bot.get_channel(row["channel_id"])
                if channel is not None:
                    try:
                        await channel.send(f"<@{row['user_id']}> reminder: {row['message']}")
                    except discord.Forbidden:
                        pass
                await db.execute("DELETE FROM reminders WHERE id = ?", (row["id"],))

            await db.commit()

    @check_reminders.before_loop
    async def before_check_reminders(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(Reminders(bot))