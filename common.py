"""stuff that'd cause circular imports if it lived in main or a cog"""
import os
from pathlib import Path

import aiosqlite

DB_FILE = Path(__file__).parent / "reminders.db"
DEFAULT_PREFIX = "e!"

# in-memory guild config, hydrated from db on boot. cogs read/write these directly
prefixes = {}
log_channels = {}

# .env comma list, e.g. ADMIN_IDS=123,456
raw_env = os.getenv("ADMIN_IDS", "")
print(f"DEBUG RAW ENV STRING: repr({raw_env})") # Shows hidden characters/quotes

ADMIN_IDS = {
    int(x.strip('"\' '))
    for x in raw_env.split(",")
    if x.strip('"\' ').isdigit()
}
print(f"DEBUG PARSED SET: {ADMIN_IDS}")

def get_prefix(bot_, message):
    from discord.ext import commands

    if not message.guild:
        return commands.when_mentioned_or(DEFAULT_PREFIX)(bot_, message)
    p = prefixes.get(str(message.guild.id), DEFAULT_PREFIX)
    return commands.when_mentioned_or(p)(bot_, message)


async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                fire_at REAL NOT NULL,
                message TEXT NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                prefix TEXT,
                log_channel_id INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji TEXT NOT NULL,
                role_id INTEGER NOT NULL,
                PRIMARY KEY (message_id, emoji)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bump_reminders (
                guild_id INTEGER NOT NULL,
                service TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                fire_at REAL NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, service)
            )
            """
        )
        await db.commit()


async def load_guild_settings():
    async with aiosqlite.connect(DB_FILE) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT guild_id, prefix, log_channel_id FROM guild_settings"
        ) as cursor:
            rows = await cursor.fetchall()

    for row in rows:
        if row["prefix"]:
            prefixes[str(row["guild_id"])] = row["prefix"]
        if row["log_channel_id"]:
            log_channels[str(row["guild_id"])] = row["log_channel_id"]


async def upsert_guild_setting(guild_id, *, prefix=None, log_channel_id=None):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO guild_settings (guild_id, prefix, log_channel_id) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET "
            "prefix = COALESCE(excluded.prefix, prefix), "
            "log_channel_id = COALESCE(excluded.log_channel_id, log_channel_id)",
            (guild_id, prefix, log_channel_id),
        )
        await db.commit()


async def clear_guild_prefix(guild_id):
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT INTO guild_settings (guild_id, prefix, log_channel_id) "
            "VALUES (?, NULL, NULL) "
            "ON CONFLICT(guild_id) DO UPDATE SET prefix = NULL",
            (guild_id,),
        )
        await db.commit()


def get_log_channel(ctx):
    chan_id = log_channels.get(str(ctx.guild.id))
    if chan_id is None:
        return None
    return ctx.guild.get_channel(chan_id)


async def post_mod_log(ctx, *, title, color, fields):
    import discord

    channel = get_log_channel(ctx)
    if channel is None:
        return

    embed = discord.Embed(title=title, color=color)
    for name, value in fields:
        embed.add_field(name=name, value=value, inline=False)
    embed.set_footer(text=f"Action by {ctx.author}")
    embed.timestamp = discord.utils.utcnow()

    try:
        await channel.send(embed=embed)
    except discord.Forbidden:
        pass


def is_admin():
    """gate for admin.py, not the same as discord Administrator perm"""
    from discord.ext import commands

    async def predicate(ctx):
        return ctx.author.id in ADMIN_IDS

    return commands.check(predicate)