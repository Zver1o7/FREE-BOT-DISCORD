"""Щит сервера: верификация кнопкой, антирейд, статистика."""

import time
from collections import deque
from typing import Deque

import discord
from discord.ext import commands

import utils.settings as store
from utils.helpers import COLOR_NEG, COLOR_NEUTRAL, COLOR_OK, clip, mk_embed, send_log


class VerifyView(discord.ui.View):
    """Кнопка верификации. timeout=None + custom_id = переживает рестарт бота."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Я не бот ✅", style=discord.ButtonStyle.success, custom_id="shield_verify_v1")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        role_id = store.get_settings(guild.id)["verify"].get("role_id")
        if not role_id:
            await interaction.response.send_message("❌ Верификация не настроена.", ephemeral=True)
            return
        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message("❌ Роль верификации удалена — позови админа.", ephemeral=True)
            return
        if role in member.roles:
            await interaction.response.send_message("ℹ️ Ты уже верифицирован.", ephemeral=True)
            return
        if role.managed or role.position >= guild.me.top_role.position:
            await interaction.response.send_message("❌ Не могу выдать роль (роль бота ниже). Позови админа.", ephemeral=True)
            return
        try:
            await member.add_roles(role, reason="Верификация кнопкой")
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message("❌ Не вышло выдать роль.", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Готово, {member.mention}! Доступ открыт.", ephemeral=True)
        embed = mk_embed("✅ Верификация", color=COLOR_OK)
        embed.add_field(name="Участник", value=f"{member.mention} `{member}`", inline=False)
        embed.add_field(name="Роль", value=role.mention, inline=True)
        await send_log(guild, embed)


class ShieldCog(commands.Cog):
    """Верификация, антирейд и статистика сервера."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self._joins: Deque[float] = deque()
        self._last_alert = 0.0

    async def cog_load(self) -> None:
        # Постоянная вьюха: кнопка работает и после перезапуска бота.
        self.bot.add_view(VerifyView(self.bot))

    # ---------------------------------------------------------- верификация

    @commands.hybrid_command(name="verifysetup", description="Настроить верификацию кнопкой")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def verifysetup(self, ctx: commands.Context, channel: discord.TextChannel, role: discord.Role) -> None:
        if role.is_default() or role.managed:
            await ctx.send("❌ Нужна обычная роль (не @everyone и не от интеграции).")
            return
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Эта роль не ниже моей. Подними роль бота выше в списке ролей.")
            return
        settings = store.get_settings(ctx.guild.id)
        settings["verify"]["channel_id"] = channel.id
        settings["verify"]["role_id"] = role.id
        store.save_settings(ctx.guild.id, settings)
        embed = mk_embed(
            "🎫 Верификация",
            description=f"Нажми кнопку ниже, чтобы получить роль {role.mention} и открыть доступ к серверу.",
        )
        try:
            message = await channel.send(embed=embed, view=VerifyView(self.bot))
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send("❌ Не могу писать в этот канал (проверь права).")
            return
        settings["verify"]["message_id"] = message.id
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Верификация настроена: {channel.mention} → {role.mention}.")
    verifysetup.category = "Щит"

    @commands.hybrid_command(name="verifyoff", description="Выключить верификацию")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def verifyoff(self, ctx: commands.Context) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["verify"] = {"channel_id": None, "role_id": None, "message_id": None}
        store.save_settings(ctx.guild.id, settings)
        await ctx.send("✅ Верификация выключена (старое сообщение с кнопкой можно удалить вручную).")
    verifyoff.category = "Щит"

    # ------------------------------------------------------------- антирейд

    @commands.hybrid_command(name="antiraid", description="Антирейд: on | off | status")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antiraid(self, ctx: commands.Context, state: str = "status") -> None:
        state = state.strip().lower()
        settings = store.get_settings(ctx.guild.id)
        if state in ("on", "вкл", "1"):
            settings["antiraid"]["enabled"] = True
            store.save_settings(ctx.guild.id, settings)
            await ctx.send("🛡 Антирейд **включён**.")
        elif state in ("off", "выкл", "0"):
            settings["antiraid"]["enabled"] = False
            store.save_settings(ctx.guild.id, settings)
            await ctx.send("🛡 Антирейд **выключен**.")
        elif state == "status":
            enabled = settings["antiraid"].get("enabled")
            days = settings["antiraid"].get("min_age_days", 0)
            await ctx.send(f"🛡 Антирейд: {'вкл ✅' if enabled else 'выкл ❌'}, минимальный возраст аккаунта: {days} дн.")
        else:
            await ctx.send("❌ Состояние: `on`, `off` или `status`.")
    antiraid.category = "Щит"

    @commands.hybrid_command(name="antiraidage", description="Минимальный возраст аккаунта в днях (0 — выкл)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def antiraidage(self, ctx: commands.Context, days: commands.Range[int, 0, 365]) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["antiraid"]["min_age_days"] = int(days)
        store.save_settings(ctx.guild.id, settings)
        await ctx.send("✅ Минимальный возраст аккаунта: 0 — проверка по возрасту выключена." if days == 0 else f"✅ Аккаунты младше {days} дн. будут кикаться при входе.")
    antiraidage.category = "Щит"

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if member.bot:
            return
        now = time.monotonic()
        self._joins.append(now)
        while self._joins and now - self._joins[0] > 120:
            self._joins.popleft()

        # Детектор волны входов (возможный рейд) — только алерт в лог.
        if len(self._joins) >= 10 and now - self._last_alert > 600:
            self._last_alert = now
            embed = mk_embed("🚨 Подозрение на рейд", color=COLOR_NEG)
            embed.add_field(name="Входов за 2 минуты", value=str(len(self._joins)), inline=True)
            embed.add_field(name="Что делать", value="Проверь журнал аудита. При подтверждении — `/lock`, бан волны через `/ban`.", inline=False)
            await send_log(member.guild, embed)

        antiraid = store.get_settings(member.guild.id)["antiraid"]
        if not antiraid.get("enabled"):
            return
        min_age = int(antiraid.get("min_age_days", 0) or 0)
        if min_age <= 0:
            return
        age_days = (discord.utils.utcnow() - discord.utils.snowflake_time(member.id)).days
        if age_days >= min_age:
            return
        try:
            await member.kick(reason=f"Антирейд: аккаунту {age_days} дн. (минимум {min_age})")
        except (discord.Forbidden, discord.HTTPException):
            return
        embed = mk_embed("🛡 Антирейд: кик", color=COLOR_NEG)
        embed.add_field(name="Участник", value=f"`{member}`", inline=False)
        embed.add_field(name="Возраст аккаунта", value=f"{age_days} дн. (минимум {min_age})", inline=True)
        await send_log(member.guild, embed)

    # ------------------------------------------------------------ статистика

    @commands.hybrid_command(name="stats", description="Статистика сервера")
    @commands.guild_only()
    async def stats(self, ctx: commands.Context) -> None:
        guild = ctx.guild
        now = discord.utils.utcnow()
        settings = store.get_settings(guild.id)

        warn_map = store.get_all_warnings(guild.id)
        total_warns = sum(len(entries) for entries in warn_map.values() if isinstance(entries, list))
        top = sorted(
            ((user_id, len(entries)) for user_id, entries in warn_map.items() if isinstance(entries, list) and entries),
            key=lambda item: item[1],
            reverse=True,
        )[:5]
        top_lines = [f"<@{user_id}> — {count}" for user_id, count in top] or ["—"]

        tempbans = [entry for entry in store.get_tempbans() if int(entry.get("guild_id", 0)) == guild.id]
        newcomers = sum(
            1
            for member in guild.members
            if member.joined_at is not None and (now - member.joined_at).days < 7
        )

        automod = settings["automod"]
        enabled_filters = [
            name
            for name, key in (
                ("спам", "anti_spam"),
                ("инвайты", "invites"),
                ("ссылки", "links"),
                ("слова", "bad_words"),
                ("капс", "caps"),
                ("упоминания", "mention_spam"),
            )
            if automod.get(key)
        ]
        antiraid = settings["antiraid"]
        verify_role = guild.get_role(settings["verify"].get("role_id") or 0)

        embed = mk_embed(f"📊 Статистика: {guild.name}", color=COLOR_NEUTRAL)
        embed.add_field(name="Участников", value=str(guild.member_count), inline=True)
        embed.add_field(name="Новичков за 7 дней", value=str(newcomers), inline=True)
        embed.add_field(name="Варнов всего", value=str(total_warns), inline=True)
        embed.add_field(name="Топ нарушителей", value="\n".join(top_lines), inline=False)
        embed.add_field(name="Активных темпбанов", value=str(len(tempbans)), inline=True)
        embed.add_field(name="Автомодерация", value=", ".join(enabled_filters) or "выключена", inline=True)
        embed.add_field(
            name="Щит",
            value=f"верификация: {verify_role.mention if verify_role else '—'}, "
            f"антирейд: {'вкл' if antiraid.get('enabled') else 'выкл'}",
            inline=False,
        )
        await ctx.send(embed=embed)
    stats.category = "Щит"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ShieldCog(bot))
