"""Тикеты: приватный тред на запрос пользователя.

By @Zver1o7 — https://github.com/Zver1o7
"""

__author__ = "@Zver1o7"
__github__ = "https://github.com/Zver1o7"

import discord
from discord.ext import commands

from utils.helpers import COLOR_NEUTRAL, mk_embed

TICKET_PREFIX = "ticket-"


class TicketsCog(commands.Cog):
    """Простая система тикетов на приватных тредах."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="ticket", description="Создать тикет (приватный тред)")
    @commands.guild_only()
    @commands.cooldown(1, 60, commands.BucketType.member)
    async def ticket(self, ctx: commands.Context, *, reason: str = "Без описания") -> None:
        my_id = ctx.author.id
        thread_prefix = f"{TICKET_PREFIX}{my_id}"
        for existing in ctx.guild.threads:
            if existing.name.startswith(thread_prefix) and not existing.archived:
                await ctx.send(f"ℹ️ У тебя уже открыт тикет: {existing.mention}")
                return
        channel = ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Тикет можно создать только в обычном текстовом канале.")
            return
        bot_perms = channel.permissions_for(ctx.guild.me)
        if not bot_perms.create_private_threads:
            await ctx.send("⚠️ Мне не хватает права `создавать приватные треды` в этом канале.")
            return
        try:
            thread = await channel.create_thread(
                name=thread_prefix,
                type=discord.ChannelType.private_thread,
                reason=f"Тикет от {ctx.author} | {reason}",
            )
        except discord.HTTPException:
            await ctx.send("❌ Не удалось создать тред, попробуй позже.")
            return
        try:
            await thread.add_user(ctx.author)
        except discord.HTTPException:
            pass  # тред всё равно создан, просто без приглашения

        embed = mk_embed(
            "🎫 Тикет создан",
            description=(
                f"Причина: **{reason}**\n"
                "Опиши здесь свою проблему — подсоединённая поддержка ответит в этом треде.\n"
                "Закрыть тикет: `/ticketclose`."
            ),
            color=COLOR_NEUTRAL,
        )
        try:
            await thread.send(content=f"{ctx.author.mention}", embed=embed)
        except discord.HTTPException:
            pass
        await ctx.send(f"✅ Тикет создан: {thread.mention}")
    ticket.category = "Тикеты"

    @commands.hybrid_command(name="ticketclose", description="Закрыть тикет (внутри треда тикета)")
    @commands.guild_only()
    async def ticketclose(self, ctx: commands.Context, *, reason: str = "") -> None:
        thread = ctx.channel
        if not isinstance(thread, discord.Thread) or thread.owner_id != self.bot.user.id or not thread.name.startswith(TICKET_PREFIX):
            await ctx.send("❌ Эту команду нужно писать внутри треда тикета.")
            return
        owns_ticket = self._ticket_user_id(thread.name) == ctx.author.id
        can_manage = ctx.author.guild_permissions.manage_threads
        if not (owns_ticket or can_manage):
            await ctx.send("⛔ Закрыть тикет может его создатель или модератор (`управление тредами`).")
            return
        try:
            await thread.edit(locked=True, archived=True, reason=f"{ctx.author} | {reason or 'Тикет закрыт'}")
        except discord.HTTPException:
            await ctx.send("❌ Не удалось закрыть тикет.")
            return
        await ctx.send("✅ Тикет закрыт.")
    ticketclose.category = "Тикеты"

    @staticmethod
    def _ticket_user_id(thread_name: str) -> int:
        try:
            return int(thread_name.split("-", 1)[1])
        except (ValueError, IndexError):
            return 0


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketsCog(bot))
