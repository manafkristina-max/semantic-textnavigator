"""Contract Rules Engine: действующие условия договора на дату проверки.

Юридические правила (реализованы ниже, в порядке применения):
 1. Основной договор задает первоначальные условия.
 2. Допсоглашение меняет условие, только если оно (а) подписано обеими сторонами по тексту,
    (б) имеет дату вступления в силу и (в) эта дата не позднее даты проверки.
 3. Допсоглашение меняет только те пункты, которые в нем явно изложены в новой редакции
    или явно изменены; остальные условия берутся из договора.
 4. Проект и письмо никогда не меняют условия — они показываются как несогласованные предложения.
 5. Если статус допсоглашения не удается установить, затронутые им условия получают
    «Требуется проверка», а не значение из договора или из соглашения.
 6. Несколько действующих соглашений меняют одно условие: применяется соглашение с более
    поздней датой вступления в силу (новая редакция пункта заменяет предыдущую). Если даты
    совпадают, а значения разные — «Требуется проверка».
 7. Имя файла и порядок загрузки на результат не влияют.
"""
from __future__ import annotations

from datetime import date
from enum import Enum

from .extractors import FIELD_SPECS, extract_changes, extract_contract_terms, find_hint
from .models import (
    ContractTerm,
    ContractView,
    Document,
    DocumentType,
    FieldResult,
    PendingProposal,
    SignatureStatus,
    ValueStatus,
)
from .normalize import format_date, format_value


class ChangeState(Enum):
    APPLIED = "действующее допсоглашение"
    NOT_IN_FORCE = "допсоглашение, не вступившее в силу на дату проверки"
    PENDING = "несогласованное предложение"
    UNRESOLVED = "документ с неподтвержденным статусом"


def change_state(doc: Document, check_date: date) -> tuple[ChangeState, str]:
    if doc.document_type is DocumentType.LETTER:
        return ChangeState.PENDING, "письмо содержит предложение и не изменяет договор"
    if doc.document_type is DocumentType.DRAFT:
        return ChangeState.PENDING, "проект изменения не является подписанным соглашением"
    # Далее — дополнительное соглашение.
    if doc.signature_status is SignatureStatus.NOT_SIGNED:
        return ChangeState.PENDING, "соглашение не подписано"
    if doc.signature_status is not SignatureStatus.SIGNED_BY_BOTH:
        return ChangeState.UNRESOLVED, "не удалось установить подписание обеими сторонами"
    if doc.effective_date is None:
        return ChangeState.UNRESOLVED, "не указана дата вступления в силу"
    if doc.effective_date > check_date:
        return ChangeState.NOT_IN_FORCE, f"вступает в силу {format_date(doc.effective_date)}, позже даты проверки"
    return ChangeState.APPLIED, f"подписано обеими сторонами, в силе с {format_date(doc.effective_date)}"


def _sort_key(doc: Document):
    return (doc.effective_date or date.min, doc.doc_id)


def build_contract_view(
    contract: Document,
    linked: list[Document],
    check_date: date,
    duplicate_number: bool = False,
) -> ContractView:
    warnings: list[str] = list(contract.warnings)
    base_terms = extract_contract_terms(contract)

    applied: list[tuple[Document, list[ContractTerm]]] = []
    unresolved: list[tuple[Document, list[ContractTerm]]] = []
    not_in_force: list[Document] = []
    pending: list[PendingProposal] = []

    for doc in sorted(linked, key=_sort_key):
        state, reason = change_state(doc, check_date)
        role = f"{doc.label} — {state.value}"
        changes = extract_changes(doc, role)
        if state is ChangeState.APPLIED:
            applied.append((doc, changes))
            if not changes:
                warnings.append(f"{doc.label} ({doc.filename}): не найдено изменений поддерживаемых условий")
        elif state is ChangeState.UNRESOLVED:
            unresolved.append((doc, changes))
            warnings.append(f"{doc.label} ({doc.filename}): {reason} — затронутые условия требуют проверки")
        elif state is ChangeState.NOT_IN_FORCE:
            not_in_force.append(doc)
            warnings.append(f"{doc.label} ({doc.filename}): {reason}; текущие условия не меняет")
        else:
            for term in changes:
                pending.append(
                    PendingProposal(
                        field_name=term.field_name,
                        display=format_value(term.normalized_value),
                        source_label=doc.label,
                        reason=reason,
                        evidence=term.evidence,
                    )
                )

    contract_signed = contract.signature_status is SignatureStatus.SIGNED_BY_BOTH
    if not contract_signed:
        warnings.append("Подписание договора обеими сторонами не подтверждено текстом — требуется проверка")
    if duplicate_number:
        warnings.append(f"Загружено несколько договоров с номером {contract.contract_number} — требуется проверка")

    fields: dict[str, FieldResult] = {}
    for spec in FIELD_SPECS:
        result = FieldResult(field_name=spec.name, label=spec.label, status=ValueStatus.MISSING, display="Нет данных")
        base = base_terms[spec.name]
        distinct_base = {t.normalized_value for t in base}
        if len(distinct_base) == 1:
            result.initial_display = format_value(base[0].normalized_value)
            result.initial_evidence = base[0].evidence
        elif len(distinct_base) > 1:
            result.notes.append(
                "В договоре несколько разных значений: " + ", ".join(sorted(format_value(v) for v in distinct_base))
            )

        field_changes = [(doc, t) for doc, terms in applied for t in terms if t.field_name == spec.name]
        touched_unresolved = [doc for doc, terms in unresolved if any(t.field_name == spec.name for t in terms)]

        if not contract_signed or duplicate_number:
            _set_review(result, "Статус договора не подтвержден")
        elif touched_unresolved:
            _set_review(result, "Условие затронуто документом с неподтвержденным статусом: "
                        + ", ".join(d.filename for d in touched_unresolved))
        elif field_changes:
            latest_date = max(doc.effective_date for doc, _ in field_changes)
            latest = [(doc, t) for doc, t in field_changes if doc.effective_date == latest_date]
            if len({t.normalized_value for _, t in latest}) > 1:
                _set_review(result, "Действующие соглашения с одной датой вступления в силу противоречат друг другу: "
                            + ", ".join(f"{format_value(t.normalized_value)} ({d.filename})" for d, t in latest))
            else:
                doc, term = latest[0]
                result.status = ValueStatus.CONFIRMED
                result.value = term.normalized_value
                result.display = format_value(term.normalized_value)
                result.evidence = term.evidence
                result.changed_by = doc.label
                if len(field_changes) > len(latest):
                    result.notes.append("Условие менялось несколькими соглашениями; применена редакция с более поздней датой вступления в силу")
        elif len(distinct_base) > 1:
            _set_review(result, "Неоднозначное значение в договоре")
        elif base:
            result.status = ValueStatus.CONFIRMED
            result.value = base[0].normalized_value
            result.display = format_value(base[0].normalized_value)
            result.evidence = base[0].evidence
        else:
            hint = find_hint(contract, spec)
            if hint:
                result.notes.append(f"Числовое/явное значение не найдено. В договоре ({hint.paragraph_id}): «{hint.text}»")
            else:
                result.notes.append("Условие в тексте договора не найдено")
        fields[spec.name] = result

    statuses = {f.status for f in fields.values()}
    if ValueStatus.REVIEW in statuses:
        status = ValueStatus.REVIEW
    elif ValueStatus.MISSING in statuses:
        status = ValueStatus.MISSING
    else:
        status = ValueStatus.CONFIRMED

    return ContractView(
        contract_number=contract.contract_number or "б/н",
        document=contract,
        fields=fields,
        status=status,
        applied_amendments=[doc for doc, _ in applied],
        not_in_force=not_in_force,
        pending=pending,
        related_documents=sorted(linked, key=_sort_key),
        warnings=warnings,
    )


def _set_review(result: FieldResult, note: str) -> None:
    result.status = ValueStatus.REVIEW
    result.value = None
    result.display = "Требуется проверка"
    result.notes.append(note)
