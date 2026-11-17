import os
import logging
from typing import Optional

log = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")


async def extract_from_image(image_bytes: bytes) -> Optional[dict]:
    """Extrait les informations d'une annonce depuis une capture d'écran via Gemini."""
    if not GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY absente, analyse d'image désactivée")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = (
            "Analyse cette capture d'écran d'annonce Leboncoin. "
            "Extrais les informations suivantes au format JSON strict : "
            '{"titre": "...", "prix": 123.45, "description": "...", '
            '"vendeur_anciennete_jours": null, "vendeur_note": null, '
            '"livraison": true/false, "localisation": "..."}. '
            "Si une information est absente, mets null. Réponds UNIQUEMENT avec le JSON."
        )

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )

        import json
        text = response.text.strip()
        # Nettoyer les éventuels backticks
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(text)
    except Exception as e:
        log.exception("Erreur lors de l'extraction Gemini")
        return None
