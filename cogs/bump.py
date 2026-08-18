import aiosqlite
import discord
from discord.ext import commands, tasks

import common

DISBOARD_BOT_ID = 302050872383242240
CARL_BOT_ID = 235148962103951360

COMPONENTS_V2_FLAG = 1 << 15  # discord message flag bit

# role must be letter by letter "Bumper" otherwise pinging wont work
BUMPER_ROLE_NAME = "Bumper"
CARLBOT_PREFIX = "c!"

BUMP_DEBUG = True  # flip off once confirmed stable

BUMP_SERVICES = {
    DISBOARD_BOT_ID: {
        "name": "Disboard",
        "cooldown": 2 * 3600,
        "success_phrases": ("bump done",),
    },
    CARL_BOT_ID: {
        "name": "Carl-bot",
        "cooldown": 6 * 3600,
        "success_phrases": ("successfully bumped",),
    },
}

_BUMP_INVOCATION_WINDOW_SECONDS = 10
_BUMP_DEDUPE_SECONDS = 30


def extract_components_text(components) -> list[str]:
    texts = []
    for comp in components:
        content = getattr(comp, "content", None)
        if content:
            texts.append(content)
        section_components = getattr(comp, "components", None)
        if section_components:
            texts.extend(extract_components_text(section_components))
        children = getattr(comp, "children", None)
        if children:
            texts.extend(extract_components_text(children))
    return texts


class Bump(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._pending_carlbot_invocations = {}
        self._recent_fires = {}
        self.check_bump_reminders.start()

    def cog_unload(self):
        self.check_bump_reminders.cancel()

    def get_bump_service(self, message: discord.Message):
        if not message.author.bot or message.author.id not in BUMP_SERVICES:
            return None

        info = BUMP_SERVICES[message.author.id]
        interaction = getattr(message, "interaction", None) or getattr(
            message, "interaction_metadata", None
        )
        invoked_name = getattr(interaction, "name", None)

        if message.author.id == CARL_BOT_ID:
            if invoked_name is not None:
                if invoked_name.lower() != "bump":
                    if BUMP_DEBUG:
                        print(
                            f"[bump-debug] not a /bump "
                            f"response (was /{invoked_name})"
                        )
                    return None
            else:
                now = discord.utils.utcnow().timestamp()
                last = self._pending_carlbot_invocations.get(message.channel.id)
                if last is None or now - last > _BUMP_INVOCATION_WINDOW_SECONDS:
                    if BUMP_DEBUG:
                        print(
                            "[bump-debug] no recent "
                            f"{CARLBOT_PREFIX}bump invocation in this channel"
                        )
                    return None

        text_parts = [message.content or ""]
        for embed in message.embeds:
            text_parts.append(embed.title or "")
            text_parts.append(embed.description or "")
            for field in embed.fields:
                text_parts.append(field.value or "")
        if message.components:
            text_parts.extend(extract_components_text(message.components))

        text = " ".join(text_parts).lower()

        if BUMP_DEBUG:
            is_components_v2 = bool(message.flags.value & COMPONENTS_V2_FLAG)
            print(
                f"[bump-debug] saw message from {info['name']} "
                f"(author id {message.author.id}) in #{getattr(message.channel, 'name', message.channel.id)}"
            )
            print(f"[bump-debug] raw content: {message.content!r}")
            print(f"[bump-debug] interaction={interaction!r} invoked_name={invoked_name!r}")
            print(
                f"[bump-debug] flags={message.flags.value} "
                f"is_components_v2={is_components_v2} "
                f"num_components={len(message.components)}"
            )
            for i, embed in enumerate(message.embeds):
                print(f"[bump-debug] embed[{i}] title: {embed.title!r}")
                print(f"[bump-debug] embed[{i}] description: {embed.description!r}")
                for field in embed.fields:
                    print(f"[bump-debug] embed[{i}] field {field.name!r}: {field.value!r}")
            if message.components:
                print(
                    f"[bump-debug] components text: {extract_components_text(message.components)!r}"
                )
            print(f"[bump-debug] combined lowercased text: {text!r}")

        if "cooldown" in text or "bump this server again" in text:
            if BUMP_DEBUG:
                print("[bump-debug] looked like a cooldown/wait message, ignoring")
            return None

        matched = any(phrase in text for phrase in info["success_phrases"])
        if BUMP_DEBUG:
            print(f"[bump-debug] success phrase matched: {matched}")

        return info if matched else None

    async def handle_bump(self, message: discord.Message, service: dict):
        if not message.guild:
            return

        dedupe_key = (message.channel.id, message.author.id, service["name"])
        now = discord.utils.utcnow().timestamp()
        last_fired = self._recent_fires.get(dedupe_key)
        if last_fired is not None and now - last_fired < _BUMP_DEDUPE_SECONDS:
            if BUMP_DEBUG:
                print(f"[bump-debug] ignoring duplicate bump fire for {dedupe_key}")
            return
        self._recent_fires[dedupe_key] = now

        fire_at = now + service["cooldown"]

        async with aiosqlite.connect(common.DB_FILE) as db:
            await db.execute(
                """INSERT INTO bump_reminders (guild_id, service, channel_id, fire_at, notified)
                   VALUES (?, ?, ?, ?, 0)
                   ON CONFLICT(guild_id, service) DO UPDATE SET
                       channel_id = excluded.channel_id,
                       fire_at = excluded.fire_at,
                       notified = 0""",
                (message.guild.id, service["name"], message.channel.id, fire_at),
            )
            await db.commit()

        hours = service["cooldown"] // 3600
        try:
            await message.channel.send(
                f"thanks for bumping with **{service['name']}**, "
                f"ill remind this channel in {hours}h"
            )
        except discord.Forbidden:
            pass

    async def process_potential_bump(self, message: discord.Message):
        if not message.author.bot:
            return
        service = self.get_bump_service(message)
        if service:
            await self.handle_bump(message, service)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if (
            message.guild
            and not message.author.bot
            and message.content.strip().lower().startswith(f"{CARLBOT_PREFIX}bump")
        ):
            self._pending_carlbot_invocations[message.channel.id] = (
                discord.utils.utcnow().timestamp()
            )

        await self.process_potential_bump(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # some bots edit their reply in after fetching an embed, harmless no-op otherwise
        await self.process_potential_bump(after)

    @tasks.loop(seconds=15)
    async def check_bump_reminders(self):
        now = discord.utils.utcnow().timestamp()

        async with aiosqlite.connect(common.DB_FILE) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM bump_reminders WHERE fire_at <= ? AND notified = 0", (now,)
            ) as cursor:
                due = await cursor.fetchall()

            for row in due:
                guild = self.bot.get_guild(row["guild_id"])
                channel = self.bot.get_channel(row["channel_id"])

                if channel is not None:
                    role = (
                        discord.utils.get(guild.roles, name=BUMPER_ROLE_NAME)
                        if guild
                        else None
                    )
                    mention = role.mention if role else f"`@{BUMPER_ROLE_NAME}`"
                    try:
                        await channel.send(
                            f"{mention} its time to bump with **{row['service']}**!"
                        )
                    except discord.Forbidden:
                        pass

                await db.execute(
                    "DELETE FROM bump_reminders WHERE guild_id = ? AND service = ?",
                    (row["guild_id"], row["service"]),
                )

            await db.commit()

    @check_bump_reminders.before_loop
    async def before_check_bump_reminders(self):
        await self.bot.wait_until_ready()


def setup(bot):
    bot.add_cog(Bump(bot))