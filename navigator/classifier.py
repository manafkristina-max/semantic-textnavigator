"""Document Classifier: тип документа, признак подписания, дата вступления в силу.

Тип определяется по заголовку (первому абзацу), а не по имени файла.
Признак подписания — это распознанная формулировка в тексте; подлинность подписи
по TXT проверить нельзя, поэтому статус всегда помечается как «по тексту».
"""
from __future__ import annotations

import re

from .models import Document, DocumentType, SignatureStatus
from .normalize import DATE_PATTERN, parse_date

# Порядок важен: «ПРОЕКТ ДОПОЛНИТЕЛЬНОГО СОГЛАШЕНИЯ» проверяется раньше «ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ».
TITLE_RULES: list[tuple[re.Pattern, DocumentType]] = [
    (re.compile(r"^\s*ПРОЕКТ\b", re.I), DocumentType.DRAFT),
    (re.compile(r"^\s*ДОПОЛНИТЕЛЬНОЕ\s+СОГЛАШЕНИЕ\b", re.I), DocumentType.AMENDMENT),
    (re.compile(r"^\s*ДОГОВОР\b", re.I), DocumentType.CONTRACT),
    (re.compile(r"^\s*ПИСЬМО\b", re.I), DocumentType.LETTER),
]

# «подписан(о) обеими сторонами», но не «не подписан(о) обеими сторонами»
SIGNED_BOTH_RE = re.compile(r"(?<!не\s)\bподписан[оа]?\s+обеими\s+сторонами", re.I)
NOT_SIGNED_RE = re.compile(r"\bне\s+подписан[оаы]?\b|\bподписание\s+не\s+состоялось", re.I)
EFFECTIVE_RE = re.compile(rf"вступает\s+в\s+силу\s+(?:с\s+)?({DATE_PATTERN})", re.I)
CONTRACT_NUMBER_RE = re.compile(r"\b[A-ZА-ЯЁ]{2,}-\d+\b")
OWN_NUMBER_RE = re.compile(r"№\s*([A-ZА-ЯЁ]{2,}-\d+)")
AMENDMENT_NUMBER_RE = re.compile(r"№\s*(\d+)")


def detect_type(doc: Document) -> DocumentType:
    for pattern, doc_type in TITLE_RULES:
        if pattern.search(doc.title):
            doc.classification_evidence.append(f"Тип по заголовку (p1): «{doc.title}»")
            return doc_type
    doc.classification_evidence.append("Заголовок не соответствует известным типам документов")
    return DocumentType.UNKNOWN


def detect_signature(doc: Document) -> SignatureStatus:
    signed = [p for p in doc.paragraphs if SIGNED_BOTH_RE.search(p.text)]
    not_signed = [p for p in doc.paragraphs if NOT_SIGNED_RE.search(p.text)]
    for p in signed:
        doc.classification_evidence.append(f"Признак подписания обеими сторонами ({p.paragraph_id}): «{p.text}»")
    for p in not_signed:
        doc.classification_evidence.append(f"Признак отсутствия подписи ({p.paragraph_id}): «{p.text}»")
    if signed and not_signed:
        # Противоречивые формулировки: решение не принимаем.
        doc.warnings.append("Противоречивые признаки подписания — требуется ручная проверка")
        return SignatureStatus.UNKNOWN
    if signed:
        return SignatureStatus.SIGNED_BY_BOTH
    if not_signed:
        return SignatureStatus.NOT_SIGNED
    return SignatureStatus.UNKNOWN


def detect_effective_date(doc: Document):
    for p in doc.paragraphs:
        match = EFFECTIVE_RE.search(p.text)
        if match:
            doc.classification_evidence.append(f"Дата вступления в силу ({p.paragraph_id}): «{p.text}»")
            return parse_date(match.group(1))
    return None


def classify(doc: Document) -> Document:
    doc.document_type = detect_type(doc)
    doc.signature_status = detect_signature(doc)
    if doc.document_type is DocumentType.CONTRACT:
        match = OWN_NUMBER_RE.search(doc.title)
        doc.contract_number = match.group(1) if match else None
        if not doc.contract_number:
            doc.warnings.append("В заголовке договора не найден номер — договор не может быть сопоставлен")
    if doc.document_type in (DocumentType.AMENDMENT, DocumentType.DRAFT):
        match = AMENDMENT_NUMBER_RE.search(doc.title)
        doc.amendment_number = match.group(1) if match else None
        doc.effective_date = detect_effective_date(doc)
    if doc.document_type is DocumentType.UNKNOWN:
        doc.warnings.append("Тип документа не распознан — документ не используется в расчете условий")
    return doc
