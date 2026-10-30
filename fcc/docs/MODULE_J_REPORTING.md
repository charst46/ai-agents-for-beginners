# Module J: SSA Accounting Support (Ledger and Annual Report Draft)

Rewritten 2026-10-30 to match SSA requirements. Verbatim source text is in
`SSA_SOURCE_QUOTES.md` (the section numbers below, such as §11, refer to that file).

## Source tags

Every requirement line carries one tag:

| Tag | Meaning |
|---|---|
| `[REG]` | 20 CFR § 404.2065 / § 416.665 (binding regulation) |
| `[POMS <section>]` | SSA staff instructions; shows how SSA applies the rules |
| `[DESIGN]` | FCC's own choice. SSA does not require it. Can be changed freely. |
| `[INFERENCE]` | Reasoned from SSA text, not stated by SSA. Verify before relying on it. |
| `[UNVERIFIED]` | Comes from a source not retrieved (the Org Guide, the SSA-6234 form itself). Check against the form you receive. |

## What changed from the previous Module J

| Old item | Change | Why |
|---|---|---|
| `monthly_ledger` (header comment only) | Replaced by `ledger_entries` + `monthly_ledger` + `monthly_reconciliation` with full bodies | GN 00603.020 D.3 requires per-transaction records and monthly reconciliation (§11) |
| Ledger column list (receipt_no, etc.) | Columns now follow D.3: date, whom paid, amount, deposit by program, interest, transfers, share of collective payments. `receipt_no` is kept as optional | §11. SSA's sample ledger exhibit was not retrieved, so its layout is not binding |
| `benefits_received` by program | Moved to the ledger (SS and SSI deposits listed separately); report uses Total Accountable Amount | §11 D.3.a; TAA is printed by SSA (§5) |
| *(missing)* beginning balance | Added as `prior_conserved_funds`, part of TAA | §5 |
| `spent_by_purpose` by economic_purpose | Report now uses the form's buckets: food and housing / other (personal needs) / saved. `economic_purpose` stays in the ledger only | §8; purpose detail is `[DESIGN]` |
| `saved` (Module F, single-counted) | Now `saved_end_of_period` **including interest** | Form instructions (`[UNVERIFIED]`); interest belongs to beneficiary (§10, §11) |
| *(missing)* fee | Added: fee collected yes/no and amount, capped at SSA's Maximum Fee Amount | §6 Q2B, §5 MFA |
| *(missing)* where lived, who decided | Added: `custody` and `decision_maker` | `[REG]` (c)(1)–(2); §6 Q1, Q2 |
| *(missing)* how savings are held and titled | Added: `conserved_funds_holdings` | `[REG]` (c)(4); §6 Q3–4 |
| `dedicated_account` "separate statement" | Now a **separate report** (SSA-6233-BK); the annual report is not produced for that participant | §3 NOTE |
| `exempt_status (R-102)` | Kept; organizations are never exempt | `[REG]` (b) |
| *(missing)* SSA's screening checks | Added: 90% coverage, $360 personal needs (institution), $2,000 SSI, $500 titling review | §8, §9 |
| *(missing)* interest allocation | Added: `allocate_interest` | §11 |

---

## Constants

```text
COVERAGE_MIN                = 0.90     // [POMS GN 00605.070, .040] §8, §9
INSTITUTION_PERSONAL_MIN    = 360.00   // [POMS GN 00605.070] §8, per report period
SSI_CONSERVED_ALERT         = 2000.00  // [POMS GN 00605.001, .070] §3, §8 (Title XVI / concurrent only)
TITLING_REVIEW_THRESHOLD    = 500.00   // [POMS GN 00605.070] §8, Q4 applies only above this
INTEREST_STRICT_THRESHOLD   = 10.00    // [POMS GN 00603.020 D.3] §11, per quarter, whole collective account
```

`[INFERENCE]` The $3,000 couples limit is from the user's Compendium, not from the sources in
`SSA_SOURCE_QUOTES.md`. Leave it out until verified.

---

## J.1 Ledger entries (the per-beneficiary record)

```text
ENUM entry_type :                                                      // [POMS GN 00603.020 D.3] §11
    DEPOSIT_SS          // Social Security deposit        (D.3.a "listing … Social Security … deposits")
    DEPOSIT_SSI         // SSI deposit                    (D.3.a "listing … SSI deposits")
    INTEREST            // interest credited to this beneficiary (D.3.a "posting any interest")
    EXPENDITURE         // payment for the beneficiary    (D.3.b)
    PNA_TRANSFER        // personal needs allowance handed to staff/facility, one entry per month (D.3.c)
    TRANSFER_OUT        // moved to another account or vehicle, e.g. a CD (D.3.d)
    TRANSFER_IN         // returned from another account or vehicle (D.3.d)
    REFUND              // money returned by a vendor for an earlier EXPENDITURE   [DESIGN]
    RETURN_TO_SSA       // funds returned to SSA                                   [DESIGN]
    FEE                 // SSA-authorized payee fee                                [POMS GN 00605.065] §6

RECORD ledger_entry :
    participant_id
    date                            // REQUIRED for every entry           [POMS GN 00603.020 D.3.b]
    entry_type
    amount        : Decimal > 0     // direction comes from entry_type, never from the sign  [DESIGN]
    paid_to                         // REQUIRED for EXPENDITURE, FEE, PNA_TRANSFER  [POMS D.3.b "whom they paid"]
    collective_payment_total        // REQUIRED when one payment covered several beneficiaries
    collective_payment_share        //   this beneficiary's part of it    [POMS D.3.b "individual dollar amount of any total collectively paid"]
    destination_account             // REQUIRED for TRANSFER_OUT / TRANSFER_IN  [POMS D.3.d]
    original_entry_ref              // REQUIRED for REFUND                [DESIGN]
    use_category                    // FOOD_HOUSING | OTHER, REQUIRED for EXPENDITURE  (feeds J.4)  [INFERENCE: form buckets]
    economic_purpose                // optional finer detail              [DESIGN]
    source_document_ref             // receipt, check, statement line; optional  [DESIGN]
    receipt_no                      // optional                           [DESIGN]
    statement_ref                   // bank statement line that this entry ties to  [DESIGN]

FUNCTION validate_entry(e) :
    IF e.date IS NULL OR e.amount IS NULL                → finding REVIEW_REQUIRED "D.3.b date/amount missing"
    IF e.entry_type IN {EXPENDITURE, FEE, PNA_TRANSFER} AND e.paid_to IS NULL
                                                         → finding REVIEW_REQUIRED "D.3.b whom paid missing"
    IF e.collective_payment_total IS NOT NULL AND e.collective_payment_share IS NULL
                                                         → finding REVIEW_REQUIRED "D.3.b individual share missing"
    IF e.entry_type IN {TRANSFER_OUT, TRANSFER_IN} AND e.destination_account IS NULL
                                                         → finding REVIEW_REQUIRED "D.3.d transfer destination missing"
    IF e.entry_type = EXPENDITURE AND e.use_category IS NULL
                                                         → finding REVIEW_REQUIRED "use category needed for annual report"
    IF e.entry_type = REFUND AND e.original_entry_ref IS NULL
                                                         → finding REVIEW_REQUIRED "refund not linked to expenditure"
```

**Sign rule** `[DESIGN]`: each `entry_type` has a fixed effect on the balance (+ for DEPOSIT_SS,
DEPOSIT_SSI, INTEREST, TRANSFER_IN, REFUND; − for the rest). The amount is always stored positive.
This rule exists because current FCC code classifies outgoing "reimbursement" items as increases (it
uses `abs()` in `nonprofit_custodial_reconstruction.py` and in the protected bridge runner).

**Reimbursing staff for out-of-pocket purchases** is an `EXPENDITURE` with `paid_to` = the staff
member. It is **not** a `REFUND`. `[DESIGN]`

**Transfers to a CD or savings vehicle stay in the beneficiary's funds** as conserved funds: "The
account ledger must reflect this CD as conserved funds." `[POMS GN 00603.020 D.3.d]` They are not
spending. `[INFERENCE]` from that sentence.

---

## J.2 Interest allocation

```text
FUNCTION allocate_interest(collective_account, quarter) :              // [POMS GN 00603.020 D.3] §11
    total = interest credited to collective_account in quarter
    holders = beneficiaries with a positive share during quarter
    IF total <= INTEREST_STRICT_THRESHOLD :
        method = EQUAL_SPLIT              // "reasonable method … such as equally dividing"
    ELSE :
        method = PRORATE_BY_SHARE         // "should prorate … based on their share of funds"
        // share measure: average daily balance in the quarter  [DESIGN]; SSA does not name one
    FOR each holder : create ledger_entry(entry_type = INTEREST, amount = allocated part)
    rounding: allocate cents so the parts sum exactly to total   [DESIGN]
    RETURN allocations, method
```

---

## J.3 Monthly ledger and reconciliation

```text
FUNCTION monthly_ledger(participant, month) :                          // [POMS GN 00603.020 D.3] §11
    opening = closing balance of previous month
    rows = ledger_entries(participant, month) ordered by date, ledger_ref
    FOR each row : running_balance = previous running_balance ± row.amount   (sign rule, J.1)
    RETURN {
        participant_id, month, opening,
        rows : [ date | ledger_ref | entry_type | paid_to / source | amount_in | amount_out
                 | collective share (if any) | receipt_no | running_balance ],
        closing = last running_balance,
        totals_by_entry_type,
        conserved_funds_elsewhere : TRANSFER_OUT balances still held (CDs, savings)   [POMS D.3.d]
    }

FUNCTION monthly_reconciliation(collective_account, month) :
    // Required part:  [POMS GN 00603.020 D.3.a]
    FOR each participant :
        stmt = this participant's deposits and interest on the monthly collective account statement
        ledg = DEPOSIT_SS + DEPOSIT_SSI + INTEREST entries in the ledger for month
        IF stmt != ledg → finding REVIEW_REQUIRED "D.3.a deposits/interest do not reconcile"
    // Additional control:  [DESIGN]  (FCC already has verify_1013_to_2150)
    IF statement ending balance != Σ participant closing balances held in this account
        → finding CRITICAL "collective account does not equal sum of beneficiary balances"
    RETURN { month, per_participant_results, aggregate_result,
             prepared_by, reviewed_by }      // reviewer ≠ preparer is RECOMMENDED (Compendium ch. 4), [DESIGN] here
```

---

## J.4 Annual report draft (supports the SSA-6234; does not replace it)

```text
FUNCTION annual_report_draft(participant, report_period) :
    // report_period = the 12-month period printed on SSA's form, NOT the calendar year.
    //   [POMS GN 00605.061] §5

    IF participant.has_dedicated_account :
        RETURN dedicated_account_report(participant, report_period)    // SSA-6233-BK instead
        // "Payees with dedicated accounts are excluded from the annual accounting selection criteria."
        //   [POMS GN 00605.001] §3

    IF payee.is_exempt :                                               // [REG] (b)
        RETURN records_only_notice                                     // records still kept and available, [REG] (c)
        // Organizations are never in (b)(1)–(4). For More Maitri this branch never runs.

    benefits_received     = Σ DEPOSIT_SS + DEPOSIT_SSI in report_period
    prior_conserved_funds = saved_end_of_period from the last filed report
    TAA_computed          = benefits_received + prior_conserved_funds   // [POMS GN 00605.061] §5
    TAA_printed           = value SSA printed on the form (entered by operator)
    IF TAA_printed entered AND TAA_printed != TAA_computed
        → finding REVIEW_REQUIRED "TAA differs from SSA's figure; explain before filing"

    used_food_housing = Σ EXPENDITURE where use_category = FOOD_HOUSING
                        − Σ REFUND linked to those expenditures                  // net  [DESIGN]
    used_other        = Σ EXPENDITURE where use_category = OTHER + Σ PNA_TRANSFER
                        − Σ REFUND linked to those expenditures                  // net  [DESIGN]
    fee_collected     = Σ FEE                                                     // [POMS GN 00605.065] §6 Q2B
    saved_end_of_period = closing balance on last day of report_period,
                          INCLUDING interest and conserved funds held elsewhere (CDs, savings)
                          // includes interest: form instructions  [UNVERIFIED]
                          // includes CDs: [POMS GN 00603.020 D.3.d] "reflect this CD as conserved funds"

    RETURN {
      label : "Reporting draft: supports the SSA-6234; the payee completes and signs the form",
      report_period,
      total_accountable_amount : { computed: TAA_computed, printed: TAA_printed },
      custody : residence(s) during report_period with dates          // [REG] (c)(1); §6 Q1; custody = "living with" §7
      decision_maker : who decided how funds were used or saved       // [REG] (c)(2); §6 Q2
      use_of_benefits : {                                             // [REG] (c)(3); §6 Q2
          food_and_housing : used_food_housing,                       // [INFERENCE] form bucket (SSA-623 Q3B equivalent)
          other            : used_other,                              // [INFERENCE] form bucket (SSA-623 Q3C equivalent)
          saved            : saved_end_of_period                      // SSA-623 Q3D equivalent, §8
      },
      fee : { collected: fee_collected > 0, amount: fee_collected,    // §6 Q2B
              max_authorized: MFA printed on form },                  // §5
      conserved_funds_holdings : [ { type, institution, title, amount } ]   // [REG] (c)(4); §6 Q3–4
      reconciliation : {                                              // [DESIGN]: the identity the form numbers must satisfy
          prior_conserved_funds + benefits_received + interest + refunds_not_netted
          − used_food_housing − used_other − fee_collected − returns_to_ssa
          = saved_end_of_period
      },
      screening_checks : J.5 results,
      unresolved_findings, evidence_index                             // [DESIGN]
    }
```

**Open design questions** (no SSA answer in the retrieved sources):

1. Whether the fee counts inside "use of benefits" totals or only in Q2B. The draft keeps it separate.
2. How the SSA-6234's questions are numbered and worded. GN 00605.065 says it is "similar" to the
   SSA-623 and lists Q1 custody, Q2 A–E use of benefits (2B = fee), Q3–4 conserved funds. The labels
   for food/housing and other are `[INFERENCE]` until checked against the actual form.
3. Whether refunds are netted against spending (chosen here) or shown separately, as Chunk 8 T-12 has it.
   The form has no refund line, so netting keeps the form arithmetic simple. T-12 needs to be
   reconciled with this choice.

---

## J.5 Screening checks (run before the payee files)

These reproduce how SSA screens a returned report, so problems are fixed before filing.

```text
FUNCTION screening_checks(draft, participant) :
    covered = used_food_housing + used_other + saved_end_of_period
    IF covered < COVERAGE_MIN × TAA_computed                            // [POMS GN 00605.070, .040] §8, §9
        → finding REVIEW_REQUIRED "less than 90% of TAA accounted for; SSA may require a face-to-face interview"

    IF participant.resides_in_institution
       AND ( used_other = 0
             OR (used_other < MIN(INSTITUTION_PERSONAL_MIN, TAA_computed)
                 AND used_other + saved_end_of_period < MIN(INSTITUTION_PERSONAL_MIN, TAA_computed)) )
       // SSA-623 3C rule: under $360 (zero not acceptable) unless 3C + 3D reach $360 or the TAA
        → finding REVIEW_REQUIRED "personal needs below $360; explain how personal needs were met"   // §8
        // [INFERENCE] the "other" bucket corresponds to 3C

    IF participant.program IN {SSI, CONCURRENT} AND saved_end_of_period >= SSI_CONSERVED_ALERT
        → finding ALERT "conserved funds ≥ $2,000; SSA will develop continuing SSI eligibility"     // §3, §8
        // ALERT only: SSA's own rule does not block spending

    IF saved_end_of_period > TITLING_REVIEW_THRESHOLD
        FOR each holding : IF title does not show beneficiary ownership and payee's fiduciary capacity
            → finding FAIL "account title does not meet GN 00603.010"                                 // §8 Q4, §10

    IF fee_collected > 0 AND (payee not authorized for fees OR fee_collected > max_authorized)
        → finding FAIL "fee exceeds SSA authorization"                                                // §5, §6

    // Additional SSA follow-up triggers (§8), reported as INFO:
    //   saved < 20% of TAA while TAA > $25,000; saved < 20% of prior CF while prior CF > $5,000;
    //   saved > $10,000 for Title II-only cases.
```

---

## J.6 What FCC must change to support this module

| Need | FCC today | Gap |
|---|---|---|
| Correct balance direction | `abs()` makes outgoing "reimbursement" items increase the balance | **Bug.** Apply the J.1 sign rule |
| Per-transaction ledger | Year-end totals per resident only | Build J.1 / J.3 |
| Whom paid, date, amount on each expenditure | Memo text stripped from client-safe output | Keep in the protected ledger; client-safe view can mask names |
| SS vs SSI deposits listed separately | Classified only as BENEFIT_RECEIPT | Record the program on each deposit |
| Interest allocation | All interest sent to review | Implement J.2 |
| Food/housing vs other | One RESIDENT_DISBURSEMENT class | Add `use_category` |
| Monthly reconciliation | `verify_1013_to_2150` (aggregate only) | Add the per-beneficiary deposit/interest check (J.3) |
| Fee tracking | None | Add FEE entries if More Maitri is authorized to charge fees (unknown) |
