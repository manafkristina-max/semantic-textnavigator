"""Ответы на четыре вопроса на исходном наборе и сквозная проверка UI через Streamlit AppTest."""
from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from navigator.pipeline import analyze
from navigator.questions import QUESTIONS

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def answers(files):
    result = analyze(files)
    return [q.run(result) for q in QUESTIONS]


def test_q1_delivery_stn101(sample_files):
    a = answers(sample_files)[0]
    assert "30.04.2026" in a.summary and "Доп. соглашение № 1" in a.summary
    assert any("15.04.2026" in d for d in a.details)  # первоначальное значение
    assert any("10.05.2026" in d and "не применяется" in d for d in a.details)


def test_q2_q3_amounts(sample_files):
    q2, q3 = answers(sample_files)[1:3]
    assert "840 000" in q2.summary and "252 000" not in q2.summary
    assert "Нет данных" in q3.summary and "600 000" not in q3.summary


def test_q4_before_april(sample_files):
    a = answers(sample_files)[3]
    assert "STN-102" in a.summary
    assert "STN-101" not in a.summary and "STN-103" not in a.summary
    pending = a.details[-1]
    assert "27.03.2026" in pending and "10.05.2026" in pending


def test_questions_report_missing_contract():
    a = answers([])[0]
    assert "не найден" in a.summary


def test_app_end_to_end():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.button[0].click().run()  # «Проанализировать» с папкой documents
    assert not at.exception
    assert any("Обработано документов: 6" in s.value for s in at.success)
    # Карточка договора: открываем источник суммы STN-101.
    source_buttons = [b for b in at.button if b.label == "Показать источник" and not b.disabled]
    source_buttons[0].click().run()
    assert not at.exception
    assert any("Цитата дословно найдена" in c.value for c in at.caption)
    # Смена договора сбрасывает панель источника — цитата чужого договора не остается на экране.
    contract_box = next(s for s in at.selectbox if s.label == "Договор")
    contract_box.select("STN-103").run()
    assert not at.exception
    assert not any("Цитата дословно найдена" in c.value for c in at.caption)
    assert any("Нажмите «Показать источник»" in i.value for i in at.info)
    # У отсутствующей суммы кнопка источника неактивна, а не «декоративна».
    assert any(b.label == "Показать источник" and b.disabled for b in at.button)
