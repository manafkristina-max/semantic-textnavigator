"""Evidence Navigator: проверка цитат и подсветка фрагмента в абзаце."""
from __future__ import annotations

import html

from .models import Document, Evidence


def verify_evidence(doc: Document, evidence: Evidence) -> bool:
    """Цитата обязана дословно существовать в загруженном тексте, а фрагмент — внутри цитаты."""
    paragraph = doc.paragraph(evidence.paragraph_id)
    return (
        paragraph is not None
        and evidence.document_id == doc.doc_id
        and paragraph.text == evidence.exact_quote
        and evidence.exact_quote in doc.original_text
        and evidence.extracted_fragment in evidence.exact_quote
    )


def highlight(text: str, fragment: str | None) -> str:
    """HTML абзаца с подсвеченным фрагментом (весь текст экранируется)."""
    if not fragment or fragment not in text:
        return html.escape(text)
    before, _, after = text.partition(fragment)
    return f"{html.escape(before)}<mark>{html.escape(fragment)}</mark>{html.escape(after)}"
