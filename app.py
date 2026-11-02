"""Streamlit UI. Только отображение: вся логика — в пакете navigator."""
from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from navigator.evidence import highlight, verify_evidence
from navigator.extractors import FIELD_AMOUNT, FIELD_DELIVERY, FIELD_SPECS, FIELD_SUPPLIER
from navigator.models import AnalysisResult, ContractView, Evidence, ValueStatus
from navigator.pipeline import DEFAULT_CHECK_DATE, analyze, read_folder
from navigator.questions import QUESTIONS

SAMPLES_DIR = Path(__file__).parent / "documents"
STATUS_ICON = {ValueStatus.CONFIRMED: "🟢", ValueStatus.MISSING: "⚪", ValueStatus.REVIEW: "🟠"}

st.set_page_config(page_title="Semantic TextNavigator", page_icon="📄", layout="wide")
st.markdown(
    """
    <style>
      mark { background: #ffe58a; padding: 0 2px; border-radius: 3px; }
      .stn-quote { border-left: 4px solid #f0b400; background: rgba(240,180,0,.08);
                   padding: .6rem .9rem; border-radius: 4px; margin: .4rem 0 .8rem; }
      .stn-doc { font-family: ui-monospace, Menlo, monospace; font-size: .86rem;
                 border: 1px solid rgba(128,128,128,.3); border-radius: 6px; padding: .5rem; }
      .stn-p { padding: 2px 6px; border-radius: 4px; }
      .stn-p .ln { color: #888; display: inline-block; width: 3.2em; }
      .stn-target { background: rgba(240,180,0,.18); outline: 1px solid #f0b400; }
      /* Панель источника закреплена: открытый абзац виден без прокрутки, откуда бы ни нажали кнопку. */
      div[data-testid="stColumn"]:has(.stn-source-anchor) {
        position: sticky; top: 3.75rem; align-self: flex-start; max-height: calc(100vh - 4.5rem); overflow-y: auto;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def run_analysis(files: list[tuple[str, bytes]], check_date) -> None:
    # В сессии храним исходные файлы, а не объекты результата: при горячей перезагрузке кода
    # классы пересоздаются, а файлы и дата переживают перезапуск и анализ просто пересчитывается.
    st.session_state["files"] = files
    st.session_state["check_date"] = check_date
    st.session_state.pop("source", None)


def current_result() -> AnalysisResult | None:
    if "files" not in st.session_state:
        return None
    return analyze(st.session_state["files"], st.session_state["check_date"])


def show_source_button(evidence: Evidence | None, key: str, label: str = "Показать источник") -> None:
    if evidence is None:
        st.button(label, key=key, disabled=True, help="Нет подтвержденного источника")
    elif st.button(label, key=key):
        st.session_state["source"] = evidence


# ---------- Экран 1. Загрузка ----------
def render_upload() -> None:
    st.write(
        "Загрузите TXT-документы по договорам поставки: договоры, дополнительные соглашения, письма, проекты. "
        "Система покажет **действующие** на дату проверки сумму и срок поставки с точными цитатами из источников. "
        "Изменения применяются только по подписанным обеими сторонами и вступившим в силу допсоглашениям."
    )
    col1, col2 = st.columns([1, 2])
    check_date = col1.date_input("Дата проверки", value=DEFAULT_CHECK_DATE, format="DD.MM.YYYY")
    uploaded = col2.file_uploader("TXT-документы", type=["txt"], accept_multiple_files=True)
    use_samples = st.checkbox(
        f"Использовать документы из папки «{SAMPLES_DIR.name}» (перечитываются с диска при каждом анализе)",
        value=not uploaded,
    )
    if st.button("Проанализировать", type="primary"):
        files = [(f.name, f.getvalue()) for f in uploaded or []]
        if use_samples and SAMPLES_DIR.exists():
            files += read_folder(SAMPLES_DIR)
        if not files:
            st.error("Нет файлов для анализа: загрузите TXT или включите папку с примерами.")
        else:
            run_analysis(files, check_date)

    result = current_result()
    if not result:
        return
    st.success(
        f"Обработано документов: {len(result.documents)}; договоров: {len(result.contracts)}; "
        f"дата проверки {result.check_date:%d.%m.%Y}."
    )
    for name, reason in result.rejected_files:
        st.error(f"Файл «{name}» не обработан: {reason}")
    for warning in result.warnings:
        st.warning(warning)
    st.subheader("Распознанные документы")
    st.dataframe(
        [
            {
                "Файл": d.filename,
                "Тип (по содержимому)": d.document_type.value,
                "Подписание": d.signature_status.value,
                "Вступает в силу": f"{d.effective_date:%d.%m.%Y}" if d.effective_date else "—",
                "Договор": ", ".join(d.related_contract_numbers) or "—",
                "Предупреждения": "; ".join(d.warnings) or "—",
            }
            for d in result.documents
        ],
        hide_index=True,
    )
    with st.expander("Основания классификации"):
        for d in result.documents:
            st.markdown(f"**{html.escape(d.filename)}**")
            for reason in d.classification_evidence:
                st.text(reason)


# ---------- Экран 2. Сводная таблица ----------
def changes_text(view: ContractView) -> str:
    parts = []
    for doc in view.applied_amendments:
        changed = [f.label.split(",")[0].lower() for f in view.fields.values() if f.changed_by == doc.label]
        parts.append(f"{doc.label}: {', '.join(changed) or 'без изменений полей'}")
    for doc in view.not_in_force:
        parts.append(f"{doc.label}: не вступило в силу")
    return "; ".join(parts) or "—"


def pending_text(view: ContractView) -> str:
    if not view.pending:
        return "нет"
    labels = {spec.name: spec.label.split(",")[0].lower() for spec in FIELD_SPECS}
    return "Да: " + "; ".join(f"{labels[p.field_name]} → {p.display} ({p.source_label})" for p in view.pending)


def render_table(result: AnalysisResult) -> None:
    if not result.contracts:
        st.info("Договоры не найдены в загруженных документах.")
        return
    rows = []
    for view in result.contracts:
        amount, delivery = view.field(FIELD_AMOUNT), view.field(FIELD_DELIVERY)
        rows.append(
            {
                "Договор": view.contract_number,
                "Поставщик": view.field(FIELD_SUPPLIER).display,
                "Сумма, ₽": amount.display + (" *" if amount.is_changed else ""),
                "Срок поставки": delivery.display + (" *" if delivery.is_changed else ""),
                "Статус": f"{STATUS_ICON[view.status]} {view.status.value}",
                "Изменения": changes_text(view),
                "Несогласованные изменения": pending_text(view),
            }
        )
    st.dataframe(rows, hide_index=True)
    st.caption(
        f"Условия на {result.check_date:%d.%m.%Y}. * — значение изменено действующим допсоглашением. "
        "Несогласованные изменения (проекты, письма) показаны отдельно и не применяются."
    )
    st.caption("Подробности и цитаты — во вкладке «Карточка договора».")


# ---------- Экран 3. Карточка договора и навигатор источников ----------
def render_field(view: ContractView, name: str) -> None:
    f = view.field(name)
    with st.container(border=True):
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"**{f.label}:** {STATUS_ICON[f.status]} {html.escape(f.display)}  \n"
                    f"<small>{f.status.value}</small>", unsafe_allow_html=True)
        with c2:
            show_source_button(f.evidence, key=f"src-{view.contract_number}-{name}")
        if f.changed_by:
            st.markdown(f"Изменено: **{f.changed_by}**. Первоначальное значение: {f.initial_display or 'Нет данных'}")
            show_source_button(f.initial_evidence, key=f"src0-{view.contract_number}-{name}",
                               label="Источник первоначального значения")
        for note in f.notes:
            st.caption(note)


def render_card(result: AnalysisResult) -> None:
    if not result.contracts:
        st.info("Нет договоров для отображения.")
        return
    numbers = [c.contract_number for c in result.contracts]
    number = st.selectbox("Договор", numbers)
    view = result.contracts[numbers.index(number)]
    if st.session_state.get("card_contract") != number:
        # Источник, открытый для другого договора, не должен оставаться на экране.
        st.session_state.pop("source", None)
        st.session_state["card_contract"] = number

    left, right = st.columns([1, 1])
    with left:
        st.subheader(f"Договор {view.contract_number}")
        st.markdown(f"Статус: {STATUS_ICON[view.status]} **{view.status.value}** · файл «{view.document.filename}»")
        for spec in FIELD_SPECS:
            render_field(view, spec.name)

        st.markdown("**Примененные допсоглашения**")
        if view.applied_amendments:
            for doc in view.applied_amendments:
                st.markdown(f"- {doc.label} — «{doc.filename}»")
        else:
            st.caption("Нет")

        st.markdown("**Неутвержденные предложения (не применяются)**")
        if view.pending:
            for i, p in enumerate(view.pending):
                label = next(s.label for s in FIELD_SPECS if s.name == p.field_name)
                st.markdown(f"- {label}: **{p.display}** — {p.source_label}, «{p.evidence.filename}». Причина: {p.reason}")
                show_source_button(p.evidence, key=f"src-p-{view.contract_number}-{i}")
        else:
            st.caption("Нет")

        if view.warnings:
            st.markdown("**Предупреждения**")
            for w in view.warnings:
                st.warning(w)
    with right:
        render_source_panel(result)


def render_source_panel(result: AnalysisResult) -> None:
    st.markdown('<div class="stn-source-anchor"></div>', unsafe_allow_html=True)
    st.subheader("Источник")
    evidence: Evidence | None = st.session_state.get("source")
    doc = result.document(evidence.document_id) if evidence else None
    if evidence is None or doc is None:
        st.info("Нажмите «Показать источник» у значения, чтобы открыть абзац документа.")
        return
    paragraph = doc.paragraph(evidence.paragraph_id)
    st.markdown(
        f"Файл: **{html.escape(evidence.filename)}** · абзац **{evidence.paragraph_id}** "
        f"(строка {paragraph.line_no}) · источник: {html.escape(evidence.source_role)}"
    )
    st.markdown(
        f'<div class="stn-quote">{highlight(evidence.exact_quote, evidence.extracted_fragment)}</div>',
        unsafe_allow_html=True,
    )
    if verify_evidence(doc, evidence):
        st.caption("✅ Цитата дословно найдена в загруженном тексте")
    else:
        st.error("Цитата не найдена в исходном тексте — значение нельзя считать подтвержденным")
    lines = []
    for p in doc.paragraphs:
        target = p.paragraph_id == evidence.paragraph_id
        body = highlight(p.text, evidence.extracted_fragment if target else None)
        css = "stn-p stn-target" if target else "stn-p"
        lines.append(f'<div class="{css}" id="stn-{p.paragraph_id}"><span class="ln">{p.line_no}</span>{body}</div>')
    st.markdown(f'<div class="stn-doc">{"".join(lines)}</div>', unsafe_allow_html=True)


# ---------- Экран 4. Вопросы ----------
def render_questions(result: AnalysisResult) -> None:
    texts = [q.text for q in QUESTIONS]
    choice = st.selectbox("Вопрос", texts)
    answer = QUESTIONS[texts.index(choice)].run(result)
    st.caption(f"Ответ рассчитан по загруженным документам на дату проверки {result.check_date:%d.%m.%Y}.")
    st.markdown(answer.summary)
    for line in answer.details:
        st.markdown(f"- {line}")
    if answer.sources:
        with st.expander("Цитаты-источники"):
            for e in answer.sources:
                st.markdown(
                    f"«{html.escape(e.filename)}», {e.paragraph_id} — {html.escape(e.source_role)}"
                    f'<div class="stn-quote">{highlight(e.exact_quote, e.extracted_fragment)}</div>',
                    unsafe_allow_html=True,
                )


# ---------- Каркас ----------
st.title("Semantic TextNavigator")
st.caption("Действующие условия договоров поставки — с проверяемыми цитатами из исходных документов")

tab_upload, tab_table, tab_card, tab_questions = st.tabs(
    ["1. Загрузка", "2. Сводная таблица", "3. Карточка договора", "4. Вопросы"]
)
with tab_upload:
    render_upload()

current = current_result()
for tab, render in ((tab_table, render_table), (tab_card, render_card), (tab_questions, render_questions)):
    with tab:
        if current is None:
            st.info("Сначала загрузите документы и нажмите «Проанализировать» на вкладке «Загрузка».")
        else:
            render(current)
