import json
import os
from pathlib import Path

DATA_DIR = Path(os.getenv("BOT_DATA_DIR", "./data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

SEEN_ADS_FILE = DATA_DIR / "seen_ads.json"
RADARS_FILE = DATA_DIR / "radars.json"


def _load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return default


def _save_json(path: Path, data):
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


# ---------- Annonces déjà vues ----------

def load_seen_ads() -> dict[str, list[str]]:
    return _load_json(SEEN_ADS_FILE, {})


def save_seen_ads(seen: dict[str, list[str]]):
    _save_json(SEEN_ADS_FILE, seen)


def mark_ads_seen(radar_id: str, ad_ids: list[str]):
    seen = load_seen_ads()
    current = set(seen.get(radar_id, []))
    current.update(ad_ids)
    seen[radar_id] = list(current)[-5000:]  # garder un historique borné
    save_seen_ads(seen)


def is_ad_seen(radar_id: str, ad_id: str) -> bool:
    seen = load_seen_ads()
    return ad_id in set(seen.get(radar_id, []))


# ---------- Radars ----------

def load_radars() -> dict[str, dict]:
    return _load_json(RADARS_FILE, {})


def save_radars(radars: dict[str, dict]):
    _save_json(RADARS_FILE, radars)


def upsert_radar(radar_id: str, config: dict):
    radars = load_radars()
    radars[radar_id] = config
    save_radars(radars)


def remove_radar(radar_id: str):
    radars = load_radars()
    radars.pop(radar_id, None)
    save_radars(radars)
