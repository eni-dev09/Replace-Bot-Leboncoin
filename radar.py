import asyncio
import logging
import os
import uuid
from typing import Optional

import discord

from leboncoin import search_ads
from deals import top_deals
from store import load_radars, upsert_radar, remove_radar, mark_ads_seen, is_ad_seen

log = logging.getLogger(__name__)

RADAR_INTERVAL_S = max(20, int(os.getenv("DEAL_RADAR_INTERVAL_S", "60")))
MIN_DISCOUNT_PCT = float(os.getenv("MIN_DEAL_DISCOUNT_PCT", "20"))


class RadarManager:
    def __init__(self, bot: discord.Client):
        self.bot = bot
        self._task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()
        self._scan_lock = asyncio.Lock()

    def start(self):
        if self._task is None or self._task.done():
            self._stop_event.clear()
            self._task = asyncio.create_task(self._run_loop())
            log.info("Radar démarré (intervalle %ss)", RADAR_INTERVAL_S)

    async def stop(self):
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            log.info("Radar arrêté proprement")

    async def _run_loop(self):
        while not self._stop_event.is_set():
            try:
                await self._scan_all()
            except Exception:
                log.exception("Erreur pendant le scan radar")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=RADAR_INTERVAL_S
                )
            except asyncio.TimeoutError:
                pass

    async def _scan_all(self):
        if self._scan_lock.locked():
            log.debug("Scan déjà en cours, passage ignoré")
            return
        async with self._scan_lock:
            radars = load_radars()
            for radar_id, config in radars.items():
                try:
                    await self._scan_one(radar_id, config)
                except Exception:
                    log.exception("Erreur sur le radar %s", radar_id)

    async def _scan_one(self, radar_id: str, config: dict):
        channel_id = config.get("channel_id")
        if not channel_id:
            return
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            log.warning("Salon introuvable pour le radar %s", radar_id)
            return

        ads = await search_ads(
            text=config["product"],
            price_max=config.get("price_max"),
            excludes=tuple(config.get("excludes", [])),
        )

        deals = top_deals(
            ads,
            query=config["product"],
            price_max=config.get("price_max"),
            limit=50,
        )

        min_discount = config.get("min_discount_pct", MIN_DISCOUNT_PCT)
        new_deals = []
        for deal in deals:
            ad = deal["ad"]
            if deal["discount_pct"] < min_discount:
                continue
            if is_ad_seen(radar_id, ad.id):
                continue
            new_deals.append(deal)

        if not new_deals:
            return

        # Anti-flood
        max_posts = 10 if not config.get("_first_scan_done") else 25
        to_post = new_deals[:max_posts]

        role_id = config.get("role_id")
        role_mention = f"<@&{role_id}>" if role_id else ""

        for i, deal in enumerate(to_post):
            ad = deal["ad"]
            embed = discord.Embed(
                title=ad.subject or "Annonce Leboncoin",
                url=ad.url,
                color=discord.Color.green() if not deal["suspect"] else discord.Color.orange(),
            )
            embed.add_field(name="Prix", value=f"**{ad.price} €**", inline=True)
            embed.add_field(
                name="Médiane",
                value=f"~{deal['median']:.0f} € (−{deal['discount_pct']}%)",
                inline=True,
            )
            embed.add_field(name="État", value="⚠️ Prix suspect" if deal["suspect"] else "✅ OK", inline=True)
            if getattr(ad, "location", None):
                embed.add_field(name="Lieu", value=ad.location, inline=True)
            if getattr(ad, "shippable", None) is not None:
                embed.add_field(name="Livraison", value="Oui" if ad.shippable else "Non", inline=True)

            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Voir l'annonce", url=ad.url))

            content = role_mention if i == 0 else None
            await channel.send(
                content=content,
                embed=embed,
                view=view,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
            await asyncio.sleep(1)  # éviter le flood

        mark_ads_seen(radar_id, [d["ad"].id for d in to_post])
        upsert_radar(radar_id, {**config, "_first_scan_done": True})
        log.info("Radar %s : %d nouveaux deals postés", radar_id, len(to_post))


# --- Fonctions utilitaires pour les commandes ---

def create_radar(
    product: str,
    price_max: Optional[int],
    channel_id: int,
    role_id: Optional[int] = None,
    excludes: Optional[list[str]] = None,
    min_discount_pct: float = MIN_DISCOUNT_PCT,
) -> str:
    radar_id = str(uuid.uuid4())[:8]
    upsert_radar(radar_id, {
        "product": product,
        "price_max": price_max,
        "channel_id": str(channel_id),
        "role_id": str(role_id) if role_id else None,
        "excludes": excludes or [],
        "min_discount_pct": min_discount_pct,
        "_first_scan_done": False,
    })
    return radar_id


def delete_radar(radar_id: str) -> bool:
    radars = load_radars()
    if radar_id not in radars:
        return False
    remove_radar(radar_id)
    return True
