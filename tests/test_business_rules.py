"""Обязательные сценарии 1–14 из ТЗ. Все проверки идут через публичный analyze(), т.е. через реальную обработку текста."""
from __future__ import annotations

import itertools
from datetime import date

from conftest import amendment_text, as_files, contract_text

from navigator.evidence import verify_evidence
from navigator.extractors import FIELD_AMOUNT, FIELD_DELIVERY, FIELD_SUPPLIER
from navigator.models import ValueStatus
from navigator.pipeline import analyze
from navigator.questions import deliveries_before

CHECK = date(2026, 3, 10)


def snapshot(result):
    """Сравнимое представление результата: номер → (статус и значение каждого поля, предложения)."""
    return {
        c.contract_number: (
            c.status,
            tuple((name, f.status, f.value, f.changed_by) for name, f in sorted(c.fields.items())),
            tuple(sorted((p.field_name, p.display) for p in c.pending)),
        )
        for c in result.contracts
    }


def test_01_basic_extraction(sample_files):
    contract_101 = [f for f in sample_files if "№ STN-101" in f[1].decode()[:40]]
    view = analyze(contract_101, CHECK).contract("STN-101")
    assert view is not None
    assert view.field(FIELD_SUPPLIER).value == "ООО «Вектор Прибор»"
    assert view.field(FIELD_AMOUNT).value == 1_200_000
    assert view.field(FIELD_DELIVERY).value == date(2026, 4, 15)
    assert view.status is ValueStatus.CONFIRMED


def test_02_amount_change_in_source_is_reflected():
    before = analyze(as_files(contract_text(amount="500 000")), CHECK).contract("STN-201")
    after = analyze(as_files(contract_text(amount="777 000")), CHECK).contract("STN-201")
    assert before.field(FIELD_AMOUNT).value == 500_000
    assert after.field(FIELD_AMOUNT).value == 777_000


def test_03_signed_amendment_changes_only_listed_term():
    result = analyze(as_files(contract_text(), amendment_text(amount="650 000")), CHECK)
    view = result.contract("STN-201")
    amount = view.field(FIELD_AMOUNT)
    assert amount.value == 650_000 and amount.changed_by is not None
    assert amount.initial_display == "500 000"
    assert "Доп. соглашение" in amount.evidence.source_role
    # Срок соглашением не менялся — остается из договора.
    assert view.field(FIELD_DELIVERY).value == date(2026, 3, 25)
    assert view.field(FIELD_DELIVERY).changed_by is None


def test_04_unsigned_draft_does_not_apply(sample_files):
    view = analyze(sample_files, CHECK).contract("STN-101")
    assert view.field(FIELD_AMOUNT).value == 1_380_000  # из подписанного ДС № 1, а не 1 450 000 из проекта
    assert view.field(FIELD_DELIVERY).value == date(2026, 4, 30)  # не 10.05.2026
    assert {(p.field_name, p.display) for p in view.pending} == {
        (FIELD_AMOUNT, "1 450 000"),
        (FIELD_DELIVERY, "10.05.2026"),
    }


def test_04b_unsigned_amendment_is_only_a_proposal():
    draft = amendment_text(amount="999 000", status="не подписано сторонами")
    view = analyze(as_files(contract_text(), draft), CHECK).contract("STN-201")
    assert view.field(FIELD_AMOUNT).value == 500_000
    assert [p.display for p in view.pending] == ["999 000"]


def test_05_letter_is_shown_separately_and_does_not_change(sample_files):
    view = analyze(sample_files, CHECK).contract("STN-102")
    assert view.field(FIELD_DELIVERY).value == date(2026, 3, 20)
    assert view.field(FIELD_DELIVERY).changed_by is None
    [proposal] = view.pending
    assert proposal.field_name == FIELD_DELIVERY and proposal.display == "27.03.2026"
    assert proposal.source_label == "Письмо"


def test_06_missing_amount_shows_no_data(sample_files):
    amount = analyze(sample_files, CHECK).contract("STN-103").field(FIELD_AMOUNT)
    assert amount.status is ValueStatus.MISSING and amount.display == "Нет данных"
    assert amount.value is None  # бюджетный лимит 600 000 не подставлен


def test_06b_missing_amount_synthetic():
    view = analyze(as_files(contract_text(amount=None)), CHECK).contract("STN-201")
    assert view.field(FIELD_AMOUNT).status is ValueStatus.MISSING
    assert view.field(FIELD_AMOUNT).value is None  # аванс 100 000 не принят за сумму
    assert view.status is ValueStatus.MISSING


def test_07_missing_delivery_shows_no_data():
    view = analyze(as_files(contract_text(delivery=None)), CHECK).contract("STN-201")
    delivery = view.field(FIELD_DELIVERY)
    assert delivery.status is ValueStatus.MISSING and delivery.display == "Нет данных"
    assert delivery.value is None  # срок оплаты 30.06.2026 не принят за срок поставки


def test_08_every_quote_exists_in_source(sample_files):
    result = analyze(sample_files, CHECK)
    checked = 0
    for view in result.contracts:
        evidences = [f.evidence for f in view.fields.values()] + [f.initial_evidence for f in view.fields.values()]
        evidences += [p.evidence for p in view.pending]
        for evidence in filter(None, evidences):
            doc = result.document(evidence.document_id)
            assert verify_evidence(doc, evidence), evidence
            assert evidence.exact_quote in doc.original_text
            checked += 1
    assert checked >= 12


def test_09_renaming_files_does_not_change_terms(sample_files):
    renamed = [(f"zzz_{i}_99.12.2030.txt", data) for i, (_, data) in enumerate(reversed(sample_files))]
    assert snapshot(analyze(renamed, CHECK)) == snapshot(analyze(sample_files, CHECK))


def test_10_amendment_effective_after_check_date_is_not_applied():
    files = as_files(contract_text(), amendment_text(amount="650 000", effective="15.03.2026"))
    view = analyze(files, CHECK).contract("STN-201")
    assert view.field(FIELD_AMOUNT).value == 500_000
    assert len(view.not_in_force) == 1
    later = analyze(files, date(2026, 3, 15)).contract("STN-201")
    assert later.field(FIELD_AMOUNT).value == 650_000


def test_10b_real_amendment_respects_check_date(sample_files):
    view = analyze(sample_files, date(2026, 2, 28)).contract("STN-101")
    assert view.field(FIELD_AMOUNT).value == 1_200_000
    assert view.field(FIELD_DELIVERY).value == date(2026, 4, 15)


def test_11_new_contract_appears_without_code_changes(sample_files):
    new = contract_text(number="STN-777", supplier="ООО «Новый Поставщик»", amount="1 050 000", delivery="31.03.2026")
    result = analyze(sample_files + [("new.txt", new.encode())], CHECK)
    view = result.contract("STN-777")
    assert view.field(FIELD_SUPPLIER).value == "ООО «Новый Поставщик»"
    assert view.field(FIELD_AMOUNT).value == 1_050_000
    assert "STN-777" in deliveries_before(result, date(2026, 4, 1)).summary


def test_12_conflicting_amendments_require_review():
    files = as_files(
        contract_text(),
        amendment_text(amount="600 000", n=1),
        amendment_text(amount="700 000", n=2),
    )
    amount = analyze(files, CHECK).contract("STN-201").field(FIELD_AMOUNT)
    assert amount.status is ValueStatus.REVIEW and amount.value is None


def test_12b_later_amendment_supersedes_earlier():
    files = as_files(
        contract_text(),
        amendment_text(amount="600 000", n=1, effective="01.03.2026"),
        amendment_text(amount="700 000", n=2, effective="05.03.2026"),
    )
    assert analyze(files, CHECK).contract("STN-201").field(FIELD_AMOUNT).value == 700_000


def test_12c_amendment_without_effective_date_requires_review():
    files = as_files(contract_text(), amendment_text(amount="650 000", effective=None))
    amount = analyze(files, CHECK).contract("STN-201").field(FIELD_AMOUNT)
    assert amount.status is ValueStatus.REVIEW


def test_13_upload_order_does_not_matter(sample_files):
    reference = snapshot(analyze(sample_files, CHECK))
    for perm in itertools.islice(itertools.permutations(sample_files), 0, 720, 97):
        assert snapshot(analyze(list(perm), CHECK)) == reference


def test_14_boundary_date_before_april_first():
    result = analyze(
        as_files(
            contract_text(number="STN-331", delivery="31.03.2026"),
            contract_text(number="STN-401", delivery="01.04.2026"),
        ),
        CHECK,
    )
    summary = deliveries_before(result, date(2026, 4, 1)).summary
    assert "STN-331" in summary
    assert "STN-401" not in summary
