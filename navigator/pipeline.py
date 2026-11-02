"""Оркестрация: загрузка → классификация → связывание → правила."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Iterable

from .classifier import classify
from .linker import link
from .loader import DocumentLoadError, load_document
from .models import AnalysisResult, DocumentType, LinkStatus
from .rules import build_contract_view

DEFAULT_CHECK_DATE = date(2026, 3, 10)


def analyze(files: Iterable[tuple[str, bytes]], check_date: date = DEFAULT_CHECK_DATE) -> AnalysisResult:
    documents, rejected, warnings = [], [], []
    seen_ids: set[str] = set()
    for filename, data in files:
        try:
            doc = load_document(filename, data)
        except DocumentLoadError as error:
            rejected.append((filename, str(error)))
            continue
        if doc.doc_id in seen_ids:
            warnings.append(f"{filename}: содержимое совпадает с уже загруженным файлом — дубликат пропущен")
            continue
        seen_ids.add(doc.doc_id)
        documents.append(link(classify(doc)))

    # Детерминированный порядок, не зависящий от порядка загрузки и имен файлов.
    documents.sort(key=lambda d: d.doc_id)

    contracts_by_number = defaultdict(list)
    for doc in documents:
        if doc.document_type is DocumentType.CONTRACT and doc.contract_number:
            contracts_by_number[doc.contract_number].append(doc)

    linked_by_number = defaultdict(list)
    for doc in documents:
        if doc.document_type is DocumentType.CONTRACT:
            continue
        if doc.link_status is LinkStatus.LINKED:
            number = doc.related_contract_numbers[0]
            if number in contracts_by_number:
                linked_by_number[number].append(doc)
            else:
                warnings.append(f"{doc.filename}: ссылается на договор {number}, которого нет среди загруженных документов")
        elif doc.document_type is not DocumentType.UNKNOWN:
            warnings.append(f"{doc.filename}: не связан с договором ({doc.link_status.value})")

    for doc in documents:
        if doc.document_type is DocumentType.UNKNOWN:
            warnings.append(f"{doc.filename}: тип документа не распознан, документ не используется")
        if doc.document_type is DocumentType.CONTRACT and not doc.contract_number:
            warnings.append(f"{doc.filename}: договор без номера — не включен в таблицу")

    contracts = []
    for number in sorted(contracts_by_number):
        group = contracts_by_number[number]
        for contract in group:
            contracts.append(
                build_contract_view(contract, linked_by_number[number], check_date, duplicate_number=len(group) > 1)
            )

    return AnalysisResult(check_date, documents, contracts, rejected, warnings)


def read_folder(folder: Path) -> list[tuple[str, bytes]]:
    return [(path.name, path.read_bytes()) for path in sorted(folder.glob("*.txt"))]
