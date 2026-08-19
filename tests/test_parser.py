from decimal import Decimal

from app.services.parser import parse_expense_text
from app.models import Category, SplitType


def test_almuerzo() -> None:
    parsed = parse_expense_text("almuerzo 8.50")
    assert parsed is not None
    assert parsed.amount == Decimal("8.50")
    assert parsed.category == Category.comida
    assert parsed.split_type == SplitType.shared
    assert "Almuerzo" in parsed.description


def test_personal() -> None:
    parsed = parse_expense_text("farmacia 12 personal")
    assert parsed is not None
    assert parsed.amount == Decimal("12.00")
    assert parsed.split_type == SplitType.personal
    assert parsed.category == Category.salud


def test_comma_and_uber() -> None:
    parsed = parse_expense_text("uber 4,20")
    assert parsed is not None
    assert parsed.amount == Decimal("4.20")
    assert parsed.category == Category.transporte


def test_no_amount() -> None:
    assert parse_expense_text("solo un recado") is None


def test_amount_only() -> None:
    from app.services.parser import parse_amount_only

    assert parse_amount_only("8.50") == Decimal("8.50")
    assert parse_amount_only("$12") == Decimal("12.00")
    assert parse_amount_only("4,20") == Decimal("4.20")
    assert parse_amount_only("almuerzo 8.50") is None


def test_dates() -> None:
    from datetime import date

    from app.services.parser import parse_expense_text, parse_fix_message

    today = date(2026, 8, 19)
    parsed = parse_expense_text("almuerzo 8.50 ayer", today=today)
    assert parsed is not None
    assert parsed.spent_on == date(2026, 8, 18)
    assert "Almuerzo" in parsed.description

    parsed = parse_expense_text("uber 4,20 15/08", today=today)
    assert parsed is not None
    assert parsed.spent_on == date(2026, 8, 15)
    assert parsed.category == Category.transporte

    parsed = parse_expense_text("farmacia 12 15 de agosto", today=today)
    assert parsed is not None
    assert parsed.spent_on == date(2026, 8, 15)

    assert parse_fix_message("ayer", today=today) == (None, date(2026, 8, 18))
    assert parse_fix_message("8.50 ayer", today=today) == (Decimal("8.50"), date(2026, 8, 18))
    assert parse_fix_message("15/08", today=today) == (None, date(2026, 8, 15))
    assert parse_fix_message("almuerzo 8.50 ayer", today=today) is None


def test_photo_date_defaults_to_today_if_old() -> None:
    from datetime import date

    from app.services.expenses import spent_on_for_capture

    today = date(2026, 8, 19)
    assert spent_on_for_capture(date(2024, 7, 16), today) == today
    assert spent_on_for_capture(date(2026, 8, 16), today) == date(2026, 8, 16)
    assert spent_on_for_capture(date(2026, 7, 16), today, caption_date=date(2026, 7, 16)) == date(2026, 7, 16)


if __name__ == "__main__":
    test_almuerzo()
    test_personal()
    test_comma_and_uber()
    test_no_amount()
    test_amount_only()
    test_dates()
    test_photo_date_defaults_to_today_if_old()
    print("parser ok")
