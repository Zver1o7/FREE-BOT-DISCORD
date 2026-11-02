"""Приветствия, прощания и авто-роль.

By @Zver1o7 — https://github.com/Zver1o7
"""

__author__ = "@Zver1o7"
__github__ = "https://github.com/Zver1o7"

import discord
from discord.ext import commands

import utils.settings as store


class WelcomeCog(commands.Cog):
    """Реагирует на вход и выход участников."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    def _format(template: str, member: discord.Member) -> str:
        return (
            template.replace("{user}", member.mention)
            .replace("{username}", str(member))
            .replace("{name}", member.display_name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count))
        )

    @staticmethod
    async def _send_text(channel, text: str) -> None:
        try:
            await channel.send(text)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        settings = store.get_settings(member.guild.id)

        # Автороль
        role_id = settings.get("autorole_id")
        if role_id:
            role = member.guild.get_role(role_id)
            if (
                role is not None
                and not role.managed
                and role.position < member.guild.me.top_role.position
                and role not in member.roles
            ):
                try:
                    await member.add_roles(role, reason="Автороль при входе")
                except (discord.Forbidden, discord.HTTPException):
                    pass

        # Приветствие (ботов не встречаем булками текста)
        welcome = settings.get("welcome") or {}
        if member.bot:
            return
        channel_id = welcome.get("channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return
        await self._send_text(channel, self._format(str(welcome.get("message", "")), member))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        goodbye = store.get_settings(member.guild.id).get("goodbye") or {}
        channel_id = goodbye.get("channel_id")
        if not channel_id:
            return
        channel = member.guild.get_channel(channel_id)
        if channel is None:
            return
        await self._send_text(channel, self._format(str(goodbye.get("message", "")), member))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))
