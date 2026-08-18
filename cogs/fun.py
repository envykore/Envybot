from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import bridge, commands

SPAM_WINDOW_SECONDS = 6
SPAM_MESSAGE_THRESHOLD = 5
SPAM_MUTE_SECONDS = 60

NUMBERS = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]


class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.recent_messages = defaultdict(deque)  # {(guild_id, user_id): deque(ts)}

    @bridge.bridge_command(name="poll")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def poll(
        self,
        ctx,
        question: str,
        opt1: str | None = None,
        opt2: str | None = None,
        opt3: str | None = None,
        opt4: str | None = None,
        opt5: str | None = None,
        opt6: str | None = None,
        opt7: str | None = None,
        opt8: str | None = None,
        opt9: str | None = None,
        opt10: str | None = None,
    ):
        options = [
            o
            for o in (opt1, opt2, opt3, opt4, opt5, opt6, opt7, opt8, opt9, opt10)
            if o
        ]

        if not options:
            embed = discord.Embed(title=question, color=0x5865F2)
            msg = await ctx.respond(embed=embed)
            await msg.add_reaction("👍")
            await msg.add_reaction("👎")
            return

        desc = "".join(f"{NUMBERS[i]} {opt}\n" for i, opt in enumerate(options))
        embed = discord.Embed(title=question, description=desc, color=0x5865F2)
        msg = await ctx.respond(embed=embed)
        for i in range(len(options)):
            await msg.add_reaction(NUMBERS[i])

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return

        key = (message.guild.id, message.author.id)
        now = discord.utils.utcnow().timestamp()
        dq = self.recent_messages[key]
        dq.append(now)
        while dq and now - dq[0] > SPAM_WINDOW_SECONDS:
            dq.popleft()

        if len(dq) < SPAM_MESSAGE_THRESHOLD:
            return

        dq.clear()
        member = message.author
        if (
            isinstance(member, discord.Member)
            and not member.guild_permissions.manage_messages
        ):
            try:
                until = discord.utils.utcnow() + timedelta(seconds=SPAM_MUTE_SECONDS)
                await member.timeout(until, reason="Automatic: message spam")
                warning = await message.channel.send(
                    f"{member.mention} muted for {SPAM_MUTE_SECONDS}s (spam detected)"
                )
                await warning.delete(delay=5)
            except discord.Forbidden:
                pass


def setup(bot):
    bot.add_cog(Fun(bot))