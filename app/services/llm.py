"""Extracción de tickets/facturas con Gemini (Groq de respaldo)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.config import get_settings
from app.services.extraction import ExtractionResult
from app.services.parser import local_today

logger = logging.getLogger(__name__)


def _prompt() -> str:
    today = local_today()
    return f"""Eres un extractor de gastos para Ecuador (USD).
Hoy es {today.isoformat()}. Analiza el comprobante (ticket, factura o PDF) y devuelve SOLO JSON con:
{{
  "kind": "expense" o "invoice",
  "spent_on": "YYYY-MM-DD" o null,
  "amount_total": número (total a pagar),
  "currency": "USD",
  "merchant": "comercio o razón social corta",
  "description": "qué se compró, 1 línea",
  "category": una de: comida, supermercado, transporte, vivienda, servicios, salud, educacion, entretenimiento, ropa, mascotas, otros,
  "split_type": "shared" (conjunto del hogar), "personal" (gasto propio de quien pagó) o "unknown",
  "paid_by_hint": "a", "b" o "unknown",
  "confidence": 0 a 1,
  "needs_user_input": [],
  "invoice": {{
    "ruc": string o null,
    "legal_name": string o null,
    "invoice_number": string o null,
    "authorization_sri": string o null,
    "subtotal": número o null,
    "iva_amount": número o null,
    "iva_rate": 15, 5, 0 o null
  }},
  "raw_summary": "una oración"
}}
kind=invoice SOLO si hay RUC o es factura SRI. Si es ticket de restaurante sin RUC, kind=expense e invoice en null.
amount_total es el TOTAL, no el subtotal.
spent_on es la fecha del comprobante. Si el año no se lee, usa {today.year}. No uses un año anterior a {today.year - 1}.
"""


class ExtractionError(Exception):
    pass


def _parse_json(text: str) -> dict:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ExtractionError("El modelo no devolvió JSON.")
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ExtractionError("JSON inválido.")
    return data


async def extract_from_file(path: Path, mime_type: str, caption: str = "") -> ExtractionResult:
    settings = get_settings()
    extra = f"\nTexto extra del usuario: {caption}" if caption else ""
    if settings.llm_provider == "groq" or not settings.gemini_configured:
        if settings.groq_api_key:
            return await _extract_groq(path, mime_type, extra)
        raise ExtractionError("No hay API key de Gemini configurada.")
    try:
        return await _extract_gemini(path, mime_type, extra)
    except Exception as exc:
        logger.warning("Gemini falló: %s", exc)
        if settings.groq_api_key:
            return await _extract_groq(path, mime_type, extra)
        raise ExtractionError(f"No pude leer el comprobante: {exc}") from exc


async def _extract_gemini(path: Path, mime_type: str, extra: str) -> ExtractionResult:
    from google import genai
    from google.genai import types

    settings = get_settings()
    data = path.read_bytes()
    client = genai.Client(api_key=settings.gemini_api_key)
    response = await client.aio.models.generate_content(
        model=settings.gemini_model,
        contents=[
            types.Part.from_bytes(data=data, mime_type=mime_type),
            _prompt() + extra,
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        ),
    )
    text = getattr(response, "text", None) or ""
    if not text and getattr(response, "candidates", None):
        text = response.candidates[0].content.parts[0].text
    return ExtractionResult.model_validate(_parse_json(text))


async def _extract_groq(path: Path, mime_type: str, extra: str) -> ExtractionResult:
    import base64

    import httpx

    settings = get_settings()
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "model": settings.groq_model,
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt() + extra},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                    },
                ],
            }
        ],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.groq_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
    return ExtractionResult.model_validate(_parse_json(text))
