import re
import statistics
from typing import Optional

# Mots-clés indiquant une annonce non fonctionnelle ou hors sujet
BAD_KEYWORDS = [
    "hs", "hors service", "pour pièces", "pour piece", "pièces détachées",
    "coque", "support", "câble", "cable", "chargeur", "adaptateur",
    "notice", "manuel", "boîte vide", "boite vide", "emballage",
]


def normalize_model(text: str) -> str:
    """Normalise un nom de modèle pour comparaison (« 3070ti » → « 3070 ti »)."""
    text = text.lower().strip()
    text = re.sub(r"(\d)([a-z])", r"\1 \2", text)
    text = re.sub(r"([a-z])(\d)", r"\1 \2", text)
    text = re.sub(r"\s+", " ", text)
    return text


def is_relevant(ad_subject: str, query: str) -> bool:
    """Vérifie que l'annonce correspond réellement au produit recherché."""
    subject_norm = normalize_model(ad_subject)
    query_norm = normalize_model(query)
    if query_norm not in subject_norm:
        return False
    for bad in BAD_KEYWORDS:
        if bad in subject_norm:
            return False
    return True


def compute_stats(prices: list[float]) -> dict:
    """Calcule médiane et P25 en écartant les valeurs aberrantes."""
    if not prices:
        return {"median": 0.0, "p25": 0.0, "count": 0, "outliers_removed": 0}

    raw_median = statistics.median(prices)
    lower = raw_median * 0.20
    upper = raw_median * 3.00

    cleaned = [p for p in prices if lower <= p <= upper]
    if not cleaned:
        return {"median": raw_median, "p25": raw_median, "count": len(prices), "outliers_removed": 0}

    return {
        "median": statistics.median(cleaned),
        "p25": statistics.quantiles(cleaned, n=4)[0] if len(cleaned) >= 2 else cleaned[0],
        "count": len(cleaned),
        "outliers_removed": len(prices) - len(cleaned),
    }


def rank_deals(ads: list, stats: dict, min_discount_pct: float = 20.0) -> list[dict]:
    """
    Classe les deals par score décroissant.
    Score = remise + bonus livraison + bonus France − malus étranger − malus sans livraison.
    Les prix suspects (<25% de la médiane) sont relégués en bas.
    """
    median = stats.get("median", 0)
    if median <= 0:
        return []

    ranked = []
    for ad in ads:
        price = ad.price or 0
        if price <= 0:
            continue
        discount_pct = ((median - price) / median) * 100
        if discount_pct < min_discount_pct:
            continue

        score = discount_pct

        # Livraison
        if getattr(ad, "shippable", False):
            score += 10
        else:
            score -= 10

        # Localisation vendeur (France vs étranger)
        location = (getattr(ad, "location", "") or "").lower()
        if any(x in location for x in ["france", "paris", "lyon", "marseille", "toulouse"]):
            score += 15
        elif any(x in location for x in ["belgique", "suisse", "luxembourg", "etranger", "étranger"]):
            score -= 20

        suspect = discount_pct > 75  # prix < 25% de la médiane
        if suspect:
            score -= 1000  # relégué en bas

        ranked.append({
            "ad": ad,
            "price": price,
            "median": median,
            "discount_pct": round(discount_pct, 1),
            "score": round(score, 1),
            "suspect": suspect,
        })

    ranked.sort(key=lambda x: (-x["score"], x["price"]))
    return ranked


def top_deals(ads: list, query: str, price_max: Optional[int] = None, limit: int = 5) -> list[dict]:
    """Retourne les N meilleures offres pertinentes avec statistiques."""
    relevant = [ad for ad in ads if is_relevant(ad.subject or "", query)]
    if price_max:
        relevant = [ad for ad in relevant if (ad.price or 0) <= price_max]

    prices = [float(ad.price) for ad in relevant if (ad.price or 0) > 0]
    stats = compute_stats(prices)
    return rank_deals(relevant, stats, min_discount_pct=10)[:limit]
