"""Проверки отдельных компонентов: загрузчик, классификатор, связыватель, извлечение."""
from __future__ import annotations

from datetime import date

import pytest

from navigator.classifier import classify
from navigator.linker import link
from navigator.loader import DocumentLoadError, load_document
from navigator.models import DocumentType, LinkStatus, SignatureStatus
from navigator.normalize import parse_date, parse_money
from navigator.pipeline import analyze


def doc_of(text: str, name: str = "x.txt"):
    return link(classify(load_document(name, text.encode("utf-8"))))


def test_loader_handles_bom_and_cp1251():
    text = "ДОГОВОР ПОСТАВКИ № AB-1\nСтрока"
    assert load_document("a.txt", b"\xef\xbb\xbf" + text.encode("utf-8")).paragraphs[0].text == "ДОГОВОР ПОСТАВКИ № AB-1"
    assert load_document("b.txt", text.encode("cp1251")).paragraphs[1].text == "Строка"


def test_loader_rejects_empty_file_without_crashing_pipeline():
    with pytest.raises(DocumentLoadError):
        load_document("empty.txt", b"  \n\n")
    result = analyze([("empty.txt", b""), ("bin.txt", bytes([0x98, 0x81, 0xff]) * 3)])
    assert sorted(name for name, _ in result.rejected_files) == ["bin.txt", "empty.txt"]
    assert result.contracts == []


def test_paragraph_ids_are_source_line_numbers():
    doc = load_document("a.txt", "A\n\nB\n".encode())
    assert [(p.paragraph_id, p.text) for p in doc.paragraphs] == [("p1", "A"), ("p3", "B")]


def test_type_detected_by_content_not_filename():
    doc = doc_of("ПИСЬМО ПОСТАВЩИКА\nТема: договор XY-5\nПредлагаем перенести срок поставки с 01.03.2026 на 05.03.2026.",
                 name="contract_signed.txt")
    assert doc.document_type is DocumentType.LETTER
    assert doc.related_contract_numbers == ["XY-5"]


def test_negated_signature_is_not_signed():
    doc = doc_of("ПРОЕКТ ДОПОЛНИТЕЛЬНОГО СОГЛАШЕНИЯ № 2 К ДОГОВОРУ XY-5\nСтатус: не подписано обеими сторонами.")
    assert doc.document_type is DocumentType.DRAFT
    assert doc.signature_status is SignatureStatus.NOT_SIGNED


def test_signature_without_both_parties_is_unknown():
    doc = doc_of("ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 1 К ДОГОВОРУ XY-5\nСтатус: подписано поставщиком.")
    assert doc.signature_status is SignatureStatus.UNKNOWN


def test_contradictory_signature_is_unknown():
    doc = doc_of("ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 1 К ДОГОВОРУ XY-5\nподписано обеими сторонами\nсоглашение не подписано")
    assert doc.signature_status is SignatureStatus.UNKNOWN


def test_ambiguous_link_is_not_linked():
    doc = doc_of("ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 1 К ДОГОВОРУ XY-5\nТакже изменяет договор XY-6.")
    assert doc.link_status is LinkStatus.AMBIGUOUS


def test_amendment_effective_date():
    doc = doc_of("ДОПОЛНИТЕЛЬНОЕ СОГЛАШЕНИЕ № 1 К ДОГОВОРУ XY-5\nНастоящее соглашение вступает в силу 01.03.2026.")
    assert doc.effective_date == date(2026, 3, 1)


def test_normalizers():
    assert parse_money("1 380 000") == 1_380_000
    assert parse_money("1 200 000") == 1_200_000
    assert parse_date("31.03.2026") == date(2026, 3, 31)
    assert parse_date("31.02.2026") is None
