"""Логи: удалённые и изменённые сообщения, входы/выходы, баны, смена ников."""

import time
from typing import Optional

import discord
from discord.ext import commands

from utils.helpers import COLOR_NEG, COLOR_NEUTRAL, COLOR_OK, clip, mk_embed, send_log


class EventsCog(commands.Cog):
    """Слушатели событий для лог-канала."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._cache: dict = {}  # message.id -> (автор, текст)
        self._purge_suppress_until: dict = {}  # channel.id -> тайм-стамп тишины

    # --------------------------------------------------------------- хелперы

    def suppress_delete(self, channel_id: int, seconds: float = 6.0) -> None:
        """Не логировать удаление сообщений в канале (использует команда purge)."""
        self._purge_suppress_until[channel_id] = time.monotonic() + seconds
        if len(self._purge_suppress_until) > 200:
            stale = [
                key
                for key, value in self._purge_suppress_until.items()
                if value < time.monotonic()
            ]
            for key in stale:
                self._purge_suppress_until.pop(key, None)

    def _is_suppressed(self, channel_id: int) -> bool:
        until = self._purge_suppress_until.get(channel_id)
        if until is None:
            return False
        if time.monotonic() > until:
            self._purge_suppress_until.pop(channel_id, None)
            return False
        return True

    @staticmethod
    async def _find_actor(guild, action, target_id: int):
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if getattr(entry.target, "id", None) == target_id:
                    return entry.user, entry.reason
        except (discord.Forbidden, discord.HTTPException):
            pass
        return None, None

    # ------------------------------------------------------------- сообщения

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        self._cache[message.id] = (str(message.author), message.content or "")
        if len(self._cache) > 5000:
            for key in list(self._cache)[:1500]:
                self._cache.pop(key, None)

    @commands.Cog.listener()
    async def on_message_delete(self, message: Optional[discord.Message]) -> None:
        if message is None:
            return
        guild = message.guild
        if guild is None or self._is_suppressed(message.channel.id):
            return
        cached_author, cached_content = self._cache.pop(message.id, ("неизвестно", ""))
        author_line = f"{getattr(message.author, 'mention', '')} `{message.author}`" if message.author is not None else cached_author
        embed = mk_embed("🗑 Сообщение удалено", color=COLOR_NEG)
        embed.add_field(name="Канал", value=getattr(message.channel, "mention", "—"), inline=True)
        embed.add_field(name="Автор", value=author_line or "неизвестно", inline=True)
        content = message.content or cached_content
        if content:
            embed.add_field(name="Сообщение", value=clip(content), inline=False)
        if message.attachments:
            names = ", ".join(attachment.filename for attachment in message.attachments)
            embed.add_field(name="Файлы", value=clip(names, 256), inline=False)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: Optional[discord.Message], after: discord.Message) -> None:
        if before is None or after is None:
            return
        guild = after.guild
        if guild is None or after.author.bot:
            return
        if (before.content or "") == (after.content or ""):
            return
        embed = mk_embed("✏️ Сообщение изменено", color=COLOR_NEUTRAL)
        embed.add_field(name="Канал", value=getattr(after.channel, "mention", "—"), inline=True)
        embed.add_field(name="Автор", value=f"{getattr(after.author, 'mention', '')} `{after.author}`", inline=True)
        embed.add_field(name="До", value=clip(before.content) or "—", inline=False)
        embed.add_field(name="После", value=clip(after.content) or "—", inline=False)
        embed.add_field(name="Ссылка", value=after.jump_url, inline=False)
        await send_log(guild, embed)

    # ------------------------------------------------------------- участники

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        embed = mk_embed("📥 Участник зашёл", color=COLOR_OK)
        embed.add_field(name="Участник", value=f"{member.mention} `{member}`", inline=False)
        created_at = getattr(member, "created_at", None) or getattr(member.user, "created_at", None)
        if created_at is not None:
            embed.add_field(
                name="Аккаунт создан",
                value=discord.utils.format_dt(created_at, style="D"),
                inline=True,
            )
        embed.add_field(name="Всего участников", value=str(member.guild.member_count), inline=True)
        await send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if member.bot:
            return
        embed = mk_embed("📤 Участник вышел", color=COLOR_NEUTRAL)
        embed.add_field(name="Участник", value=f"`{member}`", inline=False)
        if member.joined_at is not None:
            embed.add_field(
                name="Пробыл с",
                value=discord.utils.format_dt(member.joined_at, style="D"),
                inline=True,
            )
        embed.add_field(name="Всего участников", value=str(member.guild.member_count), inline=True)
        await send_log(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.nick == after.nick:
            return  # таймауты логируются в командах и автомодерации
        embed = mk_embed("✏️ Смена ника", color=COLOR_NEUTRAL)
        embed.add_field(name="Участник", value=f"{after.mention} `{after}`", inline=False)
        embed.add_field(name="Было", value=before.nick or "—", inline=True)
        embed.add_field(name="Стало", value=after.nick or "—", inline=True)
        await send_log(after.guild, embed)

    # ----------------------------------------------------------------- баны

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user) -> None:
        actor, reason = await self._find_actor(guild, discord.AuditLogAction.ban, user.id)
        embed = mk_embed("🔨 Участник забанен", color=COLOR_NEG)
        embed.add_field(name="Участник", value=f"{getattr(user, 'mention', '')} `{user}`", inline=False)
        embed.add_field(
            name="Модератор",
            value=(getattr(actor, "mention", None) or str(actor)) if actor else "неизвестно",
            inline=False,
        )
        if reason:
            embed.add_field(name="Причина", value=clip(reason), inline=False)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user) -> None:
        actor, _reason = await self._find_actor(guild, discord.AuditLogAction.unban, user.id)
        embed = mk_embed("🔓 Участник разбанен", color=COLOR_OK)
        embed.add_field(name="Участник", value=f"{getattr(user, 'mention', '')} `{user}`", inline=False)
        embed.add_field(
            name="Модератор",
            value=(getattr(actor, "mention", None) or str(actor)) if actor else "неизвестно",
            inline=False,
        )
        await send_log(guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EventsCog(bot))
