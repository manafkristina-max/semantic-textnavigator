"""Contract Linker: связывание допсоглашений, проектов и писем с договорами.

Связь устанавливается только по номеру договора в тексте документа.
Имя файла не используется никогда.
"""
from __future__ import annotations

from .classifier import CONTRACT_NUMBER_RE
from .models import Document, DocumentType, LinkStatus


def find_contract_numbers(doc: Document) -> list[str]:
    numbers: list[str] = []
    for p in doc.paragraphs:
        for number in CONTRACT_NUMBER_RE.findall(p.text):
            if number not in numbers:
                numbers.append(number)
    return numbers


def link(doc: Document) -> Document:
    if doc.document_type is DocumentType.CONTRACT:
        doc.related_contract_numbers = [doc.contract_number] if doc.contract_number else []
        doc.link_status = LinkStatus.SELF
        return doc
    numbers = find_contract_numbers(doc)
    doc.related_contract_numbers = numbers
    if len(numbers) == 1:
        doc.link_status = LinkStatus.LINKED
    elif len(numbers) > 1:
        doc.link_status = LinkStatus.AMBIGUOUS
        doc.warnings.append(
            f"Документ упоминает несколько договоров ({', '.join(numbers)}) — связь не установлена, требуется проверка"
        )
    else:
        doc.link_status = LinkStatus.NOT_FOUND
        if doc.document_type is not DocumentType.UNKNOWN:
            doc.warnings.append("В тексте не найден номер договора — документ не связан ни с одним договором")
    return doc
