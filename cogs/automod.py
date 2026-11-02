"""Автомодерация: спам, инвайты, ссылки, запрещённые слова, капс, упоминания."""

import re
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

import discord
from discord.ext import commands

import utils.settings as store
from utils.helpers import COLOR_WARN, clip, human_time, mk_embed, send_log, timeout_member

INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord(?:app)?\.com/invite/|discord\.gg/)[\w-]+",
    re.IGNORECASE,
)
LINK_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

TOGGLES = {
    "спам": "anti_spam", "spam": "anti_spam", "анти-спам": "anti_spam",
    "инвайты": "invites", "приглашения": "invites", "invites": "invites",
    "ссылки": "links", "links": "links",
    "слова": "bad_words", "мат": "bad_words", "words": "bad_words",
    "капс": "caps", "caps": "caps",
    "упоминания": "mention_spam", "mentions": "mention_spam",
}
ON_VALUES = {"on", "вкл", "1", "true", "да"}
OFF_VALUES = {"off", "выкл", "0", "false", "нет"}


class AutoModCog(commands.Cog):
    """Слушает сообщения и наказывает за нарушения."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._spam_windows: Dict[Tuple[int, int], Deque[float]] = {}
        self._strikes: Dict[Tuple[int, int], Deque[float]] = {}
        self._last_punish: Dict[Tuple[int, int], float] = {}

    # --------------------------------------------------------------- команды

    @commands.hybrid_command(name="automod", description="Вкл/выкл фильтр автомодерации")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automod(self, ctx: commands.Context, feature: str, state: str = "on") -> None:
        key = TOGGLES.get(feature.strip().lower())
        if key is None:
            await ctx.send("❌ Неизвестный фильтр. Доступно: **спам, инвайты, ссылки, слова, капс, упоминания**.")
            return
        state_value = state.strip().lower()
        if state_value in ON_VALUES:
            enabled = True
        elif state_value in OFF_VALUES:
            enabled = False
        else:
            await ctx.send("❌ Состояние: `on` или `off`.")
            return
        settings = store.get_settings(ctx.guild.id)
        settings["automod"][key] = enabled
        store.save_settings(ctx.guild.id, settings)
        emoji = "✅" if enabled else "❌"
        await ctx.send(f"{emoji} Автомодерация · `{key}` — {'вкл' if enabled else 'выкл'}.")
    automod.category = "Автомодерация"

    @commands.hybrid_command(name="automodignore", description="Канал, где автомодерация не работает")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def automodignore(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        settings = store.get_settings(ctx.guild.id)
        ignored = settings["automod"]["ignored_channels"]
        if channel.id in ignored:
            ignored.remove(channel.id)
            store.save_settings(ctx.guild.id, settings)
            await ctx.send(f"👀 Канал {channel.mention} снова под автомодерацией.")
        else:
            ignored.append(channel.id)
            store.save_settings(ctx.guild.id, settings)
            await ctx.send(f"🙈 Канал {channel.mention} исключён из автомодерации.")
    automodignore.category = "Автомодерация"

    @commands.hybrid_command(name="addbadword", description="Добавить слово в фильтр автомодерации")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def addbadword(self, ctx: commands.Context, word: str) -> None:
        word = word.strip().lower()
        if not word:
            await ctx.send("❌ Пустое слово.")
            return
        settings = store.get_settings(ctx.guild.id)
        words = settings["automod"]["badwords"]
        if word in words:
            await ctx.send(f"ℹ️ Слово `{word}` уже в списке.")
            return
        words.append(word)
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Слово `{word}` добавлено в фильтр.")
    addbadword.category = "Автомодерация"

    @commands.hybrid_command(name="removebadword", description="Убрать слово из фильтра")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def removebadword(self, ctx: commands.Context, word: str) -> None:
        word = word.strip().lower()
        settings = store.get_settings(ctx.guild.id)
        words = settings["automod"]["badwords"]
        if word not in words:
            await ctx.send(f"ℹ️ Слово `{word}` в списке не найдено (`/badwords`, чтобы посмотреть).")
            return
        words.remove(word)
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Слово `{word}` убрано из фильтра.")
    removebadword.category = "Автомодерация"

    @commands.hybrid_command(name="badwords", description="Список запрещённых слов")
    @commands.guild_only()
    async def badwords(self, ctx: commands.Context) -> None:
        words = store.get_settings(ctx.guild.id)["automod"]["badwords"]
        if words:
            text = ", ".join(f"`{word}`" for word in words)
        else:
            text = "— список пуст. Добавить: `/addbadword слово`."
        await ctx.send(f"🚫 Запрещённые слова: {text}")
    badwords.category = "Автомодерация"

    # ------------------------------------------------------------- слушатели

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or message.author.bot or message.webhook_id is not None:
            return
        author = message.author
        if not isinstance(author, discord.Member):
            return
        if author.guild_permissions.administrator or author.guild_permissions.manage_messages:
            return  # модераторов не фильтруем

        channel = message.channel
        bot_perms = channel.permissions_for(guild.me)
        if not bot_perms.manage_messages:
            return  # даже удалить сообщение не можем — молчим

        automod = store.get_settings(guild.id)["automod"]
        if channel.id in automod["ignored_channels"]:
            return

        content = message.content or ""
        violation: Optional[str] = None
        if automod["invites"] and INVITE_RE.search(content):
            violation = "ссылка-приглашение"
        elif automod["links"] and LINK_RE.search(content):
            violation = "ссылка"
        elif automod["bad_words"] and automod["badwords"] and self._has_badword(content, automod["badwords"]):
            violation = "запрещённое слово"
        elif automod["caps"] and self._too_many_caps(content):
            violation = "чрезмерный капс"
        elif automod["mention_spam"] and len(message.mentions) >= int(automod["max_mentions"] or 5):
            violation = "спам упоминаниями"
        elif automod["anti_spam"] and self._is_spam(guild.id, author.id, automod):
            violation = "спам"

        if violation is None:
            return

        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await self._register_violation(guild, author, message, violation, automod)

    # --------------------------------------------------------- внутренности

    @staticmethod
    def _has_badword(content: str, words) -> bool:
        lowered = content.lower()
        for word in words:
            word = str(word).lower()
            if not word:
                continue
            try:
                if re.search(rf"\b{re.escape(word)}\b", lowered):
                    return True
            except re.error:
                if word in lowered:
                    return True
        return False

    @staticmethod
    def _too_many_caps(content: str) -> bool:
        letters = [char for char in content if char.isalpha()]
        if len(content) < 10 or len(letters) < 8:
            return False
        uppercase = sum(1 for char in letters if char.isupper())
        return uppercase >= 8 and uppercase / len(letters) >= 0.7

    def _is_spam(self, guild_id: int, user_id: int, automod: dict) -> bool:
        now = time.monotonic()
        key = (guild_id, user_id)
        if len(self._spam_windows) > 2000:
            self._prune_windows(now)
        window_seconds = int(automod.get("anti_spam_seconds", 5) or 5)
        limit = int(automod.get("anti_spam_messages", 6) or 6)
        timestamps = self._spam_windows.setdefault(key, deque())
        timestamps.append(now)
        while timestamps and now - timestamps[0] > window_seconds:
            timestamps.popleft()
        if len(timestamps) > limit:
            timestamps.clear()
            return True
        return False

    def _prune_windows(self, now: float) -> None:
        for key in list(self._spam_windows):
            timestamps = self._spam_windows[key]
            if not timestamps or now - timestamps[-1] > 120:
                del self._spam_windows[key]

    async def _register_violation(self, guild, member: discord.Member, message: discord.Message, violation: str, automod: dict) -> None:
        key = (guild.id, member.id)
        now = time.monotonic()

        # не наказываем одного участника каждые 20 секунд без конца
        if now - self._last_punish.get(key, 0) < 20:
            return
        self._last_punish[key] = now

        strikes = self._strikes.setdefault(key, deque())
        strikes.append(now)
        while strikes and now - strikes[0] > 300:
            strikes.popleft()
        strike_count = len(strikes)

        warn_count = store.add_warning(guild.id, member.id, "Автомодерация", self.bot.user.id, f"Автомод: {violation}")
        warn_limit = int(store.get_settings(guild.id).get("warn_limit", 5) or 5)

        embed = mk_embed("🤖 Автомодерация", color=COLOR_WARN)
        embed.add_field(name="Участник", value=f"{member.mention} `{member}`", inline=False)
        embed.add_field(name="Причина", value=violation, inline=True)
        embed.add_field(name="Канал", value=getattr(message.channel, "mention", "—"), inline=True)
        if message.content:
            embed.add_field(name="Сообщение", value=clip(message.content, 300), inline=False)
        embed.add_field(name="Предупреждений всего", value=f"{warn_count} (лимит {warn_limit})", inline=True)
        embed.add_field(name="Нарушений за 5 минут", value=str(strike_count), inline=True)

        if strike_count >= 3 or warn_count >= warn_limit:
            strikes.clear()
            seconds = int(automod.get("timeout_seconds", 600) or 600)
            if seconds > 0 and message.channel.permissions_for(guild.me).moderate_members:
                if await timeout_member(member, seconds, f"Автомод: {violation}"):
                    embed.add_field(name="Мера", value=f"Таймаут на {human_time(seconds)}", inline=False)
        await send_log(guild, embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoModCog(bot))
