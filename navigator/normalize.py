"""Нормализация денежных сумм и дат."""
from __future__ import annotations

import re
from datetime import date, datetime

DATE_PATTERN = r"\d{2}\.\d{2}\.\d{4}"
# «1 200 000», «1 200 000» (неразрывный пробел) или «840000»
MONEY_PATTERN = r"\d{1,3}(?:[   ]\d{3})+|\d+"


def parse_date(raw: str) -> date | None:
    try:
        return datetime.strptime(raw.strip(), "%d.%m.%Y").date()
    except ValueError:
        return None


def parse_money(raw: str) -> int | None:
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else None


def format_money(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_date(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_value(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return format_money(value)
    if isinstance(value, date):
        return format_date(value)
    return str(value)
