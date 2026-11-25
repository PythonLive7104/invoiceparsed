"""Bank reconciliation (P2.7).

Reconciliation answers one question: did the money we think we paid actually
leave the account, once, for the right amount? The ways it fails are all
quiet, so these tests lean on them:

* importing the same statement twice silently doubling the account;
* two genuinely identical lines being collapsed into one;
* a date read month-first that moves a transaction by months;
* a suggestion nobody looked at counting as a reconciliation;
* an inbound refund reconciled as though it were the payment going out.

Every fixture runs on the **Pro** plan: payables is a Pro capability.
"""
import io
from decimal import Decimal

import pytest

from roles import ACCOUNTANT, VIEWER
from tests.conftest import auth_header, join_org, make_org, make_user, org_header


@pytest.fixture
def owner(app):
    return make_user(app, email="owner@example.com", plan="pro")


@pytest.fixture
def supplier(app, owner):
    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    with app.app_context():
        row = Supplier(
            organization_id=owner["organization_id"],
            name="Acme Supplies Ltd",
            match_key=match_key_for("Acme Supplies Ltd"),
            currency="NGN",
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "name": row.name}


def make_invoice(app, owner, *, total="1000.00", number="INV-001",
                 supplier_id=None, name="inv.pdf"):
    from documents import apply_headline_fields
    from extensions import db
    from invoice_schema import normalize
    from models import Extraction

    document = normalize({
        "vendor": {"name": "Acme Supplies Ltd"},
        "invoice_number": number, "invoice_date": "2026-11-01",
        "currency": "NGN",
        "line_items": [{"description": "Widget", "quantity": 1,
                        "unit_price": total, "amount": total}],
        "subtotal": total, "tax": 0, "total": total, "confidence": {},
    })
    with app.app_context():
        row = Extraction(
            organization_id=owner["organization_id"], user_id=owner["id"],
            doc_type="invoice", file_name=name, file_type="application/pdf",
            file_size=100, supplier_id=supplier_id, data="{}",
            status="completed",
        )
        apply_headline_fields(row, document)
        db.session.add(row)
        db.session.commit()
        return row.id


def record_payment(client, headers, eid, amount, **extra):
    body = {"amount": str(amount)}
    body.update(extra)
    response = client.post(f"/api/payments/invoices/{eid}", json=body,
                           headers=headers)
    assert response.status_code == 201, response.get_json()
    return response.get_json()["payments"][0]


CSV = """Date,Description,Reference,Debit,Credit,Balance
2026-11-05,BACS PAYMENT TO ACME SUPPLIES LTD,FT-9001,1000.00,,4000.00
2026-11-06,BANK CHARGES,,12.50,,3987.50
2026-11-07,REFUND FROM ACME,,,250.00,4237.50
"""


def upload_csv(client, headers, text=CSV, name="statement.csv"):
    return client.post(
        "/api/reconciliation/imports",
        data={"file": (io.BytesIO(text.encode("utf-8")), name)},
        headers=headers,
        content_type="multipart/form-data",
    )


def transactions(client, headers, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = "/api/reconciliation/transactions" + (f"?{query}" if query else "")
    return client.get(url, headers=headers).get_json()["transactions"]


# ─── Parsing ─────────────────────────────────────────────────────────────────
def test_separate_debit_and_credit_columns_are_read(app):
    with app.app_context():
        from reconciliation import rows_from_csv

        rows = rows_from_csv(CSV)
        assert len(rows) == 3
        assert rows[0]["debit"] == Decimal("1000.00")
        assert rows[0]["credit"] is None
        assert rows[2]["credit"] == Decimal("250.00")


def test_a_single_signed_amount_column_is_read(app):
    """Negative is money out, which is what every one-column export means."""
    with app.app_context():
        from reconciliation import rows_from_csv

        rows = rows_from_csv(
            "Date,Narrative,Amount\n"
            "2026-11-05,Payment to Acme,-1000.00\n"
            "2026-11-06,Interest,12.50\n"
        )
        assert rows[0]["debit"] == Decimal("1000.00")
        assert rows[0]["credit"] is None
        assert rows[1]["credit"] == Decimal("12.50")


def test_day_first_dates_are_not_read_month_first(app):
    """A date read the wrong way round moves a transaction by months, which
    is far worse than failing to read it."""
    with app.app_context():
        from reconciliation import rows_from_csv

        rows = rows_from_csv(
            "Date,Details,Debit\n05/11/2026,Payment,100.00\n"
        )
        assert rows[0]["date"] == "2026-11-05"


def test_alternative_column_names_are_recognised(app):
    with app.app_context():
        from reconciliation import rows_from_csv

        rows = rows_from_csv(
            "Value Date,Particulars,Withdrawals,Deposits,Running Balance\n"
            "2026-11-05,Paid Acme,1000.00,,4000.00\n"
        )
        assert rows[0]["date"] == "2026-11-05"
        assert rows[0]["debit"] == Decimal("1000.00")
        assert "Acme" in rows[0]["description"]


def test_preamble_rows_above_the_header_are_skipped(app):
    """Plenty of exports put the account details above the table."""
    with app.app_context():
        from reconciliation import rows_from_csv

        rows = rows_from_csv(
            "Acme Bank plc\nAccount 12345678\n\n"
            "Date,Description,Debit\n2026-11-05,Payment,100.00\n"
        )
        assert len(rows) == 1


def test_a_file_with_no_recognisable_columns_is_refused(app):
    with app.app_context():
        from reconciliation import StatementImportError, rows_from_csv

        with pytest.raises(StatementImportError) as caught:
            rows_from_csv("foo,bar\n1,2\n")
        assert caught.value.code == "NO_HEADER"


# ─── Importing ───────────────────────────────────────────────────────────────
def test_importing_a_csv_creates_transactions(app, client, owner):
    headers = auth_header(app, owner)
    response = upload_csv(client, headers)
    assert response.status_code == 201
    body = response.get_json()
    assert body["imported"] == 3
    assert body["duplicates"] == 0
    assert len(transactions(client, headers)) == 3


def test_importing_the_same_statement_twice_is_harmless(app, client, owner):
    """The failure this prevents: an account silently doubled."""
    headers = auth_header(app, owner)
    upload_csv(client, headers)
    again = upload_csv(client, headers).get_json()
    assert again["imported"] == 0
    assert again["duplicates"] == 3
    assert len(transactions(client, headers)) == 3


def test_two_genuinely_identical_lines_are_both_kept(app, client, owner):
    """A bank really can issue two identical lines in a day — two card
    payments of the same amount to the same shop. Collapsing them would lose
    one."""
    headers = auth_header(app, owner)
    text = ("Date,Description,Debit\n"
            "2026-11-05,COFFEE SHOP,4.50\n"
            "2026-11-05,COFFEE SHOP,4.50\n")
    body = upload_csv(client, headers, text).get_json()
    assert body["imported"] == 2
    assert body["duplicates"] == 0


def test_a_statement_already_extracted_is_imported_without_re_parsing(
    app, client, owner
):
    """The reuse the roadmap asks for: statement_schema has read this
    document once, and a second parser would eventually disagree with it."""
    from documents import apply_headline_fields
    from extensions import db
    from models import Extraction
    from statement_schema import normalize

    document = normalize({
        "bank_name": "Acme Bank", "account_number": "12345678",
        "currency": "NGN", "period_start": "2026-11-01",
        "period_end": "2026-11-30",
        "opening_balance": "5000.00", "closing_balance": "3987.50",
        "transactions": [
            {"date": "2026-11-05", "description": "PAYMENT TO ACME",
             "debit": "1000.00", "credit": None, "balance": "4000.00",
             "reference": "FT-9001"},
            {"date": "2026-11-06", "description": "BANK CHARGES",
             "debit": "12.50", "credit": None, "balance": "3987.50",
             "reference": None},
        ],
        "confidence": {},
    })
    with app.app_context():
        row = Extraction(
            organization_id=owner["organization_id"], user_id=owner["id"],
            doc_type="statement", file_name="nov.pdf",
            file_type="application/pdf", file_size=100, data="{}",
            status="completed",
        )
        apply_headline_fields(row, document)
        db.session.add(row)
        db.session.commit()
        eid = row.id

    headers = auth_header(app, owner)
    response = client.post("/api/reconciliation/imports",
                           json={"extractionId": eid}, headers=headers)
    assert response.status_code == 201
    body = response.get_json()
    assert body["imported"] == 2
    assert body["import"]["source"] == "extraction"
    assert body["import"]["bankName"] == "Acme Bank"
    assert body["import"]["closingBalance"] == "3987.50"


def test_an_import_can_be_undone(app, client, owner):
    headers = auth_header(app, owner)
    batch = upload_csv(client, headers).get_json()["import"]
    removed = client.delete(f"/api/reconciliation/imports/{batch['id']}",
                            headers=headers)
    assert removed.status_code == 200
    assert transactions(client, headers) == []


def test_an_import_with_reconciled_lines_cannot_be_undone(
    app, client, owner, supplier
):
    """Those confirmations are decisions somebody made; removing the evidence
    under them would leave payments reconciled against nothing."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", reference="FT-9001",
                   paidOn="2026-11-05")
    batch = upload_csv(client, headers).get_json()["import"]

    rows = transactions(client, headers)
    matched = next(r for r in rows if r["match"])
    client.post(f"/api/reconciliation/matches/{matched['match']['id']}/confirm",
                headers=headers)

    blocked = client.delete(f"/api/reconciliation/imports/{batch['id']}",
                            headers=headers)
    assert blocked.status_code == 409
    assert blocked.get_json()["code"] == "HAS_CONFIRMED_MATCHES"


def test_a_file_that_is_not_a_statement_is_refused(app, client, owner):
    headers = auth_header(app, owner)
    response = upload_csv(client, headers, "hello\nworld\n", name="notes.csv")
    assert response.status_code == 400


def test_an_unsupported_file_type_is_refused(app, client, owner):
    headers = auth_header(app, owner)
    response = client.post(
        "/api/reconciliation/imports",
        data={"file": (io.BytesIO(b"%PDF-1.4"), "statement.pdf")},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["code"] == "BAD_TYPE"


# ─── Matching ────────────────────────────────────────────────────────────────
def test_a_matching_reference_is_the_strongest_signal(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", reference="FT-9001",
                   paidOn="2026-11-05")
    upload_csv(client, headers)

    rows = transactions(client, headers)
    matched = next(r for r in rows if r["match"])
    assert matched["match"]["method"] == "reference"
    assert matched["match"]["score"] == 1.0
    assert matched["match"]["status"] == "suggested"


def test_amount_and_date_match_when_there_is_no_reference(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", paidOn="2026-11-04")
    upload_csv(client, headers, "Date,Description,Debit\n"
                                "2026-11-05,PAYMENT,1000.00\n")

    rows = transactions(client, headers)
    assert rows[0]["match"]["method"] == "amount_date"


def test_a_payment_far_from_the_bank_date_is_not_matched_on_date(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", paidOn="2026-09-01")
    upload_csv(client, headers, "Date,Description,Debit\n"
                                "2026-11-05,SOMETHING,1000.00\n")

    rows = transactions(client, headers)
    # Still a candidate on amount, but not presented as a date match.
    assert rows[0]["match"]["method"] != "amount_date"


def test_a_suggestion_is_not_a_reconciliation(app, client, owner, supplier):
    """A plausible guess nobody checked is not evidence that money moved."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", reference="FT-9001",
                   paidOn="2026-11-05")
    upload_csv(client, headers)

    rows = transactions(client, headers)
    matched = next(r for r in rows if r["match"])
    assert matched["status"] == "unmatched"

    summary = client.get("/api/reconciliation/summary",
                         headers=headers).get_json()
    assert summary["byStatus"]["matched"] == 0
    assert summary["awaitingConfirmation"] == 1


def test_confirming_a_suggestion_reconciles_the_line(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", reference="FT-9001",
                   paidOn="2026-11-05")
    upload_csv(client, headers)

    rows = transactions(client, headers)
    match_id = next(r for r in rows if r["match"])["match"]["id"]
    confirmed = client.post(
        f"/api/reconciliation/matches/{match_id}/confirm", headers=headers
    )
    assert confirmed.status_code == 200
    assert confirmed.get_json()["match"]["status"] == "confirmed"

    summary = client.get("/api/reconciliation/summary",
                         headers=headers).get_json()
    assert summary["byStatus"]["matched"] == 1
    assert summary["unreconciledPayments"] == 0


def test_an_inbound_credit_is_never_matched_to_a_payment_out(
    app, client, owner, supplier
):
    """A refund reconciled as though it were the payment itself would make
    the account balance and the ledger both wrong, in opposite directions."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, total="250.00", supplier_id=supplier["id"])
    record_payment(client, headers, eid, "250.00", paidOn="2026-11-07")
    upload_csv(client, headers)

    rows = transactions(client, headers)
    refund = next(r for r in rows if r["credit"] == "250.00")
    assert refund["match"] is None


def test_a_line_can_be_matched_by_hand(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    payment = record_payment(client, headers, eid, "1000.00",
                             paidOn="2026-01-01")
    upload_csv(client, headers, "Date,Description,Debit\n"
                                "2026-11-05,MYSTERY PAYMENT,1000.00\n")

    txn = transactions(client, headers)[0]
    done = client.post(f"/api/reconciliation/transactions/{txn['id']}/match",
                       json={"paymentId": payment["id"], "note": "Checked."},
                       headers=headers)
    assert done.status_code == 200
    body = done.get_json()["match"]
    assert body["status"] == "confirmed"
    assert body["method"] == "manual"


def test_one_payment_cannot_reconcile_two_bank_lines(
    app, client, owner, supplier
):
    """Otherwise a duplicate bank payment reconciles against the single
    payment record and the duplicate disappears."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    payment = record_payment(client, headers, eid, "1000.00",
                             paidOn="2026-11-05")
    upload_csv(client, headers, "Date,Description,Debit\n"
                                "2026-11-05,PAYMENT ONE,1000.00\n"
                                "2026-11-06,PAYMENT TWO,1000.00\n")

    rows = transactions(client, headers)
    first = client.post(
        f"/api/reconciliation/transactions/{rows[0]['id']}/match",
        json={"paymentId": payment["id"]}, headers=headers)
    assert first.status_code == 200

    second = client.post(
        f"/api/reconciliation/transactions/{rows[1]['id']}/match",
        json={"paymentId": payment["id"]}, headers=headers)
    assert second.status_code == 409
    assert second.get_json()["code"] == "PAYMENT_ALREADY_MATCHED"


def test_a_voided_payment_cannot_be_reconciled(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    payment = record_payment(client, headers, eid, "1000.00")
    client.post(f"/api/payments/{payment['id']}/void",
                json={"reason": "duplicate"}, headers=headers)
    upload_csv(client, headers, "Date,Description,Debit\n"
                                "2026-11-05,PAYMENT,1000.00\n")

    txn = transactions(client, headers)[0]
    response = client.post(
        f"/api/reconciliation/transactions/{txn['id']}/match",
        json={"paymentId": payment["id"]}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "PAYMENT_VOID"


def test_unmatching_returns_the_line_to_the_unmatched_list(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", reference="FT-9001",
                   paidOn="2026-11-05")
    upload_csv(client, headers)

    rows = transactions(client, headers)
    match_id = next(r for r in rows if r["match"])["match"]["id"]
    client.post(f"/api/reconciliation/matches/{match_id}/confirm",
                headers=headers)
    removed = client.delete(f"/api/reconciliation/matches/{match_id}",
                            headers=headers)
    assert removed.status_code == 200

    summary = client.get("/api/reconciliation/summary",
                         headers=headers).get_json()
    assert summary["byStatus"]["matched"] == 0
    assert summary["unreconciledPayments"] == 1


def test_a_short_payment_records_the_difference(app, client, owner, supplier):
    """A part-settled line should be visible as a figure, not a feeling."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    payment = record_payment(client, headers, eid, "950.00",
                             paidOn="2026-11-05")
    upload_csv(client, headers, "Date,Description,Debit\n"
                                "2026-11-05,PAYMENT,1000.00\n")

    txn = transactions(client, headers)[0]
    body = client.post(
        f"/api/reconciliation/transactions/{txn['id']}/match",
        json={"paymentId": payment["id"]}, headers=headers,
    ).get_json()["match"]
    assert body["difference"] == "50.00"


def test_candidates_are_offered_strongest_first(app, client, owner, supplier):
    headers = auth_header(app, owner)
    first = make_invoice(app, owner, number="A", name="a.pdf",
                         supplier_id=supplier["id"])
    second = make_invoice(app, owner, number="B", name="b.pdf",
                          supplier_id=supplier["id"])
    record_payment(client, headers, first, "1000.00", paidOn="2020-01-01")
    exact = record_payment(client, headers, second, "1000.00",
                           reference="FT-9001", paidOn="2026-11-05")
    upload_csv(client, headers)

    txn = next(r for r in transactions(client, headers)
               if r["reference"] == "FT-9001")
    body = client.get(
        f"/api/reconciliation/transactions/{txn['id']}/candidates",
        headers=headers,
    ).get_json()
    assert body["candidates"][0]["paymentId"] == exact["id"]
    assert body["candidates"][0]["method"] == "reference"


# ─── Ignoring ────────────────────────────────────────────────────────────────
def test_a_line_can_be_set_aside_with_a_reason(app, client, owner):
    """Bank charges will never match a supplier payment. Keeping them in
    "unmatched" turns the list into a wall people stop reading."""
    headers = auth_header(app, owner)
    upload_csv(client, headers)
    charges = next(r for r in transactions(client, headers)
                   if "CHARGES" in (r["description"] or ""))

    done = client.post(
        f"/api/reconciliation/transactions/{charges['id']}/ignore",
        json={"reason": "Bank charges — posted to overheads."},
        headers=headers,
    )
    assert done.status_code == 200
    assert done.get_json()["transaction"]["status"] == "ignored"

    summary = client.get("/api/reconciliation/summary",
                         headers=headers).get_json()
    assert summary["byStatus"]["ignored"] == 1


def test_ignoring_needs_a_reason(app, client, owner):
    """Otherwise "ignored" becomes a way to hide a problem."""
    headers = auth_header(app, owner)
    upload_csv(client, headers)
    txn = transactions(client, headers)[0]
    response = client.post(
        f"/api/reconciliation/transactions/{txn['id']}/ignore",
        json={"reason": "  "}, headers=headers)
    assert response.status_code == 400
    assert response.get_json()["code"] == "REASON_REQUIRED"


def test_a_reconciled_line_cannot_be_ignored(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00", reference="FT-9001",
                   paidOn="2026-11-05")
    upload_csv(client, headers)
    rows = transactions(client, headers)
    matched = next(r for r in rows if r["match"])
    client.post(f"/api/reconciliation/matches/{matched['match']['id']}/confirm",
                headers=headers)

    response = client.post(
        f"/api/reconciliation/transactions/{matched['id']}/ignore",
        json={"reason": "x"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "ALREADY_MATCHED"


def test_an_ignored_line_can_be_brought_back(app, client, owner):
    headers = auth_header(app, owner)
    upload_csv(client, headers)
    txn = transactions(client, headers)[0]
    client.post(f"/api/reconciliation/transactions/{txn['id']}/ignore",
                json={"reason": "mistake"}, headers=headers)
    back = client.post(
        f"/api/reconciliation/transactions/{txn['id']}/unignore",
        headers=headers)
    assert back.status_code == 200
    assert back.get_json()["transaction"]["status"] == "unmatched"


# ─── The summary ─────────────────────────────────────────────────────────────
def test_the_summary_counts_payments_the_bank_has_not_shown_leaving(
    app, client, owner, supplier
):
    """Money the organization believes it paid and the bank has not shown
    going out — the figure reconciliation exists to surface."""
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, supplier_id=supplier["id"])
    record_payment(client, headers, eid, "1000.00")

    summary = client.get("/api/reconciliation/summary",
                         headers=headers).get_json()
    assert summary["unreconciledPayments"] == 1


# ─── Permissions, tenancy, paywall ───────────────────────────────────────────
def test_an_accountant_can_reconcile(app, client, owner):
    org = make_org(app, owner, name="Acme", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, org, clerk, ACCOUNTANT)
    headers = {**auth_header(app, clerk), **org_header(app, clerk, org)}
    assert upload_csv(client, headers).status_code == 201


def test_a_viewer_cannot_import_or_match(app, client, owner):
    org = make_org(app, owner, name="Watch Co", plan="pro")
    watcher = make_user(app, email="watcher@example.com", plan="pro")
    join_org(app, org, watcher, VIEWER)
    headers = {**auth_header(app, watcher), **org_header(app, watcher, org)}
    assert client.get("/api/reconciliation/summary",
                      headers=headers).status_code == 200
    assert upload_csv(client, headers).status_code == 403


def test_transactions_never_cross_an_organization_boundary(app, client, owner):
    headers = auth_header(app, owner)
    upload_csv(client, headers)

    stranger = make_user(app, email="stranger@example.com", plan="pro")
    stranger_headers = auth_header(app, stranger)
    assert transactions(client, stranger_headers) == []
    assert client.get("/api/reconciliation/imports",
                      headers=stranger_headers).get_json()["imports"] == []


def test_the_same_statement_in_two_organizations_is_not_a_duplicate(
    app, client, owner
):
    """Fingerprints are scoped per organization, or one tenant's import would
    suppress another's."""
    headers = auth_header(app, owner)
    assert upload_csv(client, headers).get_json()["imported"] == 3

    other = make_user(app, email="other@example.com", plan="pro")
    other_body = upload_csv(client, auth_header(app, other)).get_json()
    assert other_body["imported"] == 3
    assert other_body["duplicates"] == 0


def test_reconciliation_is_behind_the_payables_paywall(app, client):
    free = make_user(app, email="free@example.com", plan="free")
    response = client.get("/api/reconciliation/summary",
                          headers=auth_header(app, free))
    assert response.status_code == 402
    assert response.get_json()["capability"] == "payables"
