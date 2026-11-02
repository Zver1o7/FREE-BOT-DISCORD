"""Настройки сервера: лог-канал, приветствия, автороль, префикс, лимит варнов."""

from typing import Optional

import discord
from discord.ext import commands

import utils.settings as store
from utils.helpers import COLOR_NEUTRAL, mk_embed


def _channel_text(guild: discord.Guild, channel_id: Optional[int]) -> str:
    if not channel_id:
        return "—"
    channel = guild.get_channel(channel_id)
    return channel.mention if channel is not None else "❓ (канал удалён)"


def _role_text(guild: discord.Guild, role_id: Optional[int]) -> str:
    if not role_id:
        return "—"
    role = guild.get_role(role_id)
    return role.mention if role is not None else "❓ (роль удалена)"


class ConfigCog(commands.Cog):
    """Команды настройки бота."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------ просмотр

    @commands.hybrid_command(name="config", description="Показать настройки бота на сервере")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def config(self, ctx: commands.Context) -> None:
        settings = store.get_settings(ctx.guild.id)
        automod = settings["automod"]
        lines = [
            f"**Префикс:** `{settings.get('prefix', '!')}`",
            f"**Лимит варнов:** {settings.get('warn_limit', 5)}",
            f"**Лог-канал:** {_channel_text(ctx.guild, settings.get('log_channel_id'))}",
            f"**Автороль:** {_role_text(ctx.guild, settings.get('autorole_id'))}",
            "",
            "**Приветствие**",
            f"· Канал: {_channel_text(ctx.guild, settings['welcome'].get('channel_id'))}",
            f"· Текст: {settings['welcome'].get('message', '—')}",
            "",
            "**Прощание**",
            f"· Канал: {_channel_text(ctx.guild, settings['goodbye'].get('channel_id'))}",
            f"· Текст: {settings['goodbye'].get('message', '—')}",
            "",
            "**Автомодерация**",
            f"· спам: {_on_off(automod.get('anti_spam'))}, инвайты: {_on_off(automod.get('invites'))}, "
            f"ссылки: {_on_off(automod.get('links'))}, капс: {_on_off(automod.get('caps'))}, "
            f"упоминания: {_on_off(automod.get('mention_spam'))}",
            f"· слова: {_on_off(automod.get('bad_words'))} (в базе {len(automod.get('badwords') or [])})",
            f"· исключённые каналы: {len(automod.get('ignored_channels') or [])}",
            "",
            "**Щит сервера**",
            f"· Верификация: {_role_text(ctx.guild, settings['verify'].get('role_id'))} "
            f"(канал: {_channel_text(ctx.guild, settings['verify'].get('channel_id'))})",
            f"· Антирейд: {_on_off(settings['antiraid'].get('enabled'))} "
            f"(мин. возраст: {settings['antiraid'].get('min_age_days', 0)} дн)",
        ]
        await ctx.send(embed=mk_embed("⚙️ Настройки", description="\n".join(lines), color=COLOR_NEUTRAL))
    config.category = "Настройки"

    # ------------------------------------------------------------------ логи

    @commands.hybrid_command(name="setlog", description="Канал логов (без аргумента — отключить)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setlog(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["log_channel_id"] = channel.id if channel is not None else None
        store.save_settings(ctx.guild.id, settings)
        if channel is None:
            await ctx.send("📤 Лог-канал отключён.")
            return
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await ctx.send(
                f"⚠️ Сохранил {channel.mention}, но у меня там нет права писать сообщения или эмбеды — проверь права."
            )
            return
        await ctx.send(f"✅ Лог-канал: {channel.mention}.")
    setlog.category = "Настройки"

    # -------------------------------------------------------------- welcome

    @commands.hybrid_command(name="setwelcomechannel", description="Канал приветствий (без аргумента — отключить)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setwelcomechannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["welcome"]["channel_id"] = channel.id if channel is not None else None
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Канал приветствий: {channel.mention}." if channel else "👋 Приветствия отключены.")
    setwelcomechannel.category = "Настройки"

    @commands.hybrid_command(name="setwelcomemessage", description='Текст приветствия ({user}, {name}, {server}, {count})')
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setwelcomemessage(self, ctx: commands.Context, *, text: str) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["welcome"]["message"] = text
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Новый текст приветствия:\n> {text}")
    setwelcomemessage.category = "Настройки"

    @commands.hybrid_command(name="testwelcome", description="Отправить тестовое приветствие")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def testwelcome(self, ctx: commands.Context) -> None:
        settings = store.get_settings(ctx.guild.id)
        welcome = settings["welcome"]
        channel = ctx.guild.get_channel(welcome.get("channel_id"))
        if channel is None:
            await ctx.send("❓ Канал приветствий не задан (`/setwelcomechannel`). Отправляю сюда:")
            channel = ctx.channel
        text = settings["welcome"].get("message", "")
        replacements = {
            "{user}": ctx.author.mention,
            "{username}": str(ctx.author),
            "{name}": ctx.author.display_name,
            "{server}": ctx.guild.name,
            "{count}": str(ctx.guild.member_count),
        }
        for token, value in replacements.items():
            text = text.replace(token, value)
        await channel.send(text)
        if channel is not ctx.channel:
            await ctx.send(f"📨 Отправил тест в {channel.mention}.")
    testwelcome.category = "Настройки"

    # --------------------------------------------------------------- goodbye

    @commands.hybrid_command(name="setgoodbyechannel", description="Канал прощаний (без аргумента — отключить)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setgoodbyechannel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["goodbye"]["channel_id"] = channel.id if channel is not None else None
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Канал прощаний: {channel.mention}." if channel else "📤 Прощания отключены.")
    setgoodbyechannel.category = "Настройки"

    @commands.hybrid_command(name="setgoodbyemessage", description="Текст прощания ({user}, {name}, {server}, {count})")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setgoodbyemessage(self, ctx: commands.Context, *, text: str) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["goodbye"]["message"] = text
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Новый текст прощания:\n> {text}")
    setgoodbyemessage.category = "Настройки"

    # -------------------------------------------------------------- прочее

    @commands.hybrid_command(name="setautorole", description="Роль для новичков (без аргумента — отключить)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setautorole(self, ctx: commands.Context, role: Optional[discord.Role] = None) -> None:
        settings = store.get_settings(ctx.guild.id)
        if role is not None and not role.is_default() and role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Эта роль не ниже моей — я не смогу её выдавать. Подними роль бота выше.")
            return
        settings["autorole_id"] = role.id if role is not None else None
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Автороль: {role.mention}." if role else "✅ Автороль отключена.")
    setautorole.category = "Настройки"

    @commands.hybrid_command(name="setprefix", description="Префикс-команды бота (1–8 символов)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setprefix(self, ctx: commands.Context, prefix: str) -> None:
        prefix = prefix.strip()
        if not 1 <= len(prefix) <= 8:
            await ctx.send("❌ Префикс должен быть 1–8 символов.")
            return
        settings = store.get_settings(ctx.guild.id)
        settings["prefix"] = prefix
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Префикс: `{prefix}`. Пример: `{prefix}ping`.")
    setprefix.category = "Настройки"

    @commands.hybrid_command(name="setwarnlimit", description="Сколько варнов до авто-таймаута (1–50)")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def setwarnlimit(self, ctx: commands.Context, limit: commands.Range[int, 1, 50]) -> None:
        settings = store.get_settings(ctx.guild.id)
        settings["warn_limit"] = int(limit)
        store.save_settings(ctx.guild.id, settings)
        await ctx.send(f"✅ Лимит предупреждений: {limit}. После него — авто-таймаут на 1 час.")
    setwarnlimit.category = "Настройки"


def _on_off(value) -> str:
    return "✅" if value else "❌"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfigCog(bot))
