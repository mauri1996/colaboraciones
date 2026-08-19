"""Handlers de Telegram: gastos, fotos, facturas y recuento."""

from __future__ import annotations

import uuid
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, Update
from telegram.ext import ContextTypes

from app.config import INBOX_DIR, get_settings
from app.models import ExpenseStatus, PersonRole, SplitType
from app.services.expenses import (
    confirm_expense,
    create_pending_expense,
    create_pending_from_extraction,
    find_duplicate,
    format_expense,
    get_expense,
    latest_confirmed,
    latest_pending_for_person,
    list_pending,
    reject_expense,
    set_paid_by,
    set_split,
    today_in_timezone,
    update_pending_fields,
)
from app.services.household import bind_telegram_user, get_person_by_telegram_id, is_household_member
from app.services.llm import ExtractionError, extract_from_file
from app.services.parser import parse_date_hint, parse_expense_text, parse_fix_message, split_hint_from_text
from app.services.charts import render_month_charts
from app.services.reports import expenses_csv, format_month_text, format_year_messages, month_summary, year_overview

NOT_IN_HOUSEHOLD = "No estás en el hogar."
USAGE = (
    "Registro de compras y gastos del hogar (finanzas conjuntas).\n"
    "• texto: almuerzo 8.50  ·  almuerzo 8.50 ayer\n"
    "• foto o PDF de ticket/factura\n"
    "• propio: farmacia 12 propio\n"
    "• corregir: pulsa Corregir y manda 8.50, ayer o 15/08\n\n"
    "Todos los comandos: /ayuda"
)


def help_text() -> str:
    settings = get_settings()
    a = settings.person_a_name
    b = settings.person_b_name
    return (
        "Contabilizador — finanzas conjuntas del hogar.\n"
        "No hay deudas ni “le debe a”. Solo cuánto gastamos y quién pagó.\n\n"
        "Cómo registrar\n"
        "• texto: almuerzo 8.50\n"
        "• con fecha: almuerzo 8.50 ayer  ·  uber 4,20 15/08\n"
        "• propio: farmacia 12 propio\n"
        "• foto o PDF de ticket/factura (el pie puede decir ayer)\n"
        "• Corregir: monto o fecha (8.50, ayer, 15/08)\n"
        "• Cancelar: descarta el pendiente\n\n"
        "Comandos\n"
        "/start — ver tu ID y si ya estás en el hogar\n"
        f"/soy — vincularte: /soy {a} o /soy {b}\n"
        "/gasto — registrar por texto: /gasto almuerzo 8.50\n"
        "/mes — cuánto gastó el hogar este mes (o /mes 2026-07)\n"
        f"/pagos — cuánto pagó {a} y cuánto pagó {b} este mes\n"
        "/balance — igual que /pagos (no es deuda)\n"
        "/anio — detalle de cada mes y resumen del año (o /anio 2026)\n"
        "/grafico o /graph — cuánto pagó cada uno y gastos por día (o /grafico 2026-07)\n"
        "/cierre — cierre del mes: totales del mes actual\n"
        "/exportar — CSV del mes\n"
        "/pendientes — gastos que aún no confirmaste\n"
        "/ayuda o /help — esta lista"
    )


def _user_id(update: Update) -> int | None:
    user = update.effective_user
    if user is None or user.is_bot:
        return None
    return user.id


def _confirm_keyboard(expense_id: int) -> InlineKeyboardMarkup:
    eid = str(expense_id)
    settings = get_settings()
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Confirmar", callback_data=f"e:ok:{eid}"),
                InlineKeyboardButton("Conjunto", callback_data=f"e:sha:{eid}"),
                InlineKeyboardButton("Propio", callback_data=f"e:per:{eid}"),
            ],
            [
                InlineKeyboardButton(f"Pagó {settings.person_a_name}", callback_data=f"e:pa:{eid}:a"),
                InlineKeyboardButton(f"Pagó {settings.person_b_name}", callback_data=f"e:pa:{eid}:b"),
            ],
            [
                InlineKeyboardButton("Corregir", callback_data=f"e:edit:{eid}"),
                InlineKeyboardButton("Cancelar", callback_data=f"e:no:{eid}"),
            ],
        ]
    )


async def _require_member(update: Update) -> int | None:
    user_id = _user_id(update)
    if user_id is None:
        return None
    if not await is_household_member(user_id):
        if update.message:
            await update.message.reply_text(NOT_IN_HOUSEHOLD)
        elif update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(NOT_IN_HOUSEHOLD)
        return None
    return user_id


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user_id = _user_id(update)
    if user_id is None:
        return
    settings = get_settings()
    person = await get_person_by_telegram_id(user_id)
    mention = f"@{settings.telegram_bot_username}"
    if person is not None or await is_household_member(user_id):
        name = person.name if person else settings.person_a_name
        await update.message.reply_text(
            f"Hola, {name}. Ya estás en el hogar ({mention}).\n\n{USAGE}"
        )
        return
    await update.message.reply_text(
        f"{NOT_IN_HOUSEHOLD}\n\n"
        f"Tu ID de Telegram es {user_id}.\n"
        f"/soy {settings.person_a_name} o /soy {settings.person_b_name}"
    )


async def cmd_soy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user_id = _user_id(update)
    if user_id is None:
        return
    settings = get_settings()
    args = context.args or []
    if not args:
        await update.message.reply_text(
            f"Usa /soy {settings.person_a_name} o /soy {settings.person_b_name}."
        )
        return
    await update.message.reply_text(await bind_telegram_user(user_id, " ".join(args)))


async def cmd_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(help_text())


async def cmd_gasto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user_id = await _require_member(update)
    if user_id is None:
        return
    text = " ".join(context.args or []).strip()
    if not text:
        await update.message.reply_text(USAGE)
        return
    if await _try_fix_pending(update, context, user_id, text):
        return
    await _register_text(update, user_id, text)


async def _parse_month_args(args: list[str]) -> tuple[int, int]:
    today = today_in_timezone().date()
    if not args:
        return today.year, today.month
    raw = args[0]
    try:
        year_s, month_s = raw.split("-", 1)
        return int(year_s), int(month_s)
    except ValueError:
        return today.year, today.month


async def cmd_mes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if await _require_member(update) is None:
        return
    year, month = await _parse_month_args(context.args or [])
    summary = await month_summary(year, month)
    text = format_month_text(summary)
    latest = await latest_confirmed()
    if (
        latest is not None
        and latest.spent_on is not None
        and (latest.spent_on.year, latest.spent_on.month) != (year, month)
    ):
        text += (
            f"\n\nÚltimo guardado: {latest.description} ${latest.amount_total:.2f} "
            f"el {latest.spent_on.isoformat()} (otro mes; no entra aquí)."
        )
    await update.message.reply_text(text)


async def cmd_pagos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if await _require_member(update) is None:
        return
    year, month = await _parse_month_args(context.args or [])
    summary = await month_summary(year, month)
    await update.message.reply_text(
        f"Pagos {summary.label}\n"
        f"{summary.spent_text}\n"
        f"Conjuntos: ${summary.shared:.2f}\n"
        f"Propios {summary.person_a_name}: ${summary.personal_a:.2f}\n"
        f"Propios {summary.person_b_name}: ${summary.personal_b:.2f}"
    )


async def cmd_anio(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if await _require_member(update) is None:
        return
    today = today_in_timezone().date()
    year = today.year
    if context.args:
        try:
            year = int(context.args[0])
        except ValueError:
            year = today.year
    overview = await year_overview(year)
    for chunk in format_year_messages(overview):
        await update.message.reply_text(chunk)


async def cmd_grafico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if await _require_member(update) is None:
        return
    year, month = await _parse_month_args(context.args or [])
    summary = await month_summary(year, month)
    if summary.total <= 0:
        await update.message.reply_text(f"No hay gastos confirmados en {summary.label}.")
        return
    bars, timeline = render_month_charts(summary)
    caption = summary.spent_text
    await update.message.reply_photo(
        photo=InputFile(bars, filename=f"pagos-{summary.label}.png"),
        caption=caption,
    )
    await update.message.reply_photo(
        photo=InputFile(timeline, filename=f"diario-{summary.label}.png"),
    )


async def cmd_cierre(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if await _require_member(update) is None:
        return
    year, month = await _parse_month_args(context.args or [])
    summary = await month_summary(year, month)
    await update.message.reply_text("Cierre del mes\n\n" + format_month_text(summary))


async def cmd_exportar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if await _require_member(update) is None:
        return
    year, month = await _parse_month_args(context.args or [])
    csv_text = await expenses_csv(year, month)
    from io import BytesIO

    buffer = BytesIO(csv_text.encode("utf-8-sig"))
    buffer.name = f"gastos-{year:04d}-{month:02d}.csv"
    await update.message.reply_document(document=buffer, filename=buffer.name)


async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user_id = await _require_member(update)
    if user_id is None:
        return
    person = await get_person_by_telegram_id(user_id)
    household_id = person.household_id if person is not None else None
    rows = await list_pending(household_id, limit=10)
    if not rows:
        await update.message.reply_text("No hay gastos por confirmar.")
        return
    lines = ["Por confirmar:"]
    for expense in rows:
        fecha = expense.spent_on.isoformat() if expense.spent_on else ""
        lines.append(f"• {expense.description} · ${expense.amount_total:.2f} ({fecha})")
    latest = rows[0]
    await update.message.reply_text(
        "\n".join(lines) + "\n\nPuedes confirmar el más reciente o mandar el monto si hay que corregirlo.",
        reply_markup=_confirm_keyboard(latest.id),
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    user_id = await _require_member(update)
    if user_id is None:
        return
    if update.message.photo or update.message.document:
        await _register_media(update, context, user_id)
        return
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text(USAGE)
        return
    if await _try_fix_pending(update, context, user_id, text):
        return
    await _register_text(update, user_id, text)


async def _duplicate_note(expense) -> str:
    dup = await find_duplicate(expense.household_id, expense.amount_total, expense.spent_on)
    if dup is None:
        return ""
    fecha = dup.spent_on.isoformat() if dup.spent_on else ""
    return (
        f"Ojo: ya hay un gasto confirmado de ${dup.amount_total:.2f} "
        f"el {fecha} ({dup.description}).\n\n"
    )


async def _try_fix_pending(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    text: str,
) -> bool:
    if update.message is None:
        return False
    parsed = parse_fix_message(text)
    if parsed is None:
        return False
    amount, spent_on = parsed
    person = await get_person_by_telegram_id(user_id)
    if person is None:
        return False
    target_id = context.user_data.get("fix_id")
    if target_id is None:
        latest = await latest_pending_for_person(person.id)
        if latest is None:
            return False
        target_id = latest.id
    expense = await update_pending_fields(int(target_id), amount=amount, spent_on=spent_on)
    if expense is None:
        context.user_data.pop("fix_id", None)
        return False
    context.user_data.pop("fix_id", None)
    summary = await format_expense(expense)
    note = await _duplicate_note(expense)
    await update.message.reply_text(
        f"{note}Actualizado. ¿Confirmas?\n\n{summary}",
        reply_markup=_confirm_keyboard(expense.id),
    )
    return True


async def _register_text(update: Update, user_id: int, text: str) -> None:
    if update.message is None:
        return
    parsed = parse_expense_text(text)
    if parsed is None:
        await update.message.reply_text("No encontré un monto. Prueba así:\nalmuerzo 8.50")
        return
    person = await get_person_by_telegram_id(user_id)
    if person is None:
        await update.message.reply_text(NOT_IN_HOUSEHOLD)
        return
    expense = await create_pending_expense(
        created_by=person,
        parsed=parsed,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        message_id=update.message.message_id,
    )
    summary = await format_expense(expense)
    note = await _duplicate_note(expense)
    await update.message.reply_text(
        f"{note}Registré este gasto. ¿Confirmas?\n\n{summary}",
        reply_markup=_confirm_keyboard(expense.id),
    )


async def _register_media(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    if update.message is None:
        return
    person = await get_person_by_telegram_id(user_id)
    if person is None:
        await update.message.reply_text(NOT_IN_HOUSEHOLD)
        return
    saved = await _download_media(update, context)
    if saved is None:
        await update.message.reply_text("No pude bajar el archivo. Manda una foto o un PDF.")
        return
    path, mime = saved
    caption = update.message.caption or ""
    wait = await update.message.reply_text("Leyendo el comprobante...")
    try:
        extracted = await extract_from_file(path, mime, caption)
    except ExtractionError as exc:
        await wait.edit_text(str(exc) + "\nPuedes registrarlo a mano: almuerzo 8.50")
        return
    except Exception:
        await wait.edit_text("Falló la lectura. Intenta de nuevo o mándalo por texto.")
        return

    if not extracted.has_amount:
        await wait.edit_text(
            "No pude leer el total. Escríbelo, por ejemplo:\nalmuerzo 8.50\n\n"
            f"{extracted.raw_summary}".strip()
        )
        return

    split = split_hint_from_text(caption)
    caption_date = parse_date_hint(caption)
    expense = await create_pending_from_extraction(
        created_by=person,
        extracted=extracted,
        chat_id=update.effective_chat.id if update.effective_chat else None,
        message_id=update.message.message_id,
        source_file_path=str(path),
        split_override=split,
        caption_date=caption_date,
    )
    summary = await format_expense(expense)
    warn = ""
    if extracted.low_confidence:
        warn = "No estoy muy seguro; revisa el monto.\n\n"
    if extracted.spent_on and expense.spent_on and extracted.spent_on != expense.spent_on:
        warn += (
            f"El ticket decía {extracted.spent_on.isoformat()}; "
            f"usé {expense.spent_on.isoformat()} para este mes. "
            "Si era otro día, pulsa Corregir y manda la fecha.\n\n"
        )
    note = await _duplicate_note(expense)
    await wait.edit_text(
        f"{warn}{note}Registré este comprobante. ¿Confirmas?\n\n{summary}",
        reply_markup=_confirm_keyboard(expense.id),
    )


async def _download_media(update: Update, context: ContextTypes.DEFAULT_TYPE) -> tuple[Path, str] | None:
    if update.message is None:
        return None
    INBOX_DIR.mkdir(parents=True, exist_ok=True)
    file_id = None
    mime = "image/jpeg"
    suffix = ".jpg"
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
    elif update.message.document:
        doc = update.message.document
        name = (doc.file_name or "").lower()
        mime = doc.mime_type or "application/octet-stream"
        if mime == "application/pdf" or name.endswith(".pdf"):
            mime = "application/pdf"
            suffix = ".pdf"
        elif mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp")):
            suffix = Path(name).suffix or ".jpg"
            mime = mime if mime.startswith("image/") else "image/jpeg"
        else:
            return None
        file_id = doc.file_id
    if not file_id:
        return None
    tg_file = await context.bot.get_file(file_id)
    dest = INBOX_DIR / f"{uuid.uuid4().hex}{suffix}"
    await tg_file.download_to_drive(custom_path=dest)
    return dest, mime


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.data is None:
        return
    user_id = _user_id(update)
    if user_id is None:
        return
    await query.answer()
    if not await is_household_member(user_id):
        await query.edit_message_text(NOT_IN_HOUSEHOLD)
        return

    parts = query.data.split(":")
    if len(parts) < 3 or parts[0] != "e":
        return
    action = parts[1]
    try:
        expense_id = int(parts[2])
    except ValueError:
        return

    expense = await get_expense(expense_id)
    if expense is None:
        await query.edit_message_text("No encontré ese gasto.")
        return

    if action == "ok":
        if expense.status == ExpenseStatus.confirmed:
            await query.edit_message_text("Ese gasto ya estaba confirmado.")
            return
        expense = await confirm_expense(expense_id)
        summary = await format_expense(expense) if expense else ""
        extra = ""
        today = today_in_timezone().date()
        if expense and expense.spent_on and (
            expense.spent_on.year != today.year or expense.spent_on.month != today.month
        ):
            extra = (
                f"\n\nQuedó en {expense.spent_on.isoformat()}, no en este mes. "
                "/mes no lo muestra. En el panel puedes cambiar la fecha."
            )
        await query.edit_message_text(f"Gasto guardado.\n\n{summary}{extra}")
        return

    if expense.status != ExpenseStatus.pending_confirm:
        await query.edit_message_text("Ese gasto ya no está pendiente.")
        return

    if action == "per":
        expense = await set_split(expense_id, SplitType.personal)
    elif action == "sha":
        expense = await set_split(expense_id, SplitType.shared)
    elif action == "pa" and len(parts) == 4:
        role = PersonRole.a if parts[3] == "a" else PersonRole.b
        expense = await set_paid_by(expense_id, role)
    elif action == "no":
        context.user_data.pop("fix_id", None)
        await reject_expense(expense_id)
        await query.edit_message_text("Cancelé ese registro.")
        return
    elif action == "edit":
        context.user_data["fix_id"] = expense_id
        summary = await format_expense(expense)
        await query.edit_message_text(
            "El gasto sigue pendiente.\n\n"
            f"{summary}\n\n"
            "Mándame el monto o la fecha, por ejemplo: 8.50  ·  ayer  ·  15/08"
        )
        return
    else:
        return

    summary = await format_expense(expense) if expense else ""
    await query.edit_message_text(
        f"Actualizado. ¿Confirmas?\n\n{summary}",
        reply_markup=_confirm_keyboard(expense_id),
    )
