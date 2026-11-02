"""Общие фикстуры. Синтетические документы повторяют формат учебного набора, но с другими значениями."""
from __future__ import annotations

from pathlib import Path

import pytest

from navigator.pipeline import read_folder

DOCS_DIR = Path(__file__).resolve().parent.parent / "documents"


def contract_text(number="STN-201", supplier="ООО «Тест Поставка»", amount="500 000",
                  delivery="25.03.2026", signed=True) -> str:
    lines = [
        f"ДОГОВОР ПОСТАВКИ № {number}",
        "Дата: 01.02.2026",
        "Статус: подписан обеими сторонами 01.02.2026." if signed else "Статус: стороны подпись не подтвердили.",
        "",
        f"1.1. Покупатель: ООО «СеверМет». Поставщик: {supplier}.",
    ]
    if amount is not None:
        lines.append(f"2.1. Общая стоимость поставки составляет {amount} (сумма прописью) рублей, включая НДС.")
    lines.append("2.2. Авансовый платеж составляет 100 000 рублей и входит в общую стоимость.")
    if delivery is not None:
        lines.append(f"3.1. Поставщик обязуется поставить товар не позднее {delivery}.")
    lines.append("3.2. Оплата производится не позднее 30.06.2026. Это срок оплаты, а не поставки.")
    return "\n".join(lines) + "\n"


def amendment_text(number="STN-201", amount=None, delivery=None, effective="01.03.2026",
                   status="подписано обеими сторонами 01.03.2026", n=1) -> str:
    lines = [f"ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № {n} К ДОГОВОРУ {number}", f"Статус: {status}."]
    if amount:
        lines.append(f"1. Пункт 2.1 договора изложить в следующей редакции: «Общая стоимость поставки "
                     f"составляет {amount} (прописью) рублей, включая НДС».")
    if delivery:
        lines.append(f"2. Пункт 3.1 договора изложить в следующей редакции: «Поставщик обязуется "
                     f"поставить товар не позднее {delivery}».")
    if effective:
        lines.append(f"3. Настоящее соглашение вступает в силу {effective}.")
    return "\n".join(lines) + "\n"


def as_files(*texts: str) -> list[tuple[str, bytes]]:
    return [(f"file_{i}.txt", t.encode("utf-8")) for i, t in enumerate(texts)]


@pytest.fixture
def sample_files() -> list[tuple[str, bytes]]:
    if not DOCS_DIR.exists() or len(list(DOCS_DIR.glob("*.txt"))) < 6:
        pytest.skip("Папка documents с исходными шестью файлами недоступна")
    return read_folder(DOCS_DIR)
