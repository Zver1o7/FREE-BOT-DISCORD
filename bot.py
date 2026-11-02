"""Discord-бот администрирования (discord.py 2.x).

By @Zver1o7 — https://github.com/Zver1o7

Запуск:
    python bot.py

Токен берётся из переменной окружения DISCORD_TOKEN или из config.json.
"""

__author__ = "@Zver1o7"
__github__ = "https://github.com/Zver1o7"

import json
import logging
import os
import sys
from typing import Optional

import discord
import discord.errors
from discord.ext import commands

import utils.settings as settings_store

log = logging.getLogger("adminbot")
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(_BASE_DIR, "config.json")

EXTENSIONS = (
    "cogs.general",
    "cogs.moderation",
    "cogs.automod",
    "cogs.events",
    "cogs.welcome",
    "cogs.config",
    "cogs.tickets",
)


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def load_token(config: dict) -> str:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if token:
        return token

    token = (config.get("token") or "").strip()
    if token:
        return token

    raise SystemExit(
        "\n❌ Токен бота не найден. Два способа задать его:\n"
        "  1) Переменная окружения DISCORD_TOKEN\n"
        "     PowerShell: $env:DISCORD_TOKEN = 'тут токен'\n"
        '  2) config.json: { "token": "тут токен" }\n'
        "Как получить токен — читай README.md (раздел «Подключение к Discord»)."
    )


def get_prefix(_bot, message) -> str:
    if message.guild is None:
        return "!"
    try:
        return settings_store.get_settings(message.guild.id)["prefix"]
    except Exception:
        return "!"


class AdminBot(commands.Bot):
    def __init__(self, config: dict) -> None:
        intents = discord.Intents.default()
        intents.members = True          # welcome, goodbye, автороль (+ привилегированный)
        intents.message_content = True  # префикс-команды и автомодерация (+ привилегированный)
        intents.moderation = True       # события банов и таймаутов

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            case_insensitive=True,
            help_command=None,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False, users=True),
        )
        self._config = config

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                log.info("Модуль загружен: %s", extension)
            except Exception:
                log.exception("Не удалось загрузить модуль %s", extension)

        guild_id = str(self._config.get("guild_id") or os.getenv("GUILD_ID", "")).strip()
        if guild_id and guild_id.isdigit():
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Слэш-команды синхронизированы для сервера %s (быстро)", guild_id)
        else:
            await self.tree.sync()
            log.info("Слэш-команды отправлены в глобальную синхронизацию (до ~1 часа)")

    async def on_ready(self) -> None:
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="за порядком на серверах")
        )
        log.info("Запущен как %s (id %s). Серверов: %s", self.user, self.user.id, len(self.guilds))

    async def on_command_error(self, ctx: commands.Context, error) -> None:
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            text = "⛔ У тебя недостаточно прав: " + ", ".join(error.missing_permissions)
        elif isinstance(error, commands.BotMissingPermissions):
            text = "🤖 У меня недостаточно прав: " + ", ".join(error.missing_permissions)
        elif isinstance(error, commands.NoPrivateMessage):
            text = "🏠 Эта команда работает только на сервере."
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"❌ Не хватает аргумента: `{error.param.name}`"
        elif isinstance(error, commands.BadArgument):
            text = "❌ Неверный аргумент (проверь упоминание или ID)."
        elif isinstance(error, commands.CommandOnCooldown):
            text = f"⏳ Команда на перезарядке, подожди {error.retry_after:.0f} с."
        elif isinstance(error, commands.CheckFailure):
            text = "⛔ Ты не можешь использовать эту команду."
        elif isinstance(error, commands.CommandInvokeError):
            cause = error.__cause__
            if isinstance(cause, discord.Forbidden):
                text = "⚠️ У меня нет прав на это действие (проверь роль бота)."
            else:
                log.error("Ошибка в команде %s", ctx.command, exc_info=error)
                text = "❌ Произошла ошибка при выполнении команды. Подробности в консоли."
        else:
            log.error("Ошибка в команде %s", ctx.command, exc_info=error)
            text = "❌ Произошла ошибка при выполнении команды. Подробности в консоли."

        try:
            await ctx.send(text)
        except discord.HTTPException:
            pass


def main() -> None:
    config = load_config()
    bot = AdminBot(config)
    try:
        bot.run(load_token(config))
    except discord.errors.LoginFailure:
        raise SystemExit("❌ Неверный токен бота. Проверь его в config.json или DISCORD_TOKEN.")
    except discord.errors.PrivilegedIntentsRequired:
        raise SystemExit(
            "\n⚠️ Включи привилегированные интенты в Discord Developer Portal:\n"
            "  → страница приложения → Bot → Privileged Gateway Intents →\n"
            "  ✅ SERVER MEMBERS INTENT\n"
            "  ✅ MESSAGE CONTENT INTENT\n"
            "Подробности и скриншоты — в README.md."
        )


if __name__ == "__main__":
    main()
