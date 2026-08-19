"""Panel web: recuento mensual y edición."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from sqlalchemy import select

from app.config import TEMPLATES_DIR, get_settings
from app.db import SessionLocal
from app.models import Category, Person, PersonRole, SplitType
from app.services.charts import month_chart_payload
from app.services.expenses import confirm_expense, delete_expense, list_pending, today_in_timezone, update_expense
from app.services.reports import expenses_csv, month_summary, year_overview
from app.web.auth import require_panel

router = APIRouter(dependencies=[Depends(require_panel)])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
settings = get_settings()


def _month_from_request(year: int | None, month: int | None) -> tuple[int, int]:
    today = today_in_timezone().date()
    return year or today.year, month or today.month


def _parse_form_date(raw: str) -> date | None:
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    year: int | None = None,
    month: int | None = None,
    facturas: int = 0,
) -> HTMLResponse:
    year, month = _month_from_request(year, month)
    summary = await month_summary(year, month)
    overview = await year_overview(year)
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    expenses = summary.expenses
    if facturas:
        expenses = [e for e in expenses if e.kind.value == "invoice" or (e.invoice and e.invoice.ruc)]

    async with SessionLocal() as session:
        persons = {p.role: p for p in (await session.scalars(select(Person))).all()}
    person_a_id = persons[PersonRole.a].id if PersonRole.a in persons else 0
    person_b_id = persons[PersonRole.b].id if PersonRole.b in persons else 0
    max_cat = max(summary.by_category.values()) if summary.by_category else 1
    categories = [
        {"name": name, "total": total, "pct": int((total / max_cat) * 100)}
        for name, total in sorted(summary.by_category.items(), key=lambda x: x[1], reverse=True)
    ]
    bot_running = bool(getattr(request.app.state, "bot_running", False))
    color_a, color_b = settings.chart_colors
    months_es = (
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
    paid_sum = summary.paid_a + summary.paid_b
    paid_a_pct = int((summary.paid_a / paid_sum) * 100) if paid_sum else 0
    paid_b_pct = 100 - paid_a_pct if paid_sum else 0
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "title": "Contabilizador",
            "phase": 11,
            "summary": summary,
            "overview": overview,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "expenses": expenses,
            "pending": await list_pending(limit=20),
            "categories": categories,
            "facturas": facturas,
            "category_values": [c.value for c in Category],
            "person_a": settings.person_a_name,
            "person_b": settings.person_b_name,
            "person_a_id": person_a_id,
            "person_b_id": person_b_id,
            "bot_username": settings.telegram_bot_username,
            "bot_running": bot_running,
            "gemini_ok": settings.gemini_configured,
            "color_a": color_a,
            "color_b": color_b,
            "month_name": months_es[month],
            "months_es": months_es,
            "paid_a_pct": paid_a_pct,
            "paid_b_pct": paid_b_pct,
            "chart_data": month_chart_payload(summary),
        },
    )


@router.post("/expenses/{expense_id}/update")
async def update_row(
    expense_id: int,
    year: int = Form(),
    month: int = Form(),
    category: str = Form(),
    split_type: str = Form(),
    paid_by: str = Form(),
    amount: str = Form(""),
    spent_on: str = Form(""),
) -> RedirectResponse:
    parsed_amount = None
    raw = (amount or "").strip().replace(",", ".")
    if raw:
        try:
            parsed_amount = Decimal(raw)
        except InvalidOperation:
            parsed_amount = None
    await update_expense(
        expense_id,
        category=Category(category),
        split_type=SplitType(split_type),
        paid_by_role=PersonRole.a if paid_by == "a" else PersonRole.b,
        amount_total=parsed_amount,
        spent_on=_parse_form_date(spent_on),
    )
    return RedirectResponse(f"/?year={year}&month={month}", status_code=303)


@router.post("/expenses/{expense_id}/delete")
async def delete_row(expense_id: int, year: int = Form(), month: int = Form()) -> RedirectResponse:
    await delete_expense(expense_id)
    return RedirectResponse(f"/?year={year}&month={month}", status_code=303)


@router.post("/expenses/{expense_id}/confirm")
async def confirm_row(expense_id: int, year: int = Form(), month: int = Form()) -> RedirectResponse:
    await confirm_expense(expense_id)
    return RedirectResponse(f"/?year={year}&month={month}", status_code=303)


@router.get("/export.csv")
async def export_csv(year: int | None = None, month: int | None = None) -> Response:
    year, month = _month_from_request(year, month)
    content = await expenses_csv(year, month)
    filename = f"gastos-{year:04d}-{month:02d}.csv"
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
