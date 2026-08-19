"""Schema Pydantic de extracción (fotos/PDF)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models import Category


class InvoiceExtract(BaseModel):
    ruc: str | None = None
    legal_name: str | None = None
    invoice_number: str | None = None
    authorization_sri: str | None = None
    subtotal: Decimal | None = None
    iva_amount: Decimal | None = None
    iva_rate: Decimal | None = None


class ExtractionResult(BaseModel):
    kind: Literal["expense", "invoice"] = "expense"
    spent_on: date | None = None
    amount_total: Decimal | None = None
    currency: str = "USD"
    merchant: str = ""
    description: str = ""
    category: Category = Category.otros
    split_type: Literal["shared", "personal", "unknown"] = "unknown"
    paid_by_hint: Literal["a", "b", "unknown"] = "unknown"
    confidence: float = 0.7
    needs_user_input: list[str] = Field(default_factory=list)
    invoice: InvoiceExtract | None = None
    raw_summary: str = ""

    @field_validator("category", mode="before")
    @classmethod
    def _category(cls, value: object) -> object:
        if isinstance(value, str):
            try:
                return Category(value.lower())
            except ValueError:
                return Category.otros
        return value

    @property
    def has_amount(self) -> bool:
        return self.amount_total is not None and self.amount_total > 0

    @property
    def is_invoice(self) -> bool:
        ruc = (self.invoice.ruc if self.invoice else None) or ""
        return self.kind == "invoice" or bool(ruc.strip())

    @property
    def low_confidence(self) -> bool:
        return self.confidence < 0.55
