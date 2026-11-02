"""Модель данных.

Ключевой принцип: отсутствие значения, неоднозначность и неутвержденное предложение —
это разные состояния. Ни одно из них не сводится к голому None.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class DocumentType(Enum):
    CONTRACT = "Договор"
    AMENDMENT = "Дополнительное соглашение"
    LETTER = "Письмо"
    DRAFT = "Проект изменения"
    UNKNOWN = "Тип не распознан"


class SignatureStatus(Enum):
    # Это распознанный текстовый признак, а не юридическая верификация подписи.
    SIGNED_BY_BOTH = "Подписан обеими сторонами (по тексту)"
    NOT_SIGNED = "Не подписан"
    UNKNOWN = "Не определен — требуется проверка"


class ValueStatus(Enum):
    CONFIRMED = "Подтверждено"
    MISSING = "Нет данных"
    REVIEW = "Требуется проверка"


class LinkStatus(Enum):
    LINKED = "Связан"
    AMBIGUOUS = "Неоднозначная связь"
    NOT_FOUND = "Номер договора не найден"
    SELF = "Сам является договором"


@dataclass(frozen=True)
class Paragraph:
    paragraph_id: str  # "p6" — абзац на 6-й строке исходного файла
    line_no: int
    text: str


@dataclass
class Document:
    doc_id: str
    filename: str
    original_text: str
    paragraphs: list[Paragraph]
    document_type: DocumentType = DocumentType.UNKNOWN
    signature_status: SignatureStatus = SignatureStatus.UNKNOWN
    effective_date: date | None = None
    contract_number: str | None = None  # собственный номер (для договора)
    amendment_number: str | None = None
    related_contract_numbers: list[str] = field(default_factory=list)
    link_status: LinkStatus = LinkStatus.NOT_FOUND
    classification_evidence: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def paragraph(self, paragraph_id: str) -> Paragraph | None:
        return next((p for p in self.paragraphs if p.paragraph_id == paragraph_id), None)

    @property
    def title(self) -> str:
        return self.paragraphs[0].text if self.paragraphs else ""

    @property
    def label(self) -> str:
        """Человекочитаемое название документа — из содержимого, не из имени файла."""
        if self.document_type is DocumentType.CONTRACT:
            return f"Договор № {self.contract_number or 'б/н'}"
        num = f" № {self.amendment_number}" if self.amendment_number else ""
        if self.document_type is DocumentType.AMENDMENT:
            when = f" (в силе с {self.effective_date:%d.%m.%Y})" if self.effective_date else ""
            return f"Доп. соглашение{num}{when}"
        if self.document_type is DocumentType.DRAFT:
            return f"Проект доп. соглашения{num}"
        if self.document_type is DocumentType.LETTER:
            return "Письмо"
        return "Документ неизвестного типа"


@dataclass(frozen=True)
class Evidence:
    document_id: str
    filename: str
    paragraph_id: str
    exact_quote: str  # дословный текст абзаца из загруженного файла
    extracted_fragment: str  # подстрока цитаты, из которой взято значение
    source_role: str  # «основной договор», «действующее допсоглашение», «проект» …


@dataclass(frozen=True)
class ContractTerm:
    """Значение условия, найденное в одном документе."""

    field_name: str
    raw_value: str
    normalized_value: object
    evidence: Evidence
    source_document_type: DocumentType


@dataclass(frozen=True)
class PendingProposal:
    """Изменение, которое предложено, но не действует на дату проверки."""

    field_name: str
    display: str
    source_label: str
    reason: str
    evidence: Evidence


@dataclass
class FieldResult:
    field_name: str
    label: str
    status: ValueStatus
    value: object = None
    display: str = ""
    evidence: Evidence | None = None  # источник действующего значения
    changed_by: str | None = None  # какое допсоглашение изменило условие
    initial_display: str | None = None  # первоначальное значение из договора
    initial_evidence: Evidence | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def is_changed(self) -> bool:
        return self.changed_by is not None


@dataclass
class ContractView:
    contract_number: str
    document: Document
    fields: dict[str, FieldResult]
    status: ValueStatus
    applied_amendments: list[Document] = field(default_factory=list)
    not_in_force: list[Document] = field(default_factory=list)
    pending: list[PendingProposal] = field(default_factory=list)
    related_documents: list[Document] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def field(self, name: str) -> FieldResult:
        return self.fields[name]

    def pending_for(self, field_name: str) -> list[PendingProposal]:
        return [p for p in self.pending if p.field_name == field_name]


@dataclass
class AnalysisResult:
    check_date: date
    documents: list[Document]
    contracts: list[ContractView]
    rejected_files: list[tuple[str, str]]  # (имя файла, причина)
    warnings: list[str]

    def contract(self, number: str) -> ContractView | None:
        return next((c for c in self.contracts if c.contract_number == number), None)

    def document(self, doc_id: str) -> Document | None:
        return next((d for d in self.documents if d.doc_id == doc_id), None)
