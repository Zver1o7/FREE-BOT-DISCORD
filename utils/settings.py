"""Настройки и данные бота (JSON-файлы в папке data/).

By @Zver1o7 — https://github.com/Zver1o7

Все функции потокобезопасны (один замок) и безопасны к отсутствию файлов.
"""

__author__ = "@Zver1o7"
__github__ = "https://github.com/Zver1o7"

import datetime
import json
import os
import threading
from typing import Any, Dict, List

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_BASE_DIR, "data")

SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
WARNINGS_FILE = os.path.join(DATA_DIR, "warnings.json")
TEMPBANS_FILE = os.path.join(DATA_DIR, "tempbans.json")

os.makedirs(DATA_DIR, exist_ok=True)

_LOCK = threading.Lock()

# Настройки по умолчанию (глубоко объединяются с данными с диска)
DEFAULT_SETTINGS: Dict[str, Any] = {
    "prefix": "!",
    "log_channel_id": None,
    "warn_limit": 5,
    "autorole_id": None,
    "welcome": {
        "channel_id": None,
        "message": "👋 Добро пожаловать на **{server}**, {user}! Ты {count}-й участник сервера.",
    },
    "goodbye": {
        "channel_id": None,
        "message": "📤 **{name}** покинул сервер. Пока-пока!",
    },
    "automod": {
        "anti_spam": True,          # 6+ сообщений за 5 секунд -> нарушение
        "anti_spam_messages": 6,
        "anti_spam_seconds": 5,
        "invites": True,            # удалять ссылки-приглашения
        "links": False,             # удалять любые ссылки (выключено по умолчанию)
        "bad_words": True,          # фильтр списка слов ниже
        "badwords": [],
        "caps": False,              # чрезмерный капс
        "mention_spam": True,       # 5+ упоминаний в одном сообщении
        "max_mentions": 5,
        "timeout_seconds": 600,     # срок авто-таймаута при повторных нарушениях
        "ignored_channels": [],     # каналы, где автомодерация не работает
    },
}


def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
            return data if isinstance(data, type(default)) else default
    except FileNotFoundError:
        return default
    except (OSError, json.JSONDecodeError) as error:
        print(f"[settings] Не удалось прочитать {path}: {error!r}")
        return default


def _write_json(path: str, data: Any) -> None:
    with _LOCK:
        try:
            with open(path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
        except OSError as error:
            print(f"[settings] Не удалось записать {path}: {error!r}")


def _deep_merge(base: dict, extra: dict) -> dict:
    merged = {key: value for key, value in base.items()}
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def get_settings(guild_id: int) -> dict:
    """Настройки сервера, объединённые с дефолтами."""
    data = _read_json(SETTINGS_FILE, {})
    saved = data.get(str(guild_id))
    if not isinstance(saved, dict):
        saved = {}
    return _deep_merge(DEFAULT_SETTINGS, saved)


def save_settings(guild_id: int, settings: dict) -> None:
    data = _read_json(SETTINGS_FILE, {})
    data[str(guild_id)] = settings
    _write_json(SETTINGS_FILE, data)


# ---------------------------------------------------------------- варны

def get_user_warnings(guild_id: int, user_id: int) -> List[dict]:
    data = _read_json(WARNINGS_FILE, {})
    guild_map = data.get(str(guild_id))
    if not isinstance(guild_map, dict):
        return []
    entries = guild_map.get(str(user_id))
    return entries if isinstance(entries, list) else []


def add_warning(guild_id: int, user_id: int, moderator: str, moderator_id: int, reason: str) -> int:
    """Добавляет предупреждение, возвращает общее количество у участника."""
    with _LOCK:
        data = _read_json(WARNINGS_FILE, {})
        guild_map = data.setdefault(str(guild_id), {})
        user_list = guild_map.setdefault(str(user_id), [])
        user_list.append(
            {
                "reason": reason,
                "moderator": moderator,
                "moderator_id": moderator_id,
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        )
        _write_json(WARNINGS_FILE, data)
        return len(user_list)


def del_warning(guild_id: int, user_id: int, index: int) -> Optional[dict]:
    """Удаляет предупреждение по индексу (0-based), возвращает удалённую запись."""
    with _LOCK:
        data = _read_json(WARNINGS_FILE, {})
        guild_map = data.setdefault(str(guild_id), {})
        user_list = guild_map.get(str(user_id), [])
        if not isinstance(user_list, list) or index < 0 or index >= len(user_list):
            return None
        removed = user_list.pop(index)
        _write_json(WARNINGS_FILE, data)
        return removed


def clear_warnings(guild_id: int, user_id: int) -> int:
    """Удаляет все предупреждения участника, возвращает сколько было."""
    with _LOCK:
        data = _read_json(WARNINGS_FILE, {})
        guild_map = data.setdefault(str(guild_id), {})
        removed = len(guild_map.get(str(user_id), []))
        guild_map[str(user_id)] = []
        _write_json(WARNINGS_FILE, data)
        return removed


# ------------------------------------------------------------- временные баны

def get_tempbans() -> List[dict]:
    data = _read_json(TEMPBANS_FILE, [])
    return data if isinstance(data, list) else []


def set_tempbans(bans: List[dict]) -> None:
    _write_json(TEMPBANS_FILE, bans)
