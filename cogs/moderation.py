"""Модерация: кик, баны, муты, варны, очистка чата, роли, ник."""

import datetime
from typing import List, Optional

import discord
from discord.ext import commands, tasks

import utils.attribution as _sig
import utils.settings as store
from utils.helpers import (
    COLOR_NEG,
    COLOR_NEUTRAL,
    COLOR_OK,
    COLOR_WARN,
    clip,
    dm_user,
    hierarchy_failure,
    human_time,
    mk_embed,
    parse_time,
    send_mod_log,
    timeout_member,
)


class ModerationCog(commands.Cog):
    """Санкции, очистка чата и управление ролями."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self._tempban_loop.start()

    def cog_unload(self) -> None:
        self._tempban_loop.cancel()

    @tasks.loop(seconds=30)
    async def _tempban_loop(self) -> None:
        await self.bot.wait_until_ready()
        bans = store.get_tempbans()
        if not bans:
            return
        now = discord.utils.utcnow().timestamp()
        remaining: List[dict] = []
        changed = False
        for entry in bans:
            if entry["until"] <= now:
                changed = True
                user_id = int(entry["user_id"])
                guild = self.bot.get_guild(int(entry["guild_id"]))
                if guild is None:
                    continue  # сервер недоступен — запись отдаём на растерзание
                try:
                    await guild.unban(
                        discord.Object(id=user_id),
                        reason=f"Истёк срок временного бана (причина: {entry.get('reason', '—')})",
                    )
                except discord.NotFound:
                    pass  # уже разбанен вручную — просто выкидываем запись
                except discord.Forbidden:
                    remaining.append(entry)  # попробуем в следующий цикл
                    continue
                await send_mod_log(
                    guild,
                    "снятие временного бана",
                    moderator=guild.me,
                    reason=f"Срок истёк. Причина бана: {entry.get('reason', '—')}",
                    color=COLOR_OK,
                    target_str=f"<@{user_id}>",
                )
            else:
                remaining.append(entry)
        if changed:
            store.set_tempbans(remaining)

    # ------------------------------------------------------------ кик/баны

    @commands.hybrid_command(name="kick", description="Кикнуть участника", aliases=["кик"])
    @commands.guild_only()
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Причина не указана") -> None:
        problem = hierarchy_failure(ctx, member)
        if problem:
            await ctx.send(problem)
            return
        await dm_user(member, f"Тебя кикнули с сервера **{ctx.guild.name}**.\nПричина: {reason}")
        await member.kick(reason=f"{ctx.author} | {reason}")
        await send_mod_log(ctx.guild, "кик", moderator=ctx.author, reason=reason, color=COLOR_NEG, target=member)
        await ctx.send(f"👢 {member.mention} кикнут. Причина: {reason}")
    kick.category = "Модерация"

    @commands.hybrid_command(name="ban", description="Забанить участника", aliases=["бан"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        delete_messages: commands.Range[int, 0, 7] = 1,
        *,
        reason: str = "Причина не указана",
    ) -> None:
        problem = hierarchy_failure(ctx, member)
        if problem:
            await ctx.send(problem)
            return
        await dm_user(member, f"Тебя забанили на сервере **{ctx.guild.name}**.\nПричина: {reason}")
        await member.ban(
            delete_message_seconds=delete_messages * 86400,
            reason=f"{ctx.author} | {reason}",
        )
        await send_mod_log(ctx.guild, "бан", moderator=ctx.author, reason=reason, color=COLOR_NEG, target=member)
        await ctx.send(f"🔨 {member.mention} забанен. Причина: {reason}")
    ban.category = "Модерация"

    @commands.hybrid_command(name="unban", description="Разбанить пользователя по ID", aliases=["разбан"])
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "Причина не указана") -> None:
        try:
            await ctx.guild.unban(discord.Object(id=user_id), reason=f"{ctx.author} | {reason}")
        except discord.NotFound:
            await ctx.send("❌ Пользователь с таким ID не забанен.")
            return
        except discord.HTTPException:
            await ctx.send("❌ Не удалось разбанить, попробуй позже.")
            return
        await send_mod_log(ctx.guild, "разбан", moderator=ctx.author, reason=reason, color=COLOR_OK, target_str=f"<@{user_id}>")
        await ctx.send(f"✅ <@{user_id}> разбанен.")
    unban.category = "Модерация"

    @commands.hybrid_command(name="tempban", description="Временный бан участника")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str = "Причина не указана",
    ) -> None:
        seconds = parse_time(duration)
        if seconds is None:
            await ctx.send("❌ Не разобрал срок. Примеры: `30m`, `1h`, `3d`, `1h 30m`, `2w`.")
            return
        problem = hierarchy_failure(ctx, member)
        if problem:
            await ctx.send(problem)
            return
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)

        bans = [
            item
            for item in store.get_tempbans()
            if not (item["guild_id"] == ctx.guild.id and item["user_id"] == member.id)
        ]
        bans.append({"guild_id": ctx.guild.id, "user_id": member.id, "until": until.timestamp(), "reason": reason})
        store.set_tempbans(bans)

        await dm_user(
            member,
            f"Тебя временно забанили на сервере **{ctx.guild.name}** до "
            f"{discord.utils.format_dt(until, style='f')}.\nПричина: {reason}",
        )
        await member.ban(reason=f"{ctx.author} | tempban до {until.isoformat()} | {reason}")
        await send_mod_log(ctx.guild, "временный бан", moderator=ctx.author, reason=reason, color=COLOR_NEG, target=member)
        await ctx.send(
            f"⏳ {member.mention} забанен до {discord.utils.format_dt(until, style='f')} ({human_time(seconds)})."
        )
    tempban.category = "Модерация"

    @commands.hybrid_command(name="softban", description="Бан с чисткой сообщений + мгновенный разбан")
    @commands.guild_only()
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Причина не указана") -> None:
        problem = hierarchy_failure(ctx, member)
        if problem:
            await ctx.send(problem)
            return
        try:
            await member.ban(delete_message_seconds=7 * 86400, reason=f"{ctx.author} | softban | {reason}")
            await ctx.guild.unban(member, reason=f"{ctx.author} | softban откат")
        except discord.HTTPException:
            await ctx.send("❌ Не удалось выполнить софтбан (проверь права бота).")
            return
        await send_mod_log(ctx.guild, "софтбан", moderator=ctx.author, reason=reason, color=COLOR_NEG, target=member)
        await ctx.send(f"🧼 {member.mention} софтобан: сообщения за 7 дней удалены, участник вернулся обратно.")
    softban.category = "Модерация"

    # ------------------------------------------------------ муты (таймауты)

    @commands.hybrid_command(name="mute", description="Замутить участника (таймаут)", aliases=["мут", "timeout"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(
        self,
        ctx: commands.Context,
        member: discord.Member,
        duration: str,
        *,
        reason: str = "Причина не указана",
    ) -> None:
        seconds = parse_time(duration)
        if seconds is None:
            await ctx.send("❌ Не разобрал срок. Примеры: `30m`, `1h`, `3d`, `1h 30m`.")
            return
        seconds = min(seconds, 28 * 86400)
        problem = hierarchy_failure(ctx, member)
        if problem:
            await ctx.send(problem)
            return
        until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
        await member.timeout(until, reason=f"{ctx.author} | {reason}")
        await dm_user(
            member,
            f"Тебя замутили на сервере **{ctx.guild.name}** до {discord.utils.format_dt(until, style='f')}.\nПричина: {reason}",
        )
        await send_mod_log(ctx.guild, "мут", moderator=ctx.author, reason=reason, color=COLOR_WARN, target=member)
        await ctx.send(
            f"🔇 {member.mention} замучен до {discord.utils.format_dt(until, style='f')} ({human_time(seconds)})."
        )
    mute.category = "Модерация"

    @commands.hybrid_command(name="unmute", description="Снять таймаут с участника", aliases=["размут"])
    @commands.guild_only()
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Размут") -> None:
        if member.timed_out_until is None:
            await ctx.send("ℹ️ У этого участника не активен таймаут.")
            return
        await member.timeout(None, reason=f"{ctx.author} | {reason}")
        await send_mod_log(ctx.guild, "снятие мута", moderator=ctx.author, reason=reason, color=COLOR_OK, target=member)
        await ctx.send(f"🔊 С {member.mention} снят таймаут.")
    unmute.category = "Модерация"

    # --------------------------------------------------------- предупреждения

    @commands.hybrid_command(name="warn", description="Выдать предупреждение", aliases=["варн"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Причина не указана") -> None:
        problem = hierarchy_failure(ctx, member)
        if problem:
            await ctx.send(problem)
            return
        settings = store.get_settings(ctx.guild.id)
        limit = int(settings.get("warn_limit", 5) or 5)
        count = store.add_warning(ctx.guild.id, member.id, str(ctx.author), ctx.author.id, reason)
        await dm_user(
            member,
            f"Тебе выдали предупреждение на сервере **{ctx.guild.name}** (счётчик: {count} из лимита {limit}).\nПричина: {reason}",
        )
        await send_mod_log(ctx.guild, "варн", moderator=ctx.author, reason=reason, color=COLOR_WARN, target=member)
        reply = f"⚠️ {member.mention} получил предупреждение. Всего: **{count}** (лимит {limit})."
        if count >= limit:
            if await timeout_member(member, 3600, "Превышен лимит предупреждений"):
                reply += "\n🚫 Лимит превышен — авто-таймаут на 1 час."
                await send_mod_log(
                    ctx.guild,
                    "авто-таймаут за варны",
                    moderator=ctx.guild.me,
                    reason=f"Превышен лимит ({limit}) предупреждений",
                    color=COLOR_WARN,
                    target=member,
                )
        await ctx.send(reply)
    warn.category = "Модерация"

    @commands.hybrid_command(name="warnings", description="Список предупреждений участника", aliases=["варны"])
    @commands.guild_only()
    async def warnings(self, ctx: commands.Context, member: Optional[discord.Member] = None) -> None:
        member = member or ctx.author
        entries = store.get_user_warnings(ctx.guild.id, member.id)
        if not entries:
            await ctx.send(f"✅ У {member.mention} предупреждений нет.")
            return
        start_index = max(1, len(entries) - 9)
        lines = []
        for index, entry in enumerate(entries[-10:], start=start_index):
            when = ""
            try:
                when = discord.utils.format_dt(datetime.datetime.fromisoformat(entry.get("ts", "")), style="f")
            except ValueError:
                pass
            lines.append(
                f"**{index}.** {when} · *{entry.get('moderator', '—')}*\n    {clip(entry.get('reason', '—'), 150)}"
            )
        embed = mk_embed(
            f"⚠️ Предупреждения: {member.display_name}",
            description="\n".join(lines),
            color=COLOR_WARN,
        )
        embed.set_footer(text=f"Всего предупреждений: {len(entries)} • {_sig.tag()}")
        await ctx.send(embed=embed)
    warnings.category = "Модерация"

    @commands.hybrid_command(name="delwarn", description="Снять предупреждение по номеру")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def delwarn(self, ctx: commands.Context, member: discord.Member, index: commands.Range[int, 1, 999]) -> None:
        removed = store.del_warning(ctx.guild.id, member.id, index - 1)
        if removed is None:
            await ctx.send("❌ Предупреждение с таким номером не найдено (`/warnings`, чтобы посмотреть список).")
            return
        await send_mod_log(
            ctx.guild, "снятие варна", moderator=ctx.author, reason=str(removed), color=COLOR_OK, target=member
        )
        await ctx.send(f"✅ Снял предупреждение №{index} у {member.mention}.")
    delwarn.category = "Модерация"

    @commands.hybrid_command(name="clearwarns", description="Снять все предупреждения участника")
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    async def clearwarns(self, ctx: commands.Context, member: discord.Member) -> None:
        removed = store.clear_warnings(ctx.guild.id, member.id)
        if not removed:
            await ctx.send(f"ℹ️ У {member.mention} и так нет предупреждений.")
            return
        await send_mod_log(
            ctx.guild, "полное снятие варнов", moderator=ctx.author, reason=f"Снято {removed} шт.", color=COLOR_OK, target=member
        )
        await ctx.send(f"✅ Снял все предупреждения ({removed} шт.) у {member.mention}.")
    clearwarns.category = "Модерация"

    # ------------------------------------------------------- чат и каналы

    @commands.hybrid_command(name="purge", description="Удалить последние сообщения (максимум 100)", aliases=["очистить", "оч"])
    @commands.guild_only()
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: commands.Range[int, 1, 100], member: Optional[discord.Member] = None) -> None:
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("❌ Работает только в текстовых каналах (не в тредах).")
            return
        if ctx.interaction is not None:
            await ctx.defer()

        events_cog = self.bot.get_cog("EventsCog")
        if events_cog is not None:
            events_cog.suppress_delete(ctx.channel.id, seconds=8)
            if ctx.message is not None:
                events_cog.suppress_delete(ctx.channel.id, seconds=8)

        limit = amount + (1 if ctx.message is not None else 0)

        def predicate(message: discord.Message) -> bool:
            if member is not None and message.author.id != member.id:
                return False
            return not message.pinned

        try:
            deleted = await ctx.channel.purge(limit=limit, check=predicate, bulk=True, reason=f"purge by {ctx.author}")
        except discord.HTTPException:
            await ctx.send("⚠️ Discord ограничил удаление: больше всего — сообщения старше 14 дней не удаляются пачкой.")
            return

        await send_mod_log(
            ctx.guild,
            "очистка чата",
            moderator=ctx.author,
            reason=f"Удалено {len(deleted)} сообщений" + (f" от {member}" if member else ""),
            color=COLOR_NEUTRAL,
            target_str=ctx.channel.mention if hasattr(ctx.channel, "mention") else None,
        )
        await ctx.send(
            f"🧹 Удалено сообщений: {len(deleted)}" + (f" (автор: {member.mention})" if member else "") + "."
        )
    purge.category = "Модерация"

    @commands.hybrid_command(name="slowmode", description="Медленный режим канала (0 — выключить)")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(
        self,
        ctx: commands.Context,
        seconds: commands.Range[int, 0, 21600],
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Работает только для текстовых каналов.")
            return
        try:
            await channel.edit(slowmode_delay=seconds, reason=f"slowmode by {ctx.author}")
        except discord.HTTPException:
            await ctx.send("❌ Не удалось изменить канал (проверь права).")
            return
        await ctx.send("✅ Медленный режим выключен." if seconds == 0 else f"🐢 Медленный режим: {seconds} сек.")
    slowmode.category = "Модерация"

    @commands.hybrid_command(name="lock", description="Заблокировать чат для всех (только админы смогут писать)")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, *, reason: str = "Лок чата") -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Работает только для текстовых каналов.")
            return
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is False:
            await ctx.send("ℹ️ Канал уже заблокирован.")
            return
        overwrite.send_messages = False
        overwrite.add_reactions = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"lock by {ctx.author}")
        await send_mod_log(
            ctx.guild, "лок канала", moderator=ctx.author, reason=reason, color=COLOR_WARN,
            target_str=channel.mention,
        )
        await ctx.send(f"🔒 Канал {channel.mention} заблокирован. Разблокировать: `/unlock`.")
    lock.category = "Модерация"

    @commands.hybrid_command(name="unlock", description="Разблокировать чат")
    @commands.guild_only()
    @commands.has_permissions(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, *, reason: str = "Разлок чата") -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Работает только для текстовых каналов.")
            return
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        if overwrite.send_messages is not False:
            await ctx.send("ℹ️ Канал не заблокирован.")
            return
        overwrite.send_messages = None
        overwrite.add_reactions = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"unlock by {ctx.author}")
        await send_mod_log(
            ctx.guild, "разлок канала", moderator=ctx.author, reason=reason, color=COLOR_OK,
            target_str=channel.mention,
        )
        await ctx.send(f"🔓 Канал {channel.mention} разблокирован.")
    unlock.category = "Модерация"

    # ------------------------------------------------------- роли и ники

    @commands.hybrid_command(name="addrole", description="Выдать роль участнику")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrole(self, ctx: commands.Context, member: discord.Member, role: discord.Role) -> None:
        if role.is_default() or role.managed:
            await ctx.send("❌ Эту роль нельзя выдать вручную (базовая или интеграция).")
            return
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Эта роль не ниже моей. Подними роль бота выше в списке ролей.")
            return
        if role in member.roles:
            await ctx.send(f"ℹ️ У {member.mention} уже есть роль {role.mention}.")
            return
        try:
            await member.add_roles(role, reason=f"{ctx.author} | addrole")
        except discord.Forbidden:
            await ctx.send("⚠️ Не удалось выдать роль (проверь права).")
            return
        await send_mod_log(
            ctx.guild, "выдача роли", moderator=ctx.author, reason=f"Роль: {role.name}", color=COLOR_OK, target=member
        )
        await ctx.send(f"✅ Роль {role.mention} выдана {member.mention}.")
    addrole.category = "Модерация"

    @commands.hybrid_command(name="removerole", description="Забрать роль у участника")
    @commands.guild_only()
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removerole(self, ctx: commands.Context, member: discord.Member, role: discord.Role) -> None:
        if role.is_default() or role.managed:
            await ctx.send("❌ Эту роль нельзя снять вручную.")
            return
        if role.position >= ctx.guild.me.top_role.position:
            await ctx.send("❌ Эта роль не ниже моей.")
            return
        if role not in member.roles:
            await ctx.send(f"ℹ️ У {member.mention} нет роли {role.mention}.")
            return
        try:
            await member.remove_roles(role, reason=f"{ctx.author} | removerole")
        except discord.Forbidden:
            await ctx.send("⚠️ Не удалось снять роль.")
            return
        await send_mod_log(
            ctx.guild, "снятие роли", moderator=ctx.author, reason=f"Роль: {role.name}", color=COLOR_OK, target=member
        )
        await ctx.send(f"✅ Роль {role.mention} снята с {member.mention}.")
    removerole.category = "Модерация"

    @commands.hybrid_command(name="nickname", description="Сменить ник (без аргумента — сброс)", aliases=["ник"])
    @commands.guild_only()
    @commands.has_permissions(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, nickname: Optional[str] = None) -> None:
        if nickname is not None and nickname.strip().lower() in ("clear", "убрать", "-", "сброс", "reset"):
            nickname = None
        if member not in (ctx.author, ctx.guild.me):
            problem = hierarchy_failure(ctx, member)
            if problem:
                await ctx.send(problem)
                return
        try:
            await member.edit(nick=nickname, reason=f"{ctx.author} | nickname")
        except discord.Forbidden:
            await ctx.send("⚠️ Не удалось сменить ник (роль бота должна быть выше).")
            return
        if nickname:
            await ctx.send(f"✏️ {member.mention}: новый ник **{nickname}**.")
        else:
            await ctx.send(f"✏️ {member.mention}: ник сброшен к основному.")
    nickname.category = "Модерация"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))
