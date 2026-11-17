import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrustResult:
    score: int
    verdict: str
    reasons: list[str]


def score_listing(
    *,
    title: str,
    price: Optional[float],
    median: Optional[float],
    description: str = "",
    seller_age_days: Optional[int] = None,
    seller_rating: Optional[float] = None,
    shippable: bool = False,
    seller_location: str = "",
) -> TrustResult:
    score = 0
    reasons: list[str] = []

    # --- Prix vs médiane ---
    if price and median and median > 0:
        ratio = price / median
        if ratio < 0.25:
            score += 40
            reasons.append(f"Prix anormalement bas ({ratio*100:.0f}% de la médiane)")
        elif ratio < 0.50:
            score += 20
            reasons.append(f"Prix bien en dessous du marché ({ratio*100:.0f}% de la médiane)")

    # --- Contact hors plateforme ---
    contact_patterns = [
        (r"whatsapp", "Mention de WhatsApp"),
        (r"telegram", "Mention de Telegram"),
        (r"@\w+\.\w+", "Adresse e-mail dans l'annonce"),
        (r"06\s?\d{2}\s?\d{2}\s?\d{2}\s?\d{2}", "Numéro de téléphone dans l'annonce"),
    ]
    text = f"{title} {description}".lower()
    for pattern, label in contact_patterns:
        if re.search(pattern, text):
            score += 25
            reasons.append(label)

    # --- Phrases de pression ---
    pressure_phrases = [
        "urgence", "urgent", "dernier prix", "ne réponds pas aux",
        "premier arrivé", "premier servi", "aujourd'hui seulement",
        "nombreux intéressés", "déjà plusieurs personnes",
    ]
    for phrase in pressure_phrases:
        if phrase in text:
            score += 15
            reasons.append(f"Phrase de pression : « {phrase} »")
            break

    # --- Ancienneté vendeur ---
    if seller_age_days is not None:
        if seller_age_days < 7:
            score += 20
            reasons.append("Compte vendeur très récent (< 7 jours)")
        elif seller_age_days < 30:
            score += 10
            reasons.append("Compte vendeur récent (< 30 jours)")

    # --- Notes vendeur ---
    if seller_rating is not None:
        if seller_rating < 3.0:
            score += 20
            reasons.append(f"Note vendeur faible ({seller_rating}/5)")
        elif seller_rating < 4.0:
            score += 10
            reasons.append(f"Note vendeur moyenne ({seller_rating}/5)")

    # --- Absence de livraison ---
    if not shippable:
        score += 15
        reasons.append("Pas de livraison proposée (remise en main propre uniquement)")

    # --- Localisation étrangère ---
    if seller_location:
        loc = seller_location.lower()
        if any(x in loc for x in ["belgique", "suisse", "luxembourg", "allemagne", "espagne", "italie"]):
            score += 25
            reasons.append("Vendeur localisé à l'étranger")

    score = min(score, 100)

    if score <= 15:
        verdict = "✅ Fiable"
    elif score <= 40:
        verdict = "⚠️ Prudence"
    elif score <= 65:
        verdict = "🟠 Risque modéré"
    else:
        verdict = "🚫 Risque élevé"

    return TrustResult(score=score, verdict=verdict, reasons=reasons)
