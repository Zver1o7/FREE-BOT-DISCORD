"""Розыгрыши: создание, участие кнопкой, автозавершение, реролл."""

import datetime
import logging
import random
from typing import List, Optional

import discord
from discord.ext import commands, tasks

import utils.settings as store
from utils.helpers import COLOR_NEUTRAL, COLOR_OK, human_time, mk_embed, parse_time, send_log

log = logging.getLogger("adminbot")

MAX_GIVEAWAY_SECONDS = 30 * 86400  # дольше месяца — уже календарь, а не розыгрыш


def _active_in_channel(giveaways: List[dict], channel_id: int) -> Optional[dict]:
    actives = [
        entry
        for entry in giveaways
        if not entry.get("ended") and int(entry.get("channel_id", 0)) == channel_id
    ]
    return actives[-1] if actives else None


def _build_embed(gw: dict) -> discord.Embed:
    ends = datetime.datetime.fromtimestamp(float(gw["ends_at"]), tz=datetime.timezone.utc)
    embed = mk_embed("🎉 Розыгрыш", description=f"**Приз:** {gw.get('prize', '—')}")
    embed.add_field(
        name="Финал",
        value=f"{discord.utils.format_dt(ends, style='f')} ({discord.utils.format_dt(ends, style='R')})",
        inline=False,
    )
    embed.add_field(name="Победителей", value=str(gw.get("winners_count", 1)), inline=True)
    embed.add_field(name="Участников", value=str(len(gw.get("participants", []))), inline=True)
    embed.add_field(name="Организатор", value=f"<@{gw.get('host_id')}>", inline=True)
    return embed


class GiveawayView(discord.ui.View):
    """Кнопка участия. Постоянная (custom_id) — работает после рестарта бота."""

    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Участвовать 🎉", style=discord.ButtonStyle.success, custom_id="giveaway_join_v1")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            await interaction.response.send_message("❌ Только на сервере.", ephemeral=True)
            return
        if member.bot:
            await interaction.response.send_message("❌ Боты не участвуют.", ephemeral=True)
            return
        giveaways = store.get_giveaways()
        index = next(
            (
                i
                for i, entry in enumerate(giveaways)
                if not entry.get("ended") and int(entry.get("channel_id", 0)) == interaction.channel.id
            ),
            None,
        )
        if index is None:
            await interaction.response.send_message("❌ Активного розыгрыша здесь нет.", ephemeral=True)
            return
        gw = giveaways[index]
        participants = [int(user_id) for user_id in gw.get("participants", [])]
        if member.id in participants:
            participants.remove(member.id)
            reply = "Ты вышел из розыгрыша."
        else:
            participants.append(member.id)
            reply = f"Ты участвуешь! Участников: {len(participants)}."
        gw["participants"] = participants
        store.set_giveaways(giveaways)
        try:
            await interaction.response.edit_message(embed=_build_embed(gw))
        except (discord.Forbidden, discord.HTTPException):
            await interaction.response.send_message(reply, ephemeral=True)
            return
        try:
            await interaction.followup.send(reply, ephemeral=True)
        except (discord.Forbidden, discord.HTTPException):
            pass


class GiveawayCog(commands.Cog):
    """Розыгрыши с автозавершением."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(GiveawayView(self.bot))
        self._giveaway_loop.start()

    def cog_unload(self) -> None:
        self._giveaway_loop.cancel()

    @tasks.loop(seconds=30)
    async def _giveaway_loop(self) -> None:
        await self.bot.wait_until_ready()
        now = discord.utils.utcnow().timestamp()
        for gw in [entry for entry in store.get_giveaways() if not entry.get("ended")]:
            try:
                if float(gw.get("ends_at", 0)) <= now:
                    await self._finish_giveaway(gw)
            except Exception:
                log.exception("Не удалось завершить розыгрыш")

    async def _finish_giveaway(self, gw: dict, reason: str = "") -> None:
        giveaways = store.get_giveaways()
        index = next(
            (
                i
                for i, entry in enumerate(giveaways)
                if entry.get("message_id") == gw.get("message_id")
                and entry.get("channel_id") == gw.get("channel_id")
            ),
            None,
        )
        if index is None or giveaways[index].get("ended"):
            return
        gw = giveaways[index]
        participants = [int(user_id) for user_id in gw.get("participants", [])]
        winners = random.sample(participants, min(int(gw.get("winners_count", 1) or 1), len(participants))) if participants else []
        gw["ended"] = True
        gw["winner_ids"] = winners
        store.set_giveaways(giveaways)

        guild = self.bot.get_guild(int(gw["guild_id"]))
        if guild is None:
            return  # сервер недоступен — запись помечена завершённой
        channel = guild.get_channel(int(gw["channel_id"]))

        result = mk_embed("🎉 Розыгрыш завершён", color=COLOR_OK)
        result.add_field(name="Приз", value=str(gw.get("prize", "—")), inline=False)
        if winners:
            result.add_field(name="Победители", value=" ".join(f"<@{user_id}>" for user_id in winners), inline=False)
        else:
            result.add_field(name="Победители", value="Никто не участвовал.", inline=False)
        result.add_field(name="Организатор", value=f"<@{gw.get('host_id')}>", inline=True)
        if reason:
            result.add_field(name="Причина", value=reason, inline=True)

        message = None
        if channel is not None:
            try:
                message = await channel.fetch_message(int(gw["message_id"]))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                message = None
            if message is not None:
                try:
                    await message.edit(embed=result, view=None)
                except (discord.Forbidden, discord.HTTPException):
                    pass
            try:
                if winners:
                    mentions = " ".join(f"<@{user_id}>" for user_id in winners)
                    await channel.send(f"🎉 {mentions} — вы выиграли **{gw.get('prize')}**!", embed=result)
                else:
                    await channel.send("🎉 Розыгрыш завершён, но никто не участвовал.", embed=result)
            except (discord.Forbidden, discord.HTTPException):
                pass
        await send_log(guild, result)

    # -------------------------------------------------------------- команды

    @commands.hybrid_command(name="giveaway", description="Запустить розыгрыш")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def giveaway(
        self,
        ctx: commands.Context,
        duration: str,
        winners: commands.Range[int, 1, 20],
        prize: str,
        channel: Optional[discord.TextChannel] = None,
    ) -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Розыгрыш можно запустить только в текстовом канале.")
            return
        perms = channel.permissions_for(ctx.guild.me)
        if not perms.send_messages or not perms.embed_links:
            await ctx.send("⚠️ У меня нет прав писать сообщения/эмбеды в этот канал.")
            return
        seconds = parse_time(duration)
        if seconds is None:
            await ctx.send("❌ Не разобрал срок. Примеры: `10m`, `2h`, `1d`, `1h 30m`.")
            return
        if seconds < 60:
            await ctx.send("❌ Минимум — 1 минута.")
            return
        if seconds > MAX_GIVEAWAY_SECONDS:
            await ctx.send("❌ Максимум — 30 дней.")
            return
        giveaways = store.get_giveaways()
        if _active_in_channel(giveaways, channel.id) is not None:
            await ctx.send("❌ В этом канале уже идёт розыгрыш. Сначала заверши его: `/giveawayend`.")
            return
        ends_at = discord.utils.utcnow().timestamp() + seconds
        gw = {
            "guild_id": ctx.guild.id,
            "channel_id": channel.id,
            "message_id": None,
            "ends_at": ends_at,
            "winners_count": int(winners),
            "prize": prize,
            "host_id": ctx.author.id,
            "participants": [],
            "ended": False,
            "winner_ids": [],
        }
        try:
            message = await channel.send(embed=_build_embed(gw), view=GiveawayView(self.bot))
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send("❌ Не могу написать в этот канал.")
            return
        gw["message_id"] = message.id
        giveaways.append(gw)
        store.set_giveaways(giveaways)
        ends = datetime.datetime.fromtimestamp(ends_at, tz=datetime.timezone.utc)
        await ctx.send(
            f"✅ Розыгрыш запущен в {channel.mention}: **{prize}**, "
            f"победителей: {winners}, финал {discord.utils.format_dt(ends, style='f')} ({human_time(seconds)})."
        )
    giveaway.category = "Розыгрыши"

    @commands.hybrid_command(name="giveawayend", description="Досрочно завершить розыгрыш")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def giveawayend(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None) -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Только текстовые каналы.")
            return
        gw = _active_in_channel(store.get_giveaways(), channel.id)
        if gw is None:
            await ctx.send("❌ В этом канале нет активного розыгрыша.")
            return
        await self._finish_giveaway(gw, reason="Завершён досрочно")
        await ctx.send("✅ Розыгрыш завершён досрочно.")
    giveawayend.category = "Розыгрыши"

    @commands.hybrid_command(name="reroll", description="Перевыбрать победителей")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def reroll(
        self,
        ctx: commands.Context,
        channel: Optional[discord.TextChannel] = None,
        winners: commands.Range[int, 1, 20] = 1,
    ) -> None:
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Только текстовые каналы.")
            return
        giveaways = store.get_giveaways()
        ended = [
            entry
            for entry in giveaways
            if entry.get("ended")
            and int(entry.get("channel_id", 0)) == channel.id
            and entry.get("participants")
        ]
        if not ended:
            await ctx.send("❌ Нет завершённых розыгрышей с участниками в этом канале.")
            return
        gw = ended[-1]
        participants = [int(user_id) for user_id in gw.get("participants", [])]
        previous = [int(user_id) for user_id in gw.get("winner_ids", [])]
        pool = [user_id for user_id in participants if user_id not in previous] or participants
        new_winners = random.sample(pool, min(int(winners), len(pool)))
        gw["winner_ids"] = new_winners
        store.set_giveaways(giveaways)
        mentions = " ".join(f"<@{user_id}>" for user_id in new_winners)
        embed = mk_embed("🎲 Реролл", description=f"**Приз:** {gw.get('prize', '—')}", color=COLOR_NEUTRAL)
        embed.add_field(name="Новые победители", value=mentions, inline=False)
        try:
            await channel.send(f"🎲 {mentions} — новые победители розыгрыша **{gw.get('prize')}**!", embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            await ctx.send("❌ Не могу написать в этот канал.")
            return
        await ctx.send("✅ Победители перевыбраны.")
    reroll.category = "Розыгрыши"


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawayCog(bot))
