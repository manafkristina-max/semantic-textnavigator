"""Terms Extractor: извлечение условий с дословными цитатами.

Каждое поле описывается одной записью FieldSpec в реестре FIELD_SPECS.
Чтобы добавить новое поле (например, ставку неустойки), достаточно добавить FieldSpec —
движок правил, вопросы и интерфейс подхватят его автоматически (см. EXTENSION_GUIDE.md).

Принцип: значение извлекается только из формулировки, которая явно относится к нужному
условию. Аванс, лимит бюджета, срок оплаты и дата приемки этим формулировкам не соответствуют.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from .models import ContractTerm, Document, Evidence, Paragraph
from .normalize import DATE_PATTERN, MONEY_PATTERN, parse_date, parse_money

FIELD_SUPPLIER = "supplier"
FIELD_AMOUNT = "amount"
FIELD_DELIVERY = "delivery_date"


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    # Формулировки условия в тексте договора (и в новой редакции пункта в допсоглашении).
    clause_patterns: tuple[re.Pattern, ...]
    normalize: Callable[[str], object]
    # Формулировки изменения: «изменить … на …», «перенести … на …».
    change_patterns: tuple[re.Pattern, ...] = ()
    # Если значение не извлечено, но условие упоминается — показываем цитату как пояснение.
    hint_pattern: re.Pattern | None = None


def _re(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


FIELD_SPECS: list[FieldSpec] = [
    FieldSpec(
        name=FIELD_SUPPLIER,
        label="Поставщик",
        clause_patterns=(_re(r"Поставщик:\s*(?P<value>.+?)\s*\.?\s*$"),),
        normalize=lambda raw: raw.strip(),
        hint_pattern=_re(r"поставщик"),
    ),
    FieldSpec(
        name=FIELD_AMOUNT,
        label="Сумма договора, ₽",
        clause_patterns=(
            # «Общая стоимость поставки составляет 1 200 000 (…) рублей»
            _re(rf"Общая\s+стоимость[^.]*?составляет\s+(?P<value>{MONEY_PATTERN})\s*(?:\([^)]*\)\s*)?руб"),
        ),
        change_patterns=(
            _re(rf"изменить\s+(?:общую\s+)?стоимость(?:\s+поставки)?\s+на\s+(?P<value>{MONEY_PATTERN})\s*руб"),
        ),
        normalize=parse_money,
        hint_pattern=_re(r"общая\s+стоимость"),
    ),
    FieldSpec(
        name=FIELD_DELIVERY,
        label="Срок поставки",
        clause_patterns=(
            # «Поставщик обязуется поставить … не позднее 15.04.2026»
            _re(rf"поставить[^.]*?не\s+позднее\s+(?P<value>{DATE_PATTERN})"),
            _re(rf"срок\s+поставки[^.]*?не\s+позднее\s+(?P<value>{DATE_PATTERN})"),
        ),
        change_patterns=(
            _re(rf"(?:изменить|перенести)\s+срок\s+поставки\s+(?:с\s+{DATE_PATTERN}\s+)?на\s+(?P<value>{DATE_PATTERN})"),
        ),
        normalize=parse_date,
        hint_pattern=_re(r"срок\s+поставки|поставить"),
    ),
]

SPECS_BY_NAME = {spec.name: spec for spec in FIELD_SPECS}

# «Пункт 2.1 договора изложить в следующей редакции: «…»»
NEW_REDACTION_RE = re.compile(r"изложить\s+в\s+(?:следующей|новой)\s+редакции", re.I)
QUOTED_RE = re.compile(r"«(.+)»")


def _make_term(spec: FieldSpec, doc: Document, paragraph: Paragraph, match: re.Match, role: str) -> ContractTerm | None:
    raw = match.group("value")
    normalized = spec.normalize(raw)
    if normalized in (None, ""):
        return None
    evidence = Evidence(
        document_id=doc.doc_id,
        filename=doc.filename,
        paragraph_id=paragraph.paragraph_id,
        exact_quote=paragraph.text,
        extracted_fragment=raw,
        source_role=role,
    )
    return ContractTerm(spec.name, raw, normalized, evidence, doc.document_type)


def _search_all(patterns, text):
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            return match
    return None


def extract_contract_terms(doc: Document, role: str = "основной договор") -> dict[str, list[ContractTerm]]:
    """Условия основного договора: все совпадения по каждому полю (несколько — повод для проверки)."""
    result: dict[str, list[ContractTerm]] = {spec.name: [] for spec in FIELD_SPECS}
    for paragraph in doc.paragraphs:
        for spec in FIELD_SPECS:
            match = _search_all(spec.clause_patterns, paragraph.text)
            if match:
                term = _make_term(spec, doc, paragraph, match, role)
                if term:
                    result[spec.name].append(term)
    return result


def extract_changes(doc: Document, role: str) -> list[ContractTerm]:
    """Изменения, которые документ вносит (или предлагает внести) в условия договора.

    Учитываются только явные формулировки:
      * новая редакция пункта в кавычках «…» — к ней применяются те же правила, что к договору;
      * «изменить/перенести … на …».
    Фраза «остальные условия остаются без изменений» ничего не меняет.
    """
    changes: list[ContractTerm] = []
    for paragraph in doc.paragraphs:
        quoted = QUOTED_RE.search(paragraph.text) if NEW_REDACTION_RE.search(paragraph.text) else None
        for spec in FIELD_SPECS:
            match = _search_all(spec.clause_patterns, quoted.group(1)) if quoted else None
            if not match:
                match = _search_all(spec.change_patterns, paragraph.text)
            if match:
                term = _make_term(spec, doc, paragraph, match, role)
                if term:
                    changes.append(term)
    return changes


def find_hint(doc: Document, spec: FieldSpec) -> Paragraph | None:
    if spec.hint_pattern is None:
        return None
    return next((p for p in doc.paragraphs[1:] if spec.hint_pattern.search(p.text)), None)
