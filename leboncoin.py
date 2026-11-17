import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import lbc

log = logging.getLogger(__name__)

LBC_CITY = os.getenv("LBC_CITY", "Paris")
LBC_LAT = float(os.getenv("LBC_LAT", "48.85994982004764"))
LBC_LNG = float(os.getenv("LBC_LNG", "2.33801967847424"))
LBC_RADIUS = int(os.getenv("LBC_RADIUS", "10000"))

CACHE_TTL_S = int(os.getenv("SEARCH_CACHE_TTL_S", "300"))
MIN_REQUEST_INTERVAL_S = 4.0


@dataclass
class SearchCacheEntry:
    timestamp: float
    ads: list


_search_cache: dict[str, SearchCacheEntry] = {}
_search_lock = asyncio.Lock()
_last_request_time: float = 0.0


def _build_client() -> lbc.Client:
    proxy_host = os.getenv("LBC_PROXY_HOST", "").strip()
    proxy_port = os.getenv("LBC_PROXY_PORT", "").strip()
    if proxy_host and proxy_port:
        proxy = lbc.Proxy(
            host=proxy_host,
            port=int(proxy_port),
            username=os.getenv("LBC_PROXY_USER", "").strip() or None,
            password=os.getenv("LBC_PROXY_PASS", "").strip() or None,
            scheme="http",
        )
        return lbc.Client(proxy=proxy)
    return lbc.Client()


_lbc_client: Optional[lbc.Client] = None


def get_client() -> lbc.Client:
    global _lbc_client
    if _lbc_client is None:
        _lbc_client = _build_client()
    return _lbc_client


def _cache_key(text: str, price_max: Optional[int], excludes: tuple[str, ...]) -> str:
    return f"{text.lower().strip()}|{price_max or 0}|{','.join(sorted(excludes))}"


async def _rate_limited_search(**kwargs) -> list:
    """Exécute une recherche en respectant l'intervalle minimal entre requêtes."""
    global _last_request_time
    async with _search_lock:
        now = time.monotonic()
        wait = MIN_REQUEST_INTERVAL_S - (now - _last_request_time)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            client = get_client()
            result = await asyncio.to_thread(lambda: client.search(**kwargs))
            _last_request_time = time.monotonic()
            return result.ads
        except lbc.exceptions.LbcException as e:
            log.warning("Erreur Leboncoin : %s", e)
            raise RuntimeError(
                "Leboncoin a temporairement bloqué la requête. Réessaie dans quelques minutes."
            ) from e
        except Exception as e:
            log.exception("Erreur inattendue lors de la recherche Leboncoin")
            raise RuntimeError("Impossible d'interroger Leboncoin pour le moment.") from e


async def search_ads(
    text: str,
    price_max: Optional[int] = None,
    excludes: tuple[str, ...] = (),
    limit: int = 60,
) -> list:
    """Recherche des annonces avec cache mémoire et rate limiting."""
    key = _cache_key(text, price_max, excludes)
    now = time.monotonic()

    cached = _search_cache.get(key)
    if cached and now - cached.timestamp < CACHE_TTL_S:
        log.debug("Cache hit pour %s", key)
        return cached.ads

    location = lbc.City(
        lat=LBC_LAT,
        lng=LBC_LNG,
        radius=LBC_RADIUS,
        city=LBC_CITY,
    )

    kwargs = {
        "text": text,
        "locations": [location],
        "limit": min(limit, 100),
        "sort": lbc.Sort.PRICE_ASC,
        "ad_type": lbc.AdType.OFFER,
    }
    if price_max:
        kwargs["price"] = [0, int(price_max)]

    ads = await _rate_limited_search(**kwargs)

    # Filtre d'exclusion textuelle côté client (lbc ne le fait pas)
    if excludes:
        lower_excludes = [e.lower() for e in excludes]
        ads = [
            ad for ad in ads
            if not any(ex in (ad.subject or "").lower() for ex in lower_excludes)
        ]

    _search_cache[key] = SearchCacheEntry(timestamp=now, ads=ads)
    return ads
