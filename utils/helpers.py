"""Общие утилиты: разбор времени, иерархия, эмбеды и отправка в лог-канал."""

import datetime
import re
from typing import Optional

import discord
import discord.ext.commands

import utils.attribution as _sig
import utils.settings as store

__author__ = _sig.handle()
__github__ = _sig.url()

COLOR_NEG = 0xED4245      # красный — баны, кик
COLOR_WARN = 0xFEE75C     # жёлтый — варны, автомодерация
COLOR_OK = 0x57F287       # зелёный — позитивные действия
COLOR_NEUTRAL = 0x5865F2  # размытая гамма — просто информация

MAX_TIMEOUT_SECONDS = 28 * 86400  # ограничение Discord на таймауты

_UNIT_TABLE = {
    "s": 1, "с": 1, "sec": 1, "сек": 1,
    "m": 60, "м": 60, "min": 60, "мин": 60,
    "h": 3600, "ч": 3600, "hour": 3600, "час": 3600,
    "d": 86400, "д": 86400, "day": 86400, "дн": 86400,
    "w": 604800, "н": 604800,
}
_TIME_RE = re.compile(r"(\d+)\s*([a-zа-я]+)?", re.IGNORECASE)


# ------------------------------------------------------------------- время

def parse_time(text: str) -> Optional[int]:
    """'30m' / '2h' / '1d 12h' / '1ч30м' -> секунды. None, если срок некорректный."""
    total = 0
    matched = False
    for value, unit in _TIME_RE.findall(text.lower().strip()):
        unit = (unit or "m").strip() or "m"
        multiplier = _UNIT_TABLE.get(unit)
        if multiplier is None:
            return None
        total += int(value) * multiplier
        matched = True
    if not matched or total <= 0:
        return None
    return total


def human_time(seconds: int) -> str:
    """1800 -> '30 мин'; 90000 -> '1 дн 1 ч'."""
    seconds = int(seconds)
    parts = []
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        parts.append(f"{days} дн")
    if hours:
        parts.append(f"{hours} ч")
    if minutes:
        parts.append(f"{minutes} мин")
    if seconds or not parts:
        parts.append(f"{seconds} с")
    return " ".join(parts)


def clip(text: Optional[str], limit: int = 1024) -> str:
    text = text or ""
    return text if len(text) <= limit - 3 else text[: limit - 3] + "…"


# ------------------------------------------------------------------- эмбеды

def mk_embed(title: Optional[str] = None, description: Optional[str] = None, color: int = COLOR_NEUTRAL) -> discord.Embed:
    embed = discord.Embed(title=title, description=description, color=color)
    embed.set_footer(text=_sig.tag())
    return embed


async def send_log(guild: discord.Guild, embed: discord.Embed) -> None:
    """Отправляет эмбед в настроенный лог-канал (если он есть)."""
    channel_id = store.get_settings(guild.id).get("log_channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except (discord.Forbidden, discord.HTTPException):
        pass  # нет прав / Discord отдыхает — не мешаем основному потоку


async def send_mod_log(guild, action: str, *, moderator, reason: str = "", color: int = COLOR_NEUTRAL, target=None, target_str: Optional[str] = None) -> None:
    """Стандартный эмбед в лог о действии модератора."""
    if target is not None:
        who = f"{getattr(target, 'mention', '')} `{target}`".strip()
    else:
        who = target_str or "—"
    moderator_txt = f"{getattr(moderator, 'mention', '')} `{moderator}`".strip()
    embed = mk_embed(f"🛠 {action}", color=color)
    embed.add_field(name="Кому", value=who, inline=False)
    embed.add_field(name="Модератор", value=moderator_txt or "—", inline=False)
    if reason:
        embed.add_field(name="Причина", value=clip(reason, 500), inline=False)
    embed.timestamp = discord.utils.utcnow()
    await send_log(guild, embed)


# -------------------------------------------------------- правила и действия

def hierarchy_failure(ctx: discord.ext.commands.Context, member) -> Optional[str]:
    """Нарушена ли иерархия ролей. Возвращает текст ошибки или None."""
    if member == ctx.author:
        return "⛔ Нельзя применить это к самому себе."
    if member.id == ctx.bot.user.id:
        return "🤖 Я не могу наказать сам себя."
    if member.id == ctx.guild.owner_id:
        return "👑 Нельзя наказывать владельца сервера."
    if ctx.author.id != ctx.guild.owner_id and member.top_role >= ctx.author.top_role:
        return "🔒 У цели роль не ниже твоей."
    if member.top_role >= ctx.guild.me.top_role:
        return "🔒 У цели роль не ниже роли бота. Подними роль бота выше."
    return None


async def dm_user(member, text: str) -> bool:
    """Пытается написать в личку, возвращает успех."""
    try:
        await member.send(text)
        return True
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return False


async def timeout_member(member, seconds: int, reason: str) -> bool:
    """Выдаёт таймаут с учётом лимита Discord. Возвращает успех."""
    seconds = max(1, min(int(seconds), MAX_TIMEOUT_SECONDS))
    try:
        await member.timeout(datetime.timedelta(seconds=seconds), reason=reason)
        return True
    except (discord.Forbidden, discord.HTTPException, AttributeError):
        return False
