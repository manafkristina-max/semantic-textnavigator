"""Готовые вопросы пользователя. Ответы вычисляются только из AnalysisResult — без заготовленных значений."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Callable

from .extractors import FIELD_AMOUNT, FIELD_DELIVERY
from .models import AnalysisResult, ContractView, Evidence, FieldResult, ValueStatus
from .normalize import format_date


@dataclass
class Answer:
    summary: str
    details: list[str] = field(default_factory=list)
    sources: list[Evidence] = field(default_factory=list)


def _basis(result: FieldResult) -> str:
    return f"основание: {result.changed_by}" if result.changed_by else "основание: основной договор"


def _pending_lines(view: ContractView, field_name: str) -> list[str]:
    return [
        f"Несогласованное предложение: {p.display} — {p.source_label}, «{p.evidence.filename}» ({p.reason}); не применяется."
        for p in view.pending_for(field_name)
    ]


def _field_answer(analysis: AnalysisResult, number: str, field_name: str, what: str, unit: str = "") -> Answer:
    view = analysis.contract(number)
    if view is None:
        return Answer(f"Договор {number} не найден среди загруженных документов.")
    result = view.field(field_name)
    on_date = format_date(analysis.check_date)
    if result.status is ValueStatus.CONFIRMED:
        summary = f"{what} по договору {number} на {on_date}: **{result.display}{unit}** ({_basis(result)})."
    elif result.status is ValueStatus.MISSING:
        summary = f"{what} по договору {number}: **Нет данных** — значение не найдено в загруженных документах."
    else:
        summary = f"{what} по договору {number}: **Требуется проверка** — значение нельзя установить достоверно."
    details = list(result.notes)
    if result.is_changed and result.initial_display:
        details.append(f"Первоначальное значение по договору: {result.initial_display}{unit}.")
    details += _pending_lines(view, field_name)
    sources = [e for e in (result.evidence, result.initial_evidence) if e]
    return Answer(summary, details, sources)


def delivery_date_for(analysis: AnalysisResult, number: str) -> Answer:
    return _field_answer(analysis, number, FIELD_DELIVERY, "Срок поставки")


def amount_for(analysis: AnalysisResult, number: str) -> Answer:
    return _field_answer(analysis, number, FIELD_AMOUNT, "Сумма", " ₽")


def deliveries_before(analysis: AnalysisResult, cutoff: date) -> Answer:
    """Строго «раньше»: дата, равная cutoff, не подходит."""
    earlier, later, unknown, pending = [], [], [], []
    sources: list[Evidence] = []
    for view in analysis.contracts:
        result = view.field(FIELD_DELIVERY)
        if result.status is ValueStatus.CONFIRMED:
            line = f"{view.contract_number}: {result.display} ({_basis(result)})"
            if result.value < cutoff:
                earlier.append(line)
                sources.append(result.evidence)
            else:
                later.append(line)
        else:
            unknown.append(f"{view.contract_number}: {result.status.value} — сравнение невозможно")
        for p in view.pending_for(FIELD_DELIVERY):
            pending.append(f"{view.contract_number}: предложено {p.display} — {p.source_label} ({p.reason})")
            sources.append(p.evidence)

    cutoff_text = format_date(cutoff)
    summary = (
        f"Поставка раньше {cutoff_text} (действующие условия на {format_date(analysis.check_date)}): "
        + (", ".join(f"**{line}**" for line in earlier) if earlier else "**таких договоров нет**")
        + "."
    )
    details = []
    if later:
        details.append(f"Не раньше {cutoff_text}: " + "; ".join(later) + ".")
    if unknown:
        details.append("Без подтвержденного срока: " + "; ".join(unknown) + ".")
    details.append(
        "Несогласованные изменения срока (не применяются): " + ("; ".join(pending) if pending else "нет") + "."
    )
    return Answer(summary, details, sources)


@dataclass(frozen=True)
class Question:
    text: str
    run: Callable[[AnalysisResult], Answer]


QUESTIONS: list[Question] = [
    Question(
        "Какой срок поставки действует по договору STN-101 на 10 марта 2026 года?",
        lambda a: delivery_date_for(a, "STN-101"),
    ),
    Question("Какова сумма договора STN-102?", lambda a: amount_for(a, "STN-102")),
    Question("Какова сумма договора STN-103?", lambda a: amount_for(a, "STN-103")),
    Question(
        "По каким договорам поставка запланирована раньше 1 апреля 2026 года и есть ли несогласованные изменения срока?",
        lambda a: deliveries_before(a, date(2026, 4, 1)),
    ),
]
