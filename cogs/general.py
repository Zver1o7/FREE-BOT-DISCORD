"""Информация: help, ping, serverinfo, userinfo, avatar, ссылка-приглашение."""

from typing import Optional

import discord
from discord.ext import commands

import utils.attribution as _sig
import utils.settings as store
from utils import __version__ as BOT_VERSION
from utils.helpers import COLOR_NEUTRAL, mk_embed


class GeneralCog(commands.Cog):
    """Команды информации."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command(name="help", description="Список команд бота")
    async def help_command(self, ctx: commands.Context) -> None:
        prefix = "!"
        if ctx.guild is not None:
            try:
                prefix = store.get_settings(ctx.guild.id)["prefix"]
            except Exception:
                prefix = "!"

        groups: dict = {}
        for command in self.bot.commands:
            if command.hidden:
                continue
            category = getattr(command, "category", "Прочее")
            groups.setdefault(category, []).append(command)

        order = ["Модерация", "Автомодерация", "Щит", "Розыгрыши", "Настройки", "Сервер", "Тикеты"]
        embed = mk_embed(
            "📖 Команды бота",
            description=(
                "Каждая команда работает и как слэш (`/команда`), "
                f"и через префикс (`{prefix}команда`)."
            ),
        )
        shown = set()
        for category in order:
            items = groups.get(category)
            if not items:
                continue
            shown.add(category)
            lines = [
                f"`/{cmd.name}` — {getattr(cmd, 'description', None) or cmd.brief or ''}"
                for cmd in items
            ]
            embed.add_field(name=category, value="\n".join(lines), inline=False)
        for category, items in sorted(groups.items()):
            if category in shown:
                continue
            lines = [
                f"`/{cmd.name}` — {getattr(cmd, 'description', None) or cmd.brief or ''}"
                for cmd in items
            ]
            embed.add_field(name=category, value="\n".join(lines), inline=False)
        embed.set_footer(text=_sig.tag())
        await ctx.send(embed=embed)
    help_command.category = "Сервер"

    @commands.hybrid_command(name="ping", description="Понг!")
    async def ping(self, ctx: commands.Context) -> None:
        await ctx.send(f"🏓 Понг! Задержка: **{self.bot.latency * 1000:.0f} мс**")
    ping.category = "Сервер"

    @commands.hybrid_command(name="invite", description="Ссылка для добавления бота на сервер")
    async def invite(self, ctx: commands.Context) -> None:
        application_id = self.bot.application_id or (self.bot.user.id if self.bot.user else None)
        if not application_id:
            await ctx.send("⏳ Сервисная информация ещё не загружена, попробуй через полминуты.")
            return
        url = (
            f"https://discord.com/api/oauth2/authorize?client_id={application_id}"
            "&permissions=8&scope=bot%20applications.commands"
        )
        embed = mk_embed("🔗 Добавить бота", description=f"[Клик — и бот на сервере]({url})")
        await ctx.send(embed=embed)
    invite.category = "Сервер"

    @commands.hybrid_command(name="about", description="О боте: версия и автор")
    async def about(self, ctx: commands.Context) -> None:
        embed = mk_embed(
            "🤖 О боте",
            description=(
                f"**Discord Admin Bot v{BOT_VERSION}**\n"
                "Модерация, автомодерация, щит сервера, логи, приветствия, тикеты."
            ),
        )
        embed.add_field(name="Автор", value=f"{_sig.handle()} ({_sig.url()})", inline=False)
        embed.add_field(name="Что нового", value="Полная история — в файле CHANGELOG.md.", inline=False)
        await ctx.send(embed=embed)
    about.category = "Сервер"

    @commands.hybrid_command(name="serverinfo", description="Информация о сервере")
    @commands.guild_only()
    async def serverinfo(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        embed = mk_embed(f"🖥 {guild.name}", color=COLOR_NEUTRAL)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        created = f"📅 Создан: {discord.utils.format_dt(guild.created_at, style='D')}"
        embed.description = created
        embed.add_field(name="Владелец", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Участников", value=str(guild.member_count), inline=True)
        embed.add_field(name="Ролей", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Текстовых каналов", value=str(len(guild.text_channels)), inline=True)
        embed.add_field(name="Голосовых каналов", value=str(len(guild.voice_channels)), inline=True)
        embed.add_field(
            name="Бусты",
            value=f"уровень {guild.premium_tier}, бустов: {guild.premium_subscription_count}",
            inline=True,
        )
        await ctx.send(embed=embed)
    serverinfo.category = "Сервер"

    @commands.hybrid_command(name="userinfo", description="Информация об участнике")
    @commands.guild_only()
    async def userinfo(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        member = member or ctx.author
        warn_entries = store.get_user_warnings(ctx.guild.id, member.id)

        roles = [role.mention for role in reversed(member.roles) if not role.is_default()][:15]
        created_at = getattr(member, "created_at", None) or getattr(member.user, "created_at", None)
        embed = mk_embed(color=COLOR_NEUTRAL)
        embed.set_author(name=f"{member.display_name}", icon_url=member.display_avatar.url)
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Участник", value=f"{member.mention}\n`{member}`", inline=True)
        embed.add_field(name="ID", value=str(member.id), inline=True)
        embed.add_field(name="Бот?", value="да" if member.bot else "нет", inline=True)
        if created_at is not None:
            embed.add_field(
                name="Регистрация",
                value=discord.utils.format_dt(created_at, style="D"),
                inline=True,
            )
        if member.joined_at is not None:
            embed.add_field(
                name="Вошёл",
                value=discord.utils.format_dt(member.joined_at, style="D"),
                inline=True,
            )
        embed.add_field(name="Роли", value=", ".join(roles) or "—", inline=False)
        embed.add_field(name="Предупреждения", value=str(len(warn_entries)), inline=True)
        if member.timed_out_until is not None:
            embed.add_field(
                name="Таймаут до",
                value=discord.utils.format_dt(member.timed_out_until, style="f"),
                inline=True,
            )
        else:
            embed.add_field(name="Таймаут", value="нет", inline=True)
        await ctx.send(embed=embed)
    userinfo.category = "Сервер"

    @commands.hybrid_command(name="avatar", description="Аватар участника")
    @commands.guild_only()
    async def avatar(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        member = member or ctx.author
        embed = mk_embed(f"🖼 Аватар {member.display_name}", color=COLOR_NEUTRAL)
        embed.set_image(url=member.display_avatar.url)
        await ctx.send(embed=embed)
    avatar.category = "Сервер"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GeneralCog(bot))
