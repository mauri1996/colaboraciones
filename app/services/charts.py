"""Gráficos del mes para Telegram (PNG)."""

from __future__ import annotations

from calendar import monthrange
from decimal import Decimal
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from app.config import get_settings
from app.services.reports import MonthSummary

_BG = "#F5F2FA"
_CARD = "#FFFCFF"
_INK = "#3D3554"
_MUTED = "#7A7390"
_GRID = "#DDD6EB"
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


def render_month_charts(summary: MonthSummary) -> tuple[bytes, bytes]:
    color_a, color_b = get_settings().chart_colors
    title = f"{_MONTH_NAMES[summary.month]} {summary.year}"
    daily = _daily_series(summary)
    bars = _bars_by_person(title, summary, color_a, color_b)
    timeline = _daily_timeline(title, summary, daily, color_a, color_b)
    return bars, timeline


def month_chart_payload(summary: MonthSummary) -> dict:
    color_a, color_b = get_settings().chart_colors
    days, daily_a, daily_b = _daily_series(summary)
    by_day: dict[str, list[dict]] = {str(day): [] for day in days}
    for expense in summary.expenses:
        if expense.spent_on is None:
            continue
        who = summary.person_b_name if (
            summary.person_b_id and expense.paid_by_person_id == summary.person_b_id
        ) else summary.person_a_name
        key = str(expense.spent_on.day)
        if key in by_day:
            by_day[key].append(
                {
                    "who": who,
                    "description": expense.description or "Gasto",
                    "amount": float(expense.amount_total),
                }
            )
    return {
        "title": f"{_MONTH_NAMES[summary.month]} {summary.year}",
        "person_a": summary.person_a_name,
        "person_b": summary.person_b_name,
        "paid_a": float(summary.paid_a),
        "paid_b": float(summary.paid_b),
        "days": days,
        "daily_a": daily_a,
        "daily_b": daily_b,
        "by_day": by_day,
        "color_a": color_a,
        "color_b": color_b,
    }


def _money(value: float) -> str:
    return f"${value:,.2f}"


def _daily_series(summary: MonthSummary) -> tuple[list[int], list[float], list[float]]:
    last = monthrange(summary.year, summary.month)[1]
    days = list(range(1, last + 1))
    paid_a = [0.0] * last
    paid_b = [0.0] * last
    for expense in summary.expenses:
        if expense.spent_on is None:
            continue
        idx = expense.spent_on.day - 1
        if idx < 0 or idx >= last:
            continue
        amount = float(Decimal(expense.amount_total))
        if summary.person_b_id and expense.paid_by_person_id == summary.person_b_id:
            paid_b[idx] += amount
        else:
            paid_a[idx] += amount
    return days, paid_a, paid_b


def _style(fig, ax) -> None:
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_CARD)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(_GRID)
    ax.spines["bottom"].set_color(_GRID)
    ax.tick_params(colors=_MUTED, labelsize=9)
    ax.yaxis.grid(True, linestyle=":", color=_GRID, alpha=0.9)
    ax.set_axisbelow(True)


def _bars_by_person(title: str, summary: MonthSummary, color_a: str, color_b: str) -> bytes:
    fig, ax = plt.subplots(figsize=(8.4, 5.2), dpi=160)
    _style(fig, ax)
    names = [summary.person_a_name, summary.person_b_name]
    values = [float(summary.paid_a), float(summary.paid_b)]
    colors = [color_a, color_b]
    bars = ax.bar(names, values, color=colors, width=0.52, zorder=3)
    peak = max(values) if values else 0.0
    ax.set_ylim(0, peak * 1.22 if peak > 0 else 1)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=4))
    ax.set_ylabel("USD", color=_MUTED)
    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            _money(value),
            ha="center",
            va="bottom",
            fontsize=12,
            color=_INK,
            fontweight="bold",
        )
    ax.set_title(f"Gasto del mes por persona · {title}", color=_INK, loc="left", fontsize=13, pad=12)
    fig.tight_layout()
    return _to_png(fig)


def _daily_timeline(
    title: str,
    summary: MonthSummary,
    series: tuple[list[int], list[float], list[float]],
    color_a: str,
    color_b: str,
) -> bytes:
    days, paid_a, paid_b = series
    fig, ax = plt.subplots(figsize=(9.4, 5.4), dpi=160)
    _style(fig, ax)
    ax.plot(days, paid_a, color=color_a, linewidth=2.2, marker="o", markersize=5, label=summary.person_a_name)
    ax.plot(days, paid_b, color=color_b, linewidth=2.2, marker="o", markersize=5, label=summary.person_b_name)
    ax.fill_between(days, paid_a, color=color_a, alpha=0.12)
    ax.fill_between(days, paid_b, color=color_b, alpha=0.12)
    _label_points(ax, days, paid_a, paid_b, color_a, color_b)
    ax.set_xlim(0.5, (days[-1] if days else 31) + 0.5)
    ymax = max([*paid_a, *paid_b, 0.0])
    ax.set_ylim(0, ymax * 1.28 if ymax > 0 else 1)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True, nbins=10))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=4))
    ax.set_xlabel("Día del mes", color=_MUTED)
    ax.set_ylabel("USD", color=_MUTED)
    ax.legend(frameon=False, loc="upper right", labelcolor=_INK, fontsize=9)
    ax.set_title(f"Gastos por día · {title}", color=_INK, loc="left", fontsize=13, pad=12)
    fig.tight_layout()
    return _to_png(fig)


def _label_points(
    ax,
    days: list[int],
    paid_a: list[float],
    paid_b: list[float],
    color_a: str,
    color_b: str,
) -> None:
    for day, value_a, value_b in zip(days, paid_a, paid_b):
        both = value_a > 0 and value_b > 0
        if value_a > 0:
            ax.annotate(
                _money(value_a),
                (day, value_a),
                textcoords="offset points",
                xytext=(-10 if both else 0, 8),
                ha="center",
                fontsize=7.5,
                color=color_a,
            )
        if value_b > 0:
            ax.annotate(
                _money(value_b),
                (day, value_b),
                textcoords="offset points",
                xytext=(10 if both else 0, 8),
                ha="center",
                fontsize=7.5,
                color=color_b,
            )


def _to_png(fig) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return buffer.getvalue()
