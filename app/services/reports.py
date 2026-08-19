"""Resumen mensual, balance de pareja y CSV."""

from __future__ import annotations

import csv
import io
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Expense,
    ExpenseKind,
    ExpenseStatus,
    InvoiceDetail,
    Person,
    PersonRole,
    SplitType,
)
from app.services.expenses import today_in_timezone

_MONTH_NAMES = (
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    last = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


@dataclass
class MonthSummary:
    year: int
    month: int
    total: Decimal = Decimal("0.00")
    personal_a: Decimal = Decimal("0.00")
    personal_b: Decimal = Decimal("0.00")
    shared: Decimal = Decimal("0.00")
    iva: Decimal = Decimal("0.00")
    by_category: dict[str, Decimal] = field(default_factory=dict)
    paid_a: Decimal = Decimal("0.00")
    paid_b: Decimal = Decimal("0.00")
    paid_shared_a: Decimal = Decimal("0.00")
    paid_shared_b: Decimal = Decimal("0.00")
    person_a_name: str = "Mauri"
    person_b_name: str = "Daysi"
    person_a_id: int = 0
    person_b_id: int = 0
    expenses: list[Expense] = field(default_factory=list)

    @property
    def label(self) -> str:
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def spent_text(self) -> str:
        return (
            f"Este mes el hogar gastó ${self.total:.2f}. "
            f"{self.person_a_name} pagó ${self.paid_a:.2f} y "
            f"{self.person_b_name} pagó ${self.paid_b:.2f}."
        )


async def month_summary(year: int | None = None, month: int | None = None) -> MonthSummary:
    settings = get_settings()
    today = today_in_timezone().date()
    year = year or today.year
    month = month or today.month
    start, end = month_bounds(year, month)
    summary = MonthSummary(
        year=year,
        month=month,
        person_a_name=settings.person_a_name,
        person_b_name=settings.person_b_name,
    )
    async with SessionLocal() as session:
        persons = (await session.scalars(select(Person))).all()
        role_ids = {p.role: p.id for p in persons}
        id_a = role_ids.get(PersonRole.a)
        id_b = role_ids.get(PersonRole.b)
        summary.person_a_id = id_a or 0
        summary.person_b_id = id_b or 0
        rows = (
            await session.scalars(
                select(Expense)
                .options(joinedload(Expense.invoice))
                .where(
                    Expense.status == ExpenseStatus.confirmed,
                    Expense.spent_on >= start,
                    Expense.spent_on <= end,
                )
                .order_by(Expense.spent_on.desc(), Expense.id.desc())
            )
        ).unique().all()
        summary.expenses = list(rows)
        for expense in rows:
            amount = Decimal(expense.amount_total)
            summary.total += amount
            cat = expense.category.value if expense.category else "otros"
            summary.by_category[cat] = summary.by_category.get(cat, Decimal("0.00")) + amount
            if expense.paid_by_person_id == id_a:
                summary.paid_a += amount
            elif expense.paid_by_person_id == id_b:
                summary.paid_b += amount
            else:
                summary.paid_a += amount
            if expense.split_type == SplitType.personal:
                if expense.paid_by_person_id == id_a:
                    summary.personal_a += amount
                elif expense.paid_by_person_id == id_b:
                    summary.personal_b += amount
                else:
                    summary.personal_a += amount
            else:
                summary.shared += amount
                if expense.paid_by_person_id == id_a:
                    summary.paid_shared_a += amount
                elif expense.paid_by_person_id == id_b:
                    summary.paid_shared_b += amount
                else:
                    summary.paid_shared_a += amount
            if expense.invoice and expense.invoice.iva_amount:
                summary.iva += Decimal(expense.invoice.iva_amount)
    return summary


def format_month_text(summary: MonthSummary) -> str:
    cats = "\n".join(
        f"  · {name}: ${total:.2f}"
        for name, total in sorted(summary.by_category.items(), key=lambda x: x[1], reverse=True)
    ) or "  (sin gastos)"
    recent = "\n".join(
        f"  · {e.spent_on} {e.description} ${e.amount_total:.2f}"
        for e in summary.expenses[:8]
    ) or "  (sin gastos)"
    return (
        f"Mes {summary.label}\n"
        f"Total del hogar: ${summary.total:.2f}\n"
        f"Pagó {summary.person_a_name}: ${summary.paid_a:.2f}\n"
        f"Pagó {summary.person_b_name}: ${summary.paid_b:.2f}\n"
        f"Gastos conjuntos: ${summary.shared:.2f}\n"
        f"Propios {summary.person_a_name}: ${summary.personal_a:.2f}\n"
        f"Propios {summary.person_b_name}: ${summary.personal_b:.2f}\n"
        f"IVA en facturas: ${summary.iva:.2f}\n"
        f"{summary.spent_text}\n"
        f"Por categoría:\n{cats}\n"
        f"Movimientos:\n{recent}"
    )


async def expenses_csv(year: int, month: int) -> str:
    summary = await month_summary(year, month)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "id",
            "fecha",
            "descripcion",
            "comercio",
            "monto",
            "moneda",
            "categoria",
            "tipo",
            "reparto",
            "estado",
            "pagado_por_id",
            "ruc",
            "razon_social",
            "numero_factura",
            "subtotal",
            "iva",
            "iva_porcentaje",
        ]
    )
    async with SessionLocal() as session:
        for expense in summary.expenses:
            invoice = expense.invoice
            if invoice is None:
                invoice = await session.scalar(
                    select(InvoiceDetail).where(InvoiceDetail.expense_id == expense.id)
                )
            writer.writerow(
                [
                    expense.id,
                    expense.spent_on.isoformat() if expense.spent_on else "",
                    expense.description or "",
                    expense.merchant or "",
                    f"{expense.amount_total:.2f}",
                    expense.currency,
                    expense.category.value if expense.category else "",
                    expense.kind.value if expense.kind else "",
                    expense.split_type.value if expense.split_type else "",
                    expense.status.value if expense.status else "",
                    expense.paid_by_person_id or "",
                    invoice.ruc if invoice else "",
                    invoice.legal_name if invoice else "",
                    invoice.invoice_number if invoice else "",
                    f"{invoice.subtotal:.2f}" if invoice and invoice.subtotal is not None else "",
                    f"{invoice.iva_amount:.2f}" if invoice and invoice.iva_amount is not None else "",
                    f"{invoice.iva_rate:.2f}" if invoice and invoice.iva_rate is not None else "",
                ]
            )
    return buffer.getvalue()


@dataclass
class YearOverview:
    year: int
    person_a_name: str
    person_b_name: str
    months: list[MonthSummary] = field(default_factory=list)
    total: Decimal = Decimal("0.00")
    paid_a: Decimal = Decimal("0.00")
    paid_b: Decimal = Decimal("0.00")
    shared: Decimal = Decimal("0.00")
    personal_a: Decimal = Decimal("0.00")
    personal_b: Decimal = Decimal("0.00")
    iva: Decimal = Decimal("0.00")
    by_category: dict[str, Decimal] = field(default_factory=dict)

    @property
    def spent_text(self) -> str:
        return (
            f"En {self.year} el hogar gastó ${self.total:.2f}. "
            f"{self.person_a_name} pagó ${self.paid_a:.2f} y "
            f"{self.person_b_name} pagó ${self.paid_b:.2f}."
        )


async def year_overview(year: int | None = None) -> YearOverview:
    settings = get_settings()
    today = today_in_timezone().date()
    year = year or today.year
    overview = YearOverview(
        year=year,
        person_a_name=settings.person_a_name,
        person_b_name=settings.person_b_name,
    )
    for month in range(1, 13):
        summary = await month_summary(year, month)
        overview.months.append(summary)
        overview.total += summary.total
        overview.paid_a += summary.paid_a
        overview.paid_b += summary.paid_b
        overview.shared += summary.shared
        overview.personal_a += summary.personal_a
        overview.personal_b += summary.personal_b
        overview.iva += summary.iva
        for name, total in summary.by_category.items():
            overview.by_category[name] = overview.by_category.get(name, Decimal("0.00")) + total
    return overview


def _format_month_block(summary: MonthSummary) -> str:
    name = _MONTH_NAMES[summary.month]
    cats = "\n".join(
        f"  · {cat}: ${total:.2f}"
        for cat, total in sorted(summary.by_category.items(), key=lambda x: x[1], reverse=True)
    ) or "  (sin gastos)"
    return (
        f"{name} {summary.year}\n"
        f"Total del hogar: ${summary.total:.2f}\n"
        f"Pagó {summary.person_a_name}: ${summary.paid_a:.2f}\n"
        f"Pagó {summary.person_b_name}: ${summary.paid_b:.2f}\n"
        f"Gastos conjuntos: ${summary.shared:.2f}\n"
        f"Propios {summary.person_a_name}: ${summary.personal_a:.2f}\n"
        f"Propios {summary.person_b_name}: ${summary.personal_b:.2f}\n"
        f"IVA en facturas: ${summary.iva:.2f}\n"
        f"Por categoría:\n{cats}"
    )


def format_year_summary(overview: YearOverview) -> str:
    cats = "\n".join(
        f"  · {name}: ${total:.2f}"
        for name, total in sorted(overview.by_category.items(), key=lambda x: x[1], reverse=True)
    ) or "  (sin gastos)"
    active = [
        _MONTH_NAMES[summary.month]
        for summary in overview.months
        if summary.total > 0
    ]
    meses = ", ".join(active) if active else "ninguno"
    return (
        f"Resumen {overview.year}\n"
        f"{overview.spent_text}\n"
        f"Gastos conjuntos: ${overview.shared:.2f}\n"
        f"Propios {overview.person_a_name}: ${overview.personal_a:.2f}\n"
        f"Propios {overview.person_b_name}: ${overview.personal_b:.2f}\n"
        f"IVA en facturas: ${overview.iva:.2f}\n"
        f"Meses con gastos: {meses}\n"
        f"Por categoría:\n{cats}"
    )


def format_year_text(overview: YearOverview) -> str:
    return "\n\n".join(format_year_messages(overview))


def format_year_messages(overview: YearOverview) -> list[str]:
    blocks = [
        _format_month_block(summary)
        for summary in overview.months
        if summary.total > 0
    ]
    summary = format_year_summary(overview)
    if not blocks:
        return [f"Año {overview.year}\n\n(sin gastos confirmados este año)\n\n{summary}"]

    messages: list[str] = []
    current = f"Año {overview.year}\n"
    for block in blocks:
        candidate = f"{current}\n{block}\n"
        if len(candidate) > 3500 and current.strip() != f"Año {overview.year}":
            messages.append(current.strip())
            current = f"Año {overview.year} (sigue)\n\n{block}\n"
        else:
            current = candidate
    if len(current) + len(summary) + 2 > 3500:
        messages.append(current.strip())
        messages.append(summary)
    else:
        messages.append(f"{current.strip()}\n\n{summary}")
    return messages
