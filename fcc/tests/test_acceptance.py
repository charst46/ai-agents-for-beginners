"""Chunk 8: acceptance test cases T-1 .. T-24 (spec Section 15).

Each test name starts with its spec number. The "Exercises" column of the
spec is kept as a pytest marker (chunk3 .. chunk7) so one module's cases
can be run alone, e.g. `pytest -m chunk5`.

All method and field names come from the assumed contract in conftest.py.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from conftest import make_event, opening_balance, outcomes

D = Decimal

chunk3 = pytest.mark.chunk3
chunk4 = pytest.mark.chunk4
chunk5 = pytest.mark.chunk5
chunk6 = pytest.mark.chunk6
chunk7 = pytest.mark.chunk7


def add_business_days(start, days):
    current = start
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days -= 1
    return current


# --- T-1 .. T-5: ingestion and identity -----------------------------------

@chunk3
@chunk4
def test_t01_exact_alias_with_receipt_is_allocated(engine):
    event = make_event(counterparty_label="SAFEWAY #1234")  # assumed approved alias
    engine.ingest(event)

    result = engine.allocate(event["event_id"])

    assert result.status == "ALLOCATED"
    assert [line.transaction_class for line in result.lines] == ["PB"]
    assert result.lines[0].economic_purpose is not None
    for finding in result.findings:
        assert finding.outcome == "PASS" or finding.severity == "ADVISORY"


@chunk3
@chunk6
def test_t02_unknown_alias_posts_once_and_holds_allocation(engine):
    event = make_event(counterparty_label="ALA", date=date(2026, 10, 5))
    engine.ingest(event)
    event_id = event["event_id"]

    assert len(engine.bank_postings(event_id)) == 1
    assert engine.allocate(event_id).status == "HELD"

    # Threshold read as "5 business days or older" -- confirm against chunk 6.
    assert event_id not in engine.aging_exceptions(add_business_days(event["date"], 3))
    assert event_id in engine.aging_exceptions(add_business_days(event["date"], 5))

    engine.resolve_identity(event_id, alias="ALBERTSONS")
    engine.allocate(event_id)
    assert len(engine.bank_postings(event_id)) == 1


@chunk3
@chunk6
def test_t03_missing_source_document_requires_review(engine):
    event = make_event(source_document=None)
    engine.ingest(event)
    event_id = event["event_id"]

    result = engine.allocate(event_id)

    assert len(engine.bank_postings(event_id)) == 1
    assert result.status == "HELD"
    doc_outcomes = outcomes(engine.findings(event_id), "R-204") + \
        outcomes(engine.findings(event_id), "R-205")
    assert "REVIEW_REQUIRED" in doc_outcomes
    assert "PASS" not in doc_outcomes


@chunk3
def test_t04_same_event_id_imported_twice_is_idempotent(engine):
    event = make_event()

    first = engine.ingest(event)
    second = engine.ingest(dict(event))

    assert first.status == "POSTED"
    assert second.status == "SKIPPED_DUPLICATE"
    assert len(engine.bank_postings(event["event_id"])) == 1


@chunk3
def test_t05_lookalike_with_different_provenance_is_flagged_not_dropped(engine):
    a = make_event(amount=D("42.10"))
    b = make_event(amount=D("42.10"))  # new event_id and provenance row

    result_a = engine.ingest(a)
    result_b = engine.ingest(b)

    assert result_a.status == "POSTED"
    assert result_b.status == "POSTED"
    assert len(engine.bank_postings(a["event_id"])) == 1
    assert len(engine.bank_postings(b["event_id"])) == 1
    assert "DUPLICATE_REVIEW" in result_a.flags + result_b.flags


# --- T-6 .. T-14: allocation and balance invariants -----------------------

POSTING_KEY_FIELDS = {"event_id", "participant_id", "bucket",
                      "benefit_program", "transaction_class"}  # assumed


@chunk4
@chunk5
def test_t06_balanced_split_allocates_both_lines(engine):
    event = make_event(amount=D("100.00"))
    engine.ingest(event)

    result = engine.allocate(event["event_id"], lines=[
        {"amount": D("60.00"), "transaction_class": "PB"},
        {"amount": D("40.00"), "transaction_class": "PB"},
    ])

    assert result.status == "ALLOCATED"
    assert len(result.lines) == 2
    assert sum(line.amount for line in result.lines) == D("100.00")  # INV-6
    for line in result.lines:
        assert POSTING_KEY_FIELDS <= set(line.posting_key)
        assert all(line.posting_key[k] is not None for k in POSTING_KEY_FIELDS)


@chunk5
def test_t07_unbalanced_split_is_critical_and_held(engine):
    event = make_event(amount=D("100.00"))
    engine.ingest(event)

    result = engine.allocate(event["event_id"], lines=[
        {"amount": D("60.00"), "transaction_class": "PB"},
        {"amount": D("39.99"), "transaction_class": "PB"},
    ])

    assert result.status == "HELD"
    inv6 = [f for f in result.findings if f.rule_id == "INV-6"]
    assert inv6 and all(f.severity == "CRITICAL" for f in inv6)


@chunk5
def test_t08_card_funding_is_not_spending(engine):
    opening_balance(engine, "500.00")
    before = engine.report("P-001").participant_total

    funding = make_event(amount=D("200.00"), transaction_class="CF",
                         counterparty_label="PREPAID CARD LOAD")
    engine.ingest(funding)
    engine.allocate(funding["event_id"])
    assert engine.report("P-001").participant_total == before

    for amount in ("37.50", "12.50"):
        purchase = make_event(amount=D(amount), transaction_class="PB")
        engine.ingest(purchase)
        engine.allocate(purchase["event_id"])

    assert engine.report("P-001").report_spent == D("50.00")  # INV-1, not 250.00


@chunk4
@chunk5
def test_t09_reimbursement_with_reference_counts_expense_once(engine):
    opening_balance(engine, "100.00")
    # Assumed shape: the original out-of-pocket expense is a manual record.
    original = make_event(amount=D("30.00"), transaction_class="PB",
                          provenance={"source_file": "manual_expenses.csv",
                                      "row_number": 1, "native_txn_id": None})
    engine.ingest(original)
    engine.allocate(original["event_id"])

    reimbursement = make_event(amount=D("30.00"), transaction_class="RE",
                               counterparty_label="J. DOE (REIMB)",
                               original_event_id=original["event_id"])
    engine.ingest(reimbursement)
    result = engine.allocate(reimbursement["event_id"])

    assert result.status == "ALLOCATED"
    assert [line.transaction_class for line in result.lines] == ["RE"]
    assert engine.report("P-001").report_spent == D("30.00")  # INV-4


@chunk5
@chunk6
def test_t10_reimbursement_without_reference_requires_review(engine):
    opening_balance(engine, "100.00")
    reimbursement = make_event(amount=D("30.00"), transaction_class="RE",
                               original_event_id=None)
    engine.ingest(reimbursement)

    result = engine.allocate(reimbursement["event_id"])

    assert result.status == "HELD"
    assert any(f.outcome == "REVIEW_REQUIRED"
               for f in engine.findings(reimbursement["event_id"]))
    assert engine.report("P-001").report_spent == D("0.00")


@chunk5
def test_t11_refund_adjusts_linked_purchase_once(engine):
    opening_balance(engine, "100.00")
    purchase = make_event(amount=D("20.00"), transaction_class="PB")
    engine.ingest(purchase)
    engine.allocate(purchase["event_id"])
    received_before = engine.report("P-001").report_received

    refund = make_event(direction="CREDIT", amount=D("5.00"),
                        transaction_class="RF",
                        original_event_id=purchase["event_id"])
    engine.ingest(refund)
    result = engine.allocate(refund["event_id"])

    assert result.status == "ALLOCATED"
    assert [line.transaction_class for line in result.lines] == ["RF"]
    report = engine.report("P-001")
    assert report.report_received == received_before  # not counted as a receipt
    assert report.report_refunded == D("5.00")  # INV-5: applied once


@chunk5
def test_t12_numeric_purchase_and_refund(engine):
    opening_balance(engine, "100.00")
    purchase = make_event(amount=D("20.00"), transaction_class="PB")
    engine.ingest(purchase)
    engine.allocate(purchase["event_id"])
    refund = make_event(direction="CREDIT", amount=D("5.00"),
                        transaction_class="RF",
                        original_event_id=purchase["event_id"])
    engine.ingest(refund)
    engine.allocate(refund["event_id"])

    report = engine.report("P-001")

    assert report.ending_balance == D("85.00")
    assert report.report_spent == D("20.00")
    # "The 5 appears exactly once": as a refund, and nowhere else.
    assert report.report_refunded == D("5.00")
    assert report.report_received == D("100.00")


@chunk5
# Spec: expected to FAIL against the literal Chunk 5 balance formula.
# Leave unmarked so the failure stays visible until the formula is fixed.
def test_t13_transfer_to_savings_is_not_double_counted(engine):
    opening_balance(engine, "100.00")
    transfer = make_event(amount=D("100.00"), transaction_class="TR",
                          bucket="REGULAR", to_bucket="SAVINGS",
                          counterparty_label="TRANSFER TO SAVINGS")
    engine.ingest(transfer)
    engine.allocate(transfer["event_id"])

    report = engine.report("P-001")

    assert report.participant_total == D("100.00")
    assert report.bucket_balances["SAVINGS"] == D("100.00")
    assert report.report_saved == D("100.00")  # INV-3, not 200.00


@chunk5
def test_t14_internal_transfer_conserves_ownership(engine):
    opening_balance(engine, "100.00")
    before = engine.report("P-001")

    transfer = make_event(amount=D("40.00"), transaction_class="TR",
                          bucket="REGULAR", to_bucket="SAVINGS",
                          counterparty_label="TRANSFER TO SAVINGS")
    engine.ingest(transfer)
    engine.allocate(transfer["event_id"])
    after = engine.report("P-001")

    assert after.participant_total == before.participant_total  # INV-2
    assert after.report_spent == before.report_spent
    assert after.bucket_balances["REGULAR"] == D("60.00")
    assert after.bucket_balances["SAVINGS"] == D("40.00")


# --- T-15 .. T-19: rules ------------------------------------------------

@chunk6
def test_t15_ssi_resource_limit_alerts_without_blocking(engine):
    opening_balance(engine, "1950.00", benefit_program="SSI")
    deposit = make_event(direction="CREDIT", amount=D("200.00"),
                         counterparty_label="SSA TREAS 310")
    engine.ingest(deposit)
    engine.allocate(deposit["event_id"])

    report = engine.report("P-001")
    assert "ALERT" in outcomes(report.findings, "R-301")
    assert report.eligibility == "UNKNOWN"

    purchase = make_event(amount=D("75.00"), transaction_class="PB")
    engine.ingest(purchase)
    assert engine.allocate(purchase["event_id"]).status == "ALLOCATED"


@chunk6
def test_t16_dedicated_bucket_spend_requires_review_not_fail(engine):
    opening_balance(engine, "500.00", bucket="DEDICATED")
    purchase = make_event(amount=D("120.00"), bucket="DEDICATED",
                          transaction_class="PB")
    engine.ingest(purchase)
    engine.allocate(purchase["event_id"])

    r303 = outcomes(engine.findings(purchase["event_id"]), "R-303")
    assert "REVIEW_REQUIRED" in r303
    assert "FAIL" not in r303


@chunk3
@chunk6
def test_t17_cleared_overhead_charge_is_recorded_and_failed(engine):
    event = make_event(counterparty_label="PAYEE ORG OFFICE SUPPLIES",
                       economic_purpose="ORGANIZATIONAL_OVERHEAD")
    ingest = engine.ingest(event)
    result = engine.allocate(event["event_id"])

    assert ingest.status == "POSTED"
    assert len(engine.bank_postings(event["event_id"])) == 1  # not discarded
    assert "FAIL" in outcomes(engine.findings(event["event_id"]), "R-501")
    assert result.status != "ALLOCATED"  # not approved


@chunk3
@chunk6
def test_t18_ffs_postage_reimbursement_is_blocked_before_execution(engine):
    action = {
        "action_id": "PROP-0001",
        "action": "REIMBURSE_PAYEE",
        "payee_type": "FEE_FOR_SERVICE",
        "purpose": "POSTAGE",
        "amount": D("8.40"),
        "participant_id": "P-001",
    }

    decision = engine.evaluate_proposed_action(action)

    assert decision.outcome == "BLOCK_PROPOSED_ACTION"
    assert decision.rule_id == "R-401"
    assert engine.bank_postings("PROP-0001") == []


@chunk6
@chunk7
def test_t19_exempt_spouse_payee_skips_report_but_keeps_records(engine):
    engine.register_payee("P-001", relationship="SPOUSE")
    opening_balance(engine, "900.00")
    purchase = make_event(amount=D("50.00"), source_document=None)
    engine.ingest(purchase)
    engine.allocate(purchase["event_id"])

    report = engine.report("P-001")
    assert outcomes(report.findings, "R-102") == ["NOT_APPLICABLE"]

    r103 = outcomes(engine.findings(purchase["event_id"]), "R-103")
    assert r103, "R-103 must still be evaluated for exempt payees"
    assert "NOT_APPLICABLE" not in r103


# --- T-20 .. T-24: classification, approval, policy ----------------------

@chunk4
@chunk5
def test_t20_interest_credit_is_not_benefit_or_spending(engine):
    interest = make_event(direction="CREDIT", amount=D("4.17"),
                          counterparty_label="INTEREST PAID",
                          benefit_program=None, source_document=None)
    engine.ingest(interest)

    result = engine.allocate(interest["event_id"])

    line, = result.lines
    assert line.benefit_program == "INTEREST"
    assert line.transaction_class in {"IR", "UC"}  # UC until IR is adopted
    assert line.transaction_class != "BR"
    assert engine.report("P-001").report_spent == D("0.00")  # INV-7


@chunk4
def test_t21_approved_room_and_board_classifies_as_rb(engine):
    event = make_event(amount=D("850.00"), counterparty_label="MAPLE CARE HOME",
                       source_document={"type": "ROOM_AND_BOARD_AGREEMENT",
                                        "id": "DOC-RB-1", "approved": True})
    engine.ingest(event)

    result = engine.allocate(event["event_id"])

    assert [line.transaction_class for line in result.lines] == ["RB"]


@chunk3
def test_t22_pending_approval_holds_allocation_and_export(engine):
    event = make_event(approval_status="PENDING")
    engine.ingest(event)
    event_id = event["event_id"]

    assert len(engine.bank_postings(event_id)) == 1
    assert engine.allocate(event_id).status == "HELD"
    assert engine.is_export_ready(event_id) is False

    engine.approve(event_id)
    assert engine.allocate(event_id).status == "ALLOCATED"
    assert engine.is_export_ready(event_id) is True
    assert len(engine.bank_postings(event_id)) == 1


@chunk3
def test_t23_identical_legitimate_purchases_are_both_kept(engine):
    opening_balance(engine, "100.00")
    a = make_event(amount=D("3.50"), counterparty_label="BUS FARE")
    b = make_event(amount=D("3.50"), counterparty_label="BUS FARE")

    results = [engine.ingest(a), engine.ingest(b)]
    allocations = [engine.allocate(e["event_id"]) for e in (a, b)]

    assert [r.status for r in results] == ["POSTED", "POSTED"]
    assert any("DUPLICATE_REVIEW" in r.flags for r in results)
    assert [r.status for r in allocations] == ["ALLOCATED", "ALLOCATED"]
    assert engine.report("P-001").report_spent == D("7.00")


@chunk6
def test_t24_adopted_internal_policy_blocks_with_reference(engine):
    engine.adopt_policy({
        "rule_id": "POL-001",
        "authority": "INTERNAL_POLICY",
        "policy_reference": "Board resolution 2026-07",
        "blocks": {"action": "CASH_WITHDRAWAL"},
    })
    decision = engine.evaluate_proposed_action({
        "action_id": "PROP-0002",
        "action": "CASH_WITHDRAWAL",
        "amount": D("60.00"),
        "participant_id": "P-001",
    })

    assert decision.outcome == "BLOCK_PROPOSED_ACTION"
    assert decision.policy_reference == "Board resolution 2026-07"
    assert decision.authority == "INTERNAL_POLICY"
    assert "SSA" not in decision.authority


# --- Suggested extras (not in the spec) ------------------------------------

def test_extra_required_rule_cannot_be_disabled(engine_cls):
    with pytest.raises(Exception):  # narrow to the real error type when known
        engine_cls(rules={"R-204": {"required": True, "enabled": False}})


def test_extra_unknown_applicability_never_passes(engine):
    opening_balance(engine, "1950.00")
    for event in (make_event(counterparty_label="ALA"),
                  make_event(source_document=None),
                  make_event(bucket="DEDICATED")):
        engine.ingest(event)
        engine.allocate(event["event_id"])

    every_finding = engine.report("P-001").findings
    unknown = [f for f in every_finding if f.applicability == "UNKNOWN"]
    assert all(f.outcome != "PASS" for f in unknown)


def test_extra_reformatted_reimport_is_treated_as_new_rows(engine):
    """Documents current behavior, not a requirement: with no native_txn_id,
    provenance-based ids see a re-exported file as new rows. Both are kept
    and flagged for duplicate review. Change this test if the design changes."""
    original = make_event(provenance={"source_file": "bank_export_v1.csv",
                                      "row_number": 4, "native_txn_id": None})
    reexport = dict(original, event_id=None,
                    provenance={"source_file": "bank_export_v2.xlsx",
                                "row_number": 17, "native_txn_id": None})

    results = [engine.ingest(original), engine.ingest(reexport)]

    assert [r.status for r in results] == ["POSTED", "POSTED"]
    assert "DUPLICATE_REVIEW" in results[1].flags
