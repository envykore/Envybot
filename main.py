import asyncio
import os
from pathlib import Path

import discord
from discord.ext import bridge
from dotenv import load_dotenv

from common import get_prefix

load_dotenv(dotenv_path=Path(__file__).parent / ".env")
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in the .env file")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = bridge.Bot(command_prefix=get_prefix, intents=intents)

# admin last, it needs the others already loaded to do its job
STARTUP_COGS = (
    "cogs.moderation",
    "cogs.info",
    "cogs.roles",
    "cogs.reminders",
    "cogs.bump",
    "cogs.fun",
    "cogs.help",
    "cogs.admin",
)


@bot.event
async def on_ready():
    print(f"logged in as {bot.user}")


async def main():
    async with bot:
        for cog in STARTUP_COGS:
            bot.load_extension(cog)
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
# git commit -m "BOT REWRITE IN... idk really"
