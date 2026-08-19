"""Alta y confirmación de gastos."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Category,
    Expense,
    ExpenseKind,
    ExpenseStatus,
    InvoiceDetail,
    Person,
    PersonRole,
    SplitType,
)
from app.services.extraction import ExtractionResult
from app.services.parser import ParsedExpense

_CATEGORY_LABEL = {
    Category.comida: "comida",
    Category.supermercado: "supermercado",
    Category.transporte: "transporte",
    Category.vivienda: "vivienda",
    Category.servicios: "servicios",
    Category.salud: "salud",
    Category.educacion: "educacion",
    Category.entretenimiento: "entretenimiento",
    Category.ropa: "ropa",
    Category.mascotas: "mascotas",
    Category.otros: "otros",
}


def today_in_timezone() -> datetime:
    settings = get_settings()
    try:
        tz = ZoneInfo(settings.timezone)
    except Exception:
        tz = ZoneInfo("UTC")
    return datetime.now(tz)


def spent_on_for_capture(
    extracted: date | None,
    today: date | None = None,
    *,
    caption_date: date | None = None,
) -> date:
    """Fecha del gasto al registrar. El pie de foto gana; si el ticket parece de otro mes/año, usamos hoy."""
    today = today or today_in_timezone().date()
    if caption_date is not None:
        return caption_date
    if extracted is None:
        return today
    spent = extracted
    if spent.year != today.year:
        try:
            spent = spent.replace(year=today.year)
        except ValueError:
            return today
    if spent > today:
        return today
    if abs((today - spent).days) <= 7:
        return spent
    return today


async def _person_by_role(session, role: PersonRole) -> Person | None:
    return await session.scalar(select(Person).where(Person.role == role))


async def create_pending_expense(
    *,
    created_by: Person,
    parsed: ParsedExpense,
    chat_id: int | None,
    message_id: int | None,
) -> Expense:
    settings = get_settings()
    async with SessionLocal() as session:
        paid_by_id = created_by.id
        if parsed.paid_by_role is not None:
            other = await _person_by_role(session, parsed.paid_by_role)
            if other is not None:
                paid_by_id = other.id

        expense = Expense(
            household_id=created_by.household_id,
            created_by_person_id=created_by.id,
            paid_by_person_id=paid_by_id,
            split_type=parsed.split_type,
            kind=ExpenseKind.expense,
            status=ExpenseStatus.pending_confirm,
            spent_on=parsed.spent_on or today_in_timezone().date(),
            amount_total=parsed.amount,
            currency=settings.currency,
            merchant=parsed.description,
            description=parsed.description,
            category=parsed.category,
            confidence=Decimal("1.00"),
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
        )
        session.add(expense)
        await session.commit()
        await session.refresh(expense)
        return expense


async def create_pending_from_extraction(
    *,
    created_by: Person,
    extracted: ExtractionResult,
    chat_id: int | None,
    message_id: int | None,
    source_file_path: str | None,
    split_override: SplitType | None = None,
    caption_date: date | None = None,
) -> Expense:
    if not extracted.has_amount or extracted.amount_total is None:
        raise ValueError("No hay monto")
    settings = get_settings()
    async with SessionLocal() as session:
        paid_by_id = created_by.id
        if extracted.paid_by_hint == "a":
            other = await _person_by_role(session, PersonRole.a)
            if other:
                paid_by_id = other.id
        elif extracted.paid_by_hint == "b":
            other = await _person_by_role(session, PersonRole.b)
            if other:
                paid_by_id = other.id

        if split_override is not None:
            split = split_override
        elif extracted.split_type == "personal":
            split = SplitType.personal
        elif extracted.split_type == "shared":
            split = SplitType.shared
        else:
            split = (
                SplitType.shared
                if settings.default_split == "shared"
                else SplitType.personal
            )

        kind = ExpenseKind.invoice if extracted.is_invoice else ExpenseKind.expense
        description = extracted.description or extracted.merchant or "Comprobante"
        today = today_in_timezone().date()
        expense = Expense(
            household_id=created_by.household_id,
            created_by_person_id=created_by.id,
            paid_by_person_id=paid_by_id,
            split_type=split,
            kind=kind,
            status=ExpenseStatus.pending_confirm,
            spent_on=spent_on_for_capture(
                extracted.spent_on, today, caption_date=caption_date
            ),
            amount_total=extracted.amount_total,
            currency=extracted.currency or settings.currency,
            merchant=extracted.merchant or description,
            description=description,
            category=extracted.category,
            confidence=Decimal(str(round(extracted.confidence, 2))),
            telegram_chat_id=chat_id,
            telegram_message_id=message_id,
            source_file_path=source_file_path,
            notes=extracted.raw_summary or None,
        )
        session.add(expense)
        await session.flush()
        if extracted.is_invoice and extracted.invoice:
            inv = extracted.invoice
            session.add(
                InvoiceDetail(
                    expense_id=expense.id,
                    ruc=inv.ruc,
                    legal_name=inv.legal_name,
                    invoice_number=inv.invoice_number,
                    authorization_sri=inv.authorization_sri,
                    subtotal=inv.subtotal,
                    iva_amount=inv.iva_amount,
                    iva_rate=inv.iva_rate,
                )
            )
        await session.commit()
        await session.refresh(expense)
        return expense


async def latest_confirmed() -> Expense | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(Expense)
            .where(Expense.status == ExpenseStatus.confirmed)
            .order_by(Expense.id.desc())
            .limit(1)
        )


async def get_expense(expense_id: int) -> Expense | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(Expense)
            .options(joinedload(Expense.household), joinedload(Expense.invoice))
            .where(Expense.id == expense_id)
        )


async def confirm_expense(expense_id: int) -> Expense | None:
    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)
        if expense is None or expense.status != ExpenseStatus.pending_confirm:
            return expense if expense is not None and expense.status == ExpenseStatus.confirmed else None
        expense.status = ExpenseStatus.confirmed
        await session.commit()
        await session.refresh(expense)
        return expense


async def set_split(expense_id: int, split: SplitType) -> Expense | None:
    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)
        if expense is None:
            return None
        expense.split_type = split
        await session.commit()
        await session.refresh(expense)
        return expense


async def reject_expense(expense_id: int) -> Expense | None:
    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)
        if expense is None:
            return None
        expense.status = ExpenseStatus.rejected
        await session.commit()
        await session.refresh(expense)
        return expense


async def set_paid_by(expense_id: int, role: PersonRole) -> Expense | None:
    async with SessionLocal() as session:
        person = await _person_by_role(session, role)
        expense = await session.get(Expense, expense_id)
        if expense is None or person is None:
            return None
        expense.paid_by_person_id = person.id
        await session.commit()
        await session.refresh(expense)
        return expense


async def list_pending(household_id: int | None = None, limit: int = 10) -> list[Expense]:
    async with SessionLocal() as session:
        stmt = (
            select(Expense)
            .where(Expense.status == ExpenseStatus.pending_confirm)
            .order_by(Expense.id.desc())
            .limit(limit)
        )
        if household_id is not None:
            stmt = stmt.where(Expense.household_id == household_id)
        rows = (await session.scalars(stmt)).all()
        return list(rows)


async def latest_pending_for_person(person_id: int) -> Expense | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(Expense)
            .where(
                Expense.created_by_person_id == person_id,
                Expense.status == ExpenseStatus.pending_confirm,
            )
            .order_by(Expense.id.desc())
            .limit(1)
        )


async def update_pending_fields(
    expense_id: int,
    *,
    amount: Decimal | None = None,
    spent_on: date | None = None,
) -> Expense | None:
    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)
        if expense is None or expense.status != ExpenseStatus.pending_confirm:
            return None
        if amount is not None and amount > 0:
            expense.amount_total = amount.quantize(Decimal("0.01"))
        if spent_on is not None:
            expense.spent_on = spent_on
        await session.commit()
        await session.refresh(expense)
        return expense


async def update_amount(expense_id: int, amount: Decimal) -> Expense | None:
    return await update_pending_fields(expense_id, amount=amount)


async def find_duplicate(household_id: int, amount: Decimal, spent_on) -> Expense | None:
    async with SessionLocal() as session:
        return await session.scalar(
            select(Expense)
            .where(
                Expense.household_id == household_id,
                Expense.status == ExpenseStatus.confirmed,
                Expense.spent_on == spent_on,
                Expense.amount_total == amount.quantize(Decimal("0.01")),
            )
            .order_by(Expense.id.desc())
            .limit(1)
        )


async def delete_expense(expense_id: int) -> bool:
    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)
        if expense is None:
            return False
        invoice = await session.scalar(
            select(InvoiceDetail).where(InvoiceDetail.expense_id == expense_id)
        )
        if invoice is not None:
            await session.delete(invoice)
        await session.delete(expense)
        await session.commit()
        return True


async def update_expense(
    expense_id: int,
    *,
    category: Category | None = None,
    split_type: SplitType | None = None,
    paid_by_role: PersonRole | None = None,
    amount_total: Decimal | None = None,
    spent_on: date | None = None,
) -> Expense | None:
    async with SessionLocal() as session:
        expense = await session.get(Expense, expense_id)
        if expense is None:
            return None
        if category is not None:
            expense.category = category
        if split_type is not None:
            expense.split_type = split_type
        if paid_by_role is not None:
            person = await _person_by_role(session, paid_by_role)
            if person is not None:
                expense.paid_by_person_id = person.id
        if amount_total is not None and amount_total > 0:
            expense.amount_total = amount_total.quantize(Decimal("0.01"))
        if spent_on is not None:
            expense.spent_on = spent_on
        await session.commit()
        await session.refresh(expense)
        return expense


async def format_expense(expense: Expense) -> str:
    settings = get_settings()
    async with SessionLocal() as session:
        payer = None
        if expense.paid_by_person_id:
            payer = await session.get(Person, expense.paid_by_person_id)
        split = "conjunto" if expense.split_type == SplitType.shared else "propio"
        status = {
            ExpenseStatus.pending_confirm: "por confirmar",
            ExpenseStatus.confirmed: "confirmado",
            ExpenseStatus.rejected: "cancelado",
        }[expense.status]
        amount = f"{expense.amount_total:.2f}"
        cat = _CATEGORY_LABEL.get(expense.category, expense.category.value)
        payer_name = payer.name if payer else settings.person_a_name
        fecha = expense.spent_on.isoformat() if expense.spent_on else ""
        kind = "factura" if expense.kind == ExpenseKind.invoice else "gasto"
        lines = [
            f"{expense.description} · ${amount} {expense.currency} ({kind})",
            f"Categoría: {cat}",
            f"Pagó: {payer_name} · {split}",
            f"Fecha: {fecha}",
            f"Estado: {status}",
        ]
        invoice = await session.scalar(
            select(InvoiceDetail).where(InvoiceDetail.expense_id == expense.id)
        )
        if invoice and (invoice.ruc or invoice.iva_amount is not None):
            iva = f"{invoice.iva_amount:.2f}" if invoice.iva_amount is not None else "-"
            lines.append(
                f"Factura RUC {invoice.ruc or '-'} · IVA ${iva}"
                + (f" ({invoice.iva_rate}%)" if invoice.iva_rate is not None else "")
            )
        return "\n".join(lines)
