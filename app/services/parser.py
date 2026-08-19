"""Parser local de gastos por texto. No usa LLM."""

from __future__ import annotations

import re
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.models import Category, PersonRole, SplitType

_MONEY = re.compile(
    r"(?<![\d.,])(?:usd|us\$|\$)?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:usd|\$)?(?![\d])",
    re.IGNORECASE,
)

_PERSONAL = {"personal", "propio", "propia", "mio", "mío", "mia", "mía", "mios", "míos"}
_SHARED = {"compartido", "compartida", "conjunto", "conjunta", "hogar", "juntos", "junta"}
_RELATIVE_DAYS = {"hoy": 0, "ayer": -1, "anteayer": -2}
_MONTHS = {
    "enero": 1, "ene": 1,
    "febrero": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "mayo": 5,
    "junio": 6, "jun": 6,
    "julio": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "septiembre": 9, "setiembre": 9, "sep": 9, "set": 9,
    "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12,
}
_MONTH_NAMES = "|".join(sorted(_MONTHS, key=len, reverse=True))
_RELATIVE_RE = re.compile(
    r"(?<!\w)(hoy|ayer|anteayer)(?!\w)",
    re.IGNORECASE,
)
_NAMED_DATE_RE = re.compile(
    rf"(?<!\w)(\d{{1,2}})\s+de\s+({_MONTH_NAMES})(?:\s+de\s+(\d{{4}}))?(?!\w)",
    re.IGNORECASE,
)
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DMY_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?!\d)")

_CATEGORY_WORDS: dict[Category, tuple[str, ...]] = {
    Category.comida: (
        "almuerzo", "desayuno", "cena", "cafe", "café", "comida", "restaurante",
        "almuerzos", "pizza", "hamburguesa", "pollo", "ceviche", "helado",
        "pan", "panaderia", "panadería", "bar", "tragos",
    ),
    Category.supermercado: (
        "super", "supermaxi", "supermercado", "tia", "tía", "aki", "comisariato",
        "mercado", "despensa", "viveres", "víveres",
    ),
    Category.transporte: (
        "uber", "taxi", "bus", "gasolina", "diesel", "diésel", "pasaje",
        "parqueo", "peaje", "cabify", "indrive",
    ),
    Category.vivienda: (
        "arriendo", "alquiler", "renta", "vivienda", "departamento",
    ),
    Category.servicios: (
        "luz", "agua", "internet", "telefono", "teléfono", "celular",
        "plan", "netflix", "spotify", "cnt", "claro", "movistar",
    ),
    Category.salud: (
        "farmacia", "fybeca", "sana", "medico", "médico", "consulta",
        "hospital", "clinica", "clínica", "farmacias",
    ),
    Category.educacion: (
        "colegio", "universidad", "curso", "matricula", "matrícula", "libros",
    ),
    Category.entretenimiento: (
        "cine", "juego", "juegos", "salida", "concierto", "teatro",
    ),
    Category.ropa: (
        "ropa", "zapatos", "zapato", "camisa", "pantalon", "pantalón",
    ),
    Category.mascotas: (
        "mascota", "veterinaria", "vet", "concentrado", "perro", "gato",
    ),
}


@dataclass(frozen=True)
class ParsedExpense:
    amount: Decimal
    description: str
    category: Category
    split_type: SplitType
    paid_by_role: PersonRole | None
    raw: str
    spent_on: date | None = None


def split_hint_from_text(text: str) -> SplitType | None:
    tokens = {t.strip(".,;:").lower() for t in (text or "").split()}
    if tokens & _PERSONAL:
        return SplitType.personal
    if tokens & _SHARED:
        return SplitType.shared
    return None


def local_today() -> date:
    settings = get_settings()
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz).date()


def _safe_date(year: int, month: int, day: int) -> date | None:
    if month < 1 or month > 12:
        return None
    last = monthrange(year, month)[1]
    if day < 1 or day > last:
        return None
    return date(year, month, day)


def _clamp_past(value: date, today: date) -> date:
    if value > today:
        try:
            return value.replace(year=value.year - 1)
        except ValueError:
            return value
    return value


def extract_and_strip_date(text: str, *, today: date | None = None) -> tuple[str, date | None]:
    raw = " ".join((text or "").strip().split())
    if not raw:
        return "", None
    today = today or local_today()

    match = _RELATIVE_RE.search(raw)
    if match:
        spent = today + timedelta(days=_RELATIVE_DAYS[match.group(1).lower()])
        leftover = (raw[: match.start()] + " " + raw[match.end() :]).strip()
        return " ".join(leftover.split()), spent

    match = _NAMED_DATE_RE.search(raw)
    if match:
        day = int(match.group(1))
        month = _MONTHS[match.group(2).lower()]
        year = int(match.group(3)) if match.group(3) else today.year
        spent = _safe_date(year, month, day)
        if spent is not None:
            if match.group(3) is None:
                spent = _clamp_past(spent, today)
            leftover = (raw[: match.start()] + " " + raw[match.end() :]).strip()
            return " ".join(leftover.split()), spent

    match = _ISO_DATE_RE.search(raw)
    if match:
        spent = _safe_date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if spent is not None:
            leftover = (raw[: match.start()] + " " + raw[match.end() :]).strip()
            return " ".join(leftover.split()), spent

    match = _DMY_DATE_RE.search(raw)
    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year_raw = match.group(3)
        if year_raw:
            year = int(year_raw)
            if year < 100:
                year += 2000
        else:
            year = today.year
        spent = _safe_date(year, month, day)
        if spent is not None:
            if year_raw is None:
                spent = _clamp_past(spent, today)
            leftover = (raw[: match.start()] + " " + raw[match.end() :]).strip()
            return " ".join(leftover.split()), spent

    return raw, None


def parse_date_hint(text: str, *, today: date | None = None) -> date | None:
    _leftover, spent = extract_and_strip_date(text, today=today)
    return spent


def parse_fix_message(
    text: str, *, today: date | None = None
) -> tuple[Decimal | None, date | None] | None:
    """Solo monto y/o fecha, sin descripción. Para corregir un pendiente."""
    leftover, spent = extract_and_strip_date(text, today=today)
    amount = parse_amount_only(leftover)
    if amount is not None:
        return amount, spent
    if spent is not None and not leftover:
        return None, spent
    return None


def parse_amount_only(text: str) -> Decimal | None:
    raw = " ".join((text or "").strip().split())
    match = re.fullmatch(
        r"(?:usd|us\$|\$)?\s*(\d{1,6}(?:[.,]\d{1,2})?)\s*(?:usd|\$)?",
        raw,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None
    return amount.quantize(Decimal("0.01"))


def parse_expense_text(text: str, *, today: date | None = None) -> ParsedExpense | None:
    original = " ".join((text or "").strip().split())
    if not original:
        return None
    raw, spent_on = extract_and_strip_date(original, today=today)
    if not raw:
        return None

    matches = list(_MONEY.finditer(raw))
    if not matches:
        return None

    amount_match = matches[-1]
    try:
        amount = Decimal(amount_match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0:
        return None

    without_amount = (raw[: amount_match.start()] + " " + raw[amount_match.end() :]).strip()
    tokens = without_amount.lower().replace("pagó", "pago").replace("pagué", "pago").split()

    settings = get_settings()
    split = (
        SplitType.shared if settings.default_split == "shared" else SplitType.personal
    )
    leftover: list[str] = []
    paid_by_role: PersonRole | None = None
    skip_next = False
    names = {
        settings.person_a_name.strip().lower(): PersonRole.a,
        settings.person_b_name.strip().lower(): PersonRole.b,
    }

    for i, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue
        clean = token.strip(".,;:¡!¿?")
        if clean in _PERSONAL:
            split = SplitType.personal
            continue
        if clean in _SHARED:
            split = SplitType.shared
            continue
        if clean in {"pago", "pagado", "pagó"} and i + 1 < len(tokens):
            nxt = tokens[i + 1].strip(".,;:").lower()
            if nxt in names:
                paid_by_role = names[nxt]
                skip_next = True
                continue
            if nxt in {"yo", "mio", "mío"}:
                paid_by_role = None
                skip_next = True
                continue
        leftover.append(token)

    description = " ".join(leftover).strip(" -") or "Gasto"
    description = description[0].upper() + description[1:] if description else "Gasto"
    category = _guess_category(description.lower())
    return ParsedExpense(
        amount=amount.quantize(Decimal("0.01")),
        description=description,
        category=category,
        split_type=split,
        paid_by_role=paid_by_role,
        raw=original,
        spent_on=spent_on,
    )


def _guess_category(text: str) -> Category:
    for category, words in _CATEGORY_WORDS.items():
        for word in words:
            if word.strip() and word in text:
                return category
    return Category.otros
