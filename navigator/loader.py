"""Document Loader: декодирование TXT, разбиение на абзацы, внутренние идентификаторы."""
from __future__ import annotations

import hashlib

from .models import Document, Paragraph

ENCODINGS = ("utf-8-sig", "cp1251")  # utf-8-sig читает и UTF-8, и UTF-8 с BOM


class DocumentLoadError(ValueError):
    pass


def decode_text(data: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentLoadError("не удалось определить кодировку (поддерживаются UTF-8 и Windows-1251)")


def split_paragraphs(text: str) -> list[Paragraph]:
    """Абзац = непустая строка. Идентификатор — номер строки, чтобы его можно было найти в файле."""
    paragraphs = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if stripped:
            paragraphs.append(Paragraph(paragraph_id=f"p{line_no}", line_no=line_no, text=stripped))
    return paragraphs


def load_document(filename: str, data: bytes) -> Document:
    text = decode_text(data)
    paragraphs = split_paragraphs(text)
    if not paragraphs:
        raise DocumentLoadError("файл пуст")
    # Идентификатор зависит только от содержимого: порядок загрузки и имя файла на него не влияют.
    doc_id = "doc-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]
    return Document(doc_id=doc_id, filename=filename, original_text=text, paragraphs=paragraphs)
