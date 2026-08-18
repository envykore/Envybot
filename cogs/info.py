import discord
from discord.ext import bridge, commands


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @bridge.bridge_command(name="ping")
    async def ping(self, ctx):
        await ctx.respond(f"pong! {round(self.bot.latency * 1000)}ms")

    @bridge.bridge_command(name="userinfo")
    async def userinfo(self, ctx, member: discord.Member = None):
        member = member or ctx.author

        embed = discord.Embed(title=f"{member.display_name}'s Details", color=0x00AAFF)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Tag", value=str(member), inline=True)
        embed.add_field(
            name="Account Created",
            value=member.created_at.strftime("%b %d, %Y"),
            inline=True,
        )
        embed.add_field(
            name="Joined Server",
            value=member.joined_at.strftime("%b %d, %Y"),
            inline=True,
        )

        roles = [r.name for r in member.roles if r.name != "@everyone"]
        embed.add_field(
            name="Roles", value=", ".join(roles[:5]) if roles else "None", inline=False
        )

        await ctx.respond(embed=embed)

    @bridge.bridge_command(name="serverinfo")
    async def serverinfo(self, ctx):
        guild = ctx.guild
        embed = discord.Embed(title=guild.name, color=0xFFAA00)

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)

        embed.add_field(
            name="Owner",
            value=guild.owner.mention if guild.owner else "unknown",
            inline=True,
        )
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(
            name="Created", value=guild.created_at.strftime("%b %d, %Y"), inline=False
        )
        embed.set_footer(text=f"ID: {guild.id}")
        await ctx.respond(embed=embed)

    @bridge.bridge_command(name="roleinfo")
    async def roleinfo(self, ctx, *, role: discord.Role):
        embed = discord.Embed(title=role.name, color=role.color)
        embed.add_field(name="ID", value=str(role.id))
        embed.add_field(name="Members", value=str(len(role.members)))
        embed.add_field(name="Position", value=str(role.position))
        embed.add_field(name="Mentionable", value=str(role.mentionable))

        if role.permissions.administrator:
            perms = "Administrator"
        else:
            perms = ", ".join(
                p.replace("_", " ").title() for p, val in role.permissions if val
            )
            perms = perms or "None"

        embed.add_field(name="Permissions", value=perms[:1000], inline=False)
        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Info(bot))