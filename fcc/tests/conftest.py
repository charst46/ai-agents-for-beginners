"""Shared fixtures for the Chunk 8 acceptance tests (spec Section 15).

The engine under test is loaded from the FCC_ENGINE environment variable,
written as "package.module:ClassName". Example:

    FCC_ENGINE=fcc.engine:Engine pytest fcc/tests

If FCC_ENGINE is unset or cannot be imported, every test is skipped rather
than failing on import.

ASSUMED CONTRACT. Chunks 3-7 were not available when these tests were
written, so every method name, field name and enum string below is an
assumption. If the real modules use different names, change them in THIS
file (or write a thin adapter class) instead of editing the tests.

Engine(rules=None): rules maps rule_id -> config dict; it must raise at
construction if a REQUIRED rule has enabled = False.
Event dicts: see make_event() below. A transfer adds "to_bucket"; a refund
or reimbursement sets "original_event_id"; event_id=None means "derive it
from provenance".

    ingest(event: dict) -> IngestResult
        .status: "POSTED" | "SKIPPED_DUPLICATE"            (chunk 3)
        .flags:  list[str], e.g. "DUPLICATE_REVIEW"
    bank_postings(event_id) -> list                         (chunk 3)
        one entry per bank-effect posting for that event
    allocate(event_id, lines=None) -> AllocationResult      (chunks 4, 5)
        .status: "ALLOCATED" | "HELD"
        .lines:  list of objects with .transaction_class, .amount,
                 .posting_key (dict), .economic_purpose, .benefit_program
        .findings: list[Finding]
    resolve_identity(event_id, alias: str) -> None          (chunk 3)
    attach_document(event_id, document: dict) -> None       (chunk 3)
    approve(event_id) -> None                               (chunk 3)
    register_payee(participant_id, relationship: str)       (chunks 6, 7)
    adopt_policy(rule: dict) -> None                        (chunk 6)
    findings(event_id) -> list[Finding]                     (chunk 6)
    evaluate_proposed_action(action: dict) -> Decision      (chunk 6)
        .outcome, .rule_id, .policy_reference, .authority
    aging_exceptions(as_of: date) -> list[str]  (event_ids) (chunk 6)
    is_export_ready(event_id) -> bool                       (chunk 7)
    report(participant_id, period=None) -> Report           (chunks 5, 7)
        .report_spent, .report_saved, .report_received,
        .report_refunded, .ending_balance,
        .participant_total, .bucket_balances: dict[str, Decimal],
        .eligibility, .findings: list[Finding]

Finding: .rule_id, .outcome, .severity, .applicability
    outcome strings: PASS FAIL ALERT REVIEW_REQUIRED NOT_APPLICABLE
                     BLOCK_PROPOSED_ACTION UNKNOWN
    severity strings: CRITICAL ADVISORY
"""

import importlib
import os
from datetime import date
from decimal import Decimal
from itertools import count

import pytest

D = Decimal
_ids = count(1)


def pytest_configure(config):
    for n in range(3, 8):
        config.addinivalue_line("markers", f"chunk{n}: exercises chunk {n}")


def _load_engine_class():
    spec = os.environ.get("FCC_ENGINE")
    if not spec:
        pytest.skip("FCC_ENGINE not set (expected 'package.module:ClassName')")
    module_name, _, class_name = spec.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        pytest.skip(f"cannot import {module_name}: {exc}")
    return getattr(module, class_name)


@pytest.fixture
def engine_cls():
    return _load_engine_class()


@pytest.fixture
def engine(engine_cls):
    return engine_cls()


def make_event(**overrides):
    """Build one bank event. All amounts are Decimal and positive; the
    direction field says which way the money moved."""
    n = next(_ids)
    event = {
        "event_id": f"EVT-{n:05d}",
        "provenance": {
            "source_file": "bank_2026-10.csv",
            "row_number": n,
            "native_txn_id": f"BANK-{n:05d}",
        },
        "date": date(2026, 10, 5),
        "direction": "DEBIT",
        "amount": D("25.00"),
        "counterparty_label": "SAFEWAY #1234",
        "participant_id": "P-001",
        "bucket": "REGULAR",
        "benefit_program": "SSI",
        "source_document": {"type": "RECEIPT", "id": f"DOC-{n:05d}"},
        "approval_status": "APPROVED",
        "transaction_class": None,
        "original_event_id": None,
        "payee_type": "ORGANIZATIONAL",
    }
    event.update(overrides)
    return event


def outcomes(findings, rule_id):
    """All outcomes recorded for one rule id."""
    return [f.outcome for f in findings if f.rule_id == rule_id]


def opening_balance(engine, amount, participant_id="P-001", bucket="REGULAR",
                    benefit_program="SSI"):
    """Seed a beginning balance as a benefit deposit and allocate it."""
    event = make_event(
        direction="CREDIT",
        amount=D(amount),
        counterparty_label="SSA TREAS 310",
        participant_id=participant_id,
        bucket=bucket,
        benefit_program=benefit_program,
        date=date(2026, 10, 1),
    )
    engine.ingest(event)
    engine.allocate(event["event_id"])
    return event
