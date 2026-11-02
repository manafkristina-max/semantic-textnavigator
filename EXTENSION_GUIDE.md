# Как добавить новое извлекаемое поле

Пример — ставка неустойки («Неустойка за просрочку поставки составляет 0,1% …»).

## 1. Правило извлечения — `navigator/extractors.py`
Добавьте запись в реестр `FIELD_SPECS`:

```python
FIELD_PENALTY = "penalty_rate"

FieldSpec(
    name=FIELD_PENALTY,
    label="Неустойка, % в день",
    clause_patterns=(
        _re(r"Неустойка\s+за\s+просрочку\s+поставки\s+составляет\s+(?P<value>\d+(?:,\d+)?)\s*%"),
    ),
    change_patterns=(_re(r"изменить\s+(?:размер\s+)?неустойк\w*\s+на\s+(?P<value>\d+(?:,\d+)?)\s*%"),),
    normalize=lambda raw: Decimal(raw.replace(",", ".")),
    hint_pattern=_re(r"неустойк"),
),
```

Правила:
- значение всегда в именованной группе `value` — она становится `extracted_fragment` цитаты;
- шаблон должен требовать контекст условия («неустойка за просрочку поставки»), а не просто «%»;
- `normalize` возвращает `None`, если значение не распознано, — тогда поле получит «Нет данных».

## 2. Связь с Evidence
Ничего делать не нужно: `extract_contract_terms` и `extract_changes` создают `Evidence`
(файл, абзац, дословная цитата, фрагмент) для любого поля реестра. Движок `rules.py`
автоматически применяет к новому полю правила допсоглашений, проектов и писем.

## 3. Интерфейс
Карточка договора (`app.py → render_card`) перебирает `FIELD_SPECS`, поэтому поле и кнопка
«Показать источник» появятся сами. Колонку в сводной таблице добавьте в `render_table`:

```python
"Неустойка": view.field(FIELD_PENALTY).display,
```

Для отображения `Decimal` при необходимости дополните `normalize.format_value`.

## 4. Тест — `tests/test_business_rules.py`
```python
def test_penalty_rate(sample_files):
    result = analyze(sample_files, CHECK)
    penalty = result.contract("STN-101").field(FIELD_PENALTY)
    assert penalty.value == Decimal("0.1")
    assert verify_evidence(result.document(penalty.evidence.document_id), penalty.evidence)
    # «Ставка неустойки в тексте договора не установлена» → Нет данных, а не 0
    assert result.contract("STN-103").field(FIELD_PENALTY).status is ValueStatus.MISSING
```

## 5. Типичные ошибки
- Захват «не более 10%» (потолок) вместо ставки 0,1% — шаблон должен брать число сразу после «составляет».
- Запятая как десятичный разделитель: `0,1` → `Decimal("0.1")`, не `float`.
- Фраза «размер неустойки остается без изменений» в допсоглашении не является изменением — `change_patterns`
  должны требовать «изменить … на …».
- Отсутствие ставки — это «Нет данных», а не 0.
- После добавления поля строка статуса договора учитывает его: если ставки нет, весь договор получит «Нет данных».
  Если это нежелательно, исключите поле из расчета статуса в `rules.build_contract_view`.
