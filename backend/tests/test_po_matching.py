"""Invoice-to-PO matching (P2.3).

Weighted toward the errors that cost money rather than the happy path. Four
things these tests care about more than anything else:

* an invoice is never linked to an order on weak evidence;
* over-invoicing is caught across several invoices, not just one;
* a tolerance absorbs rounding and nothing larger;
* a blocking finding stays blocking until a named person accepts it in writing.

The arithmetic assertions use exact decimal strings throughout. A test that
accepted "about right" would pass against the float bug this whole codebase is
arranged to prevent.

Every fixture here runs on the **Pro** plan, because suppliers, purchase
orders and matching are a Pro capability (`plans.PAYABLES`). On a free or
starter plan every endpoint in this module answers 402, which is what
tests/test_payables_plan.py checks - so do not drop the `plan="pro"`
arguments below.
"""
import io
from decimal import Decimal

import pytest

from invoice_schema import normalize
from roles import ACCOUNTANT, APPROVER, FINANCE_MANAGER, PROCUREMENT, VIEWER
from tests.conftest import auth_header, join_org, make_org, make_user, org_header


# ─── Fixtures and helpers ────────────────────────────────────────────────────
@pytest.fixture
def owner(app):
    return make_user(app, email="owner@example.com", plan="pro")


@pytest.fixture
def supplier(app, owner):
    return make_supplier(app, owner["organization_id"], name="Acme Supplies Ltd",
                         currency="NGN")


def make_supplier(app, organization_id, name="Acme Supplies Ltd", key=None,
                  currency="NGN", status="active"):
    """A supplier whose match_key is built the way production builds it.

    `suppliers.match_key_for` drops company-form suffixes, so a key of
    name.lower() would leave "acme supplies ltd" here while an uploaded
    invoice looked up "acme supplies" - and the upload would quietly create
    a SECOND supplier rather than find this one.
    """
    from extensions import db
    from models import Supplier
    from suppliers import match_key_for

    with app.app_context():
        row = Supplier(
            organization_id=organization_id,
            name=name,
            match_key=key or match_key_for(name),
            currency=currency,
            status=status,
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "name": row.name}


PO_LINE = {"description": "Hydraulic hose", "sku": "HH-1003", "unit": "each",
           "quantity": "10", "unitPrice": "100.00", "taxRate": "0"}


def create_po(client, headers, supplier_id, lines=None, approve=True, **extra):
    """An approved order, which is the state an invoice normally arrives against."""
    body = {"supplierId": supplier_id, "lines": lines if lines is not None else [PO_LINE]}
    body.update(extra)
    response = client.post("/api/purchase-orders", json=body, headers=headers)
    assert response.status_code == 201, response.get_json()
    po = response.get_json()["purchaseOrder"]
    if approve:
        client.post(f"/api/purchase-orders/{po['id']}/submit", headers=headers)
        approved = client.post(f"/api/purchase-orders/{po['id']}/approve",
                               headers=headers)
        assert approved.status_code == 200, approved.get_json()
        po = approved.get_json()["purchaseOrder"]
    return po


INVOICE_LINE = {"description": "Hydraulic hose", "product_name": "HH-1003",
                "quantity": 10, "unit_price": 100, "discount": None,
                "tax_rate": 0, "amount": 1000}


def invoice_doc(*, reference="PO-0001", lines=None, total="1000.00",
                currency="NGN", vendor="Acme Supplies Ltd", number="INV-001"):
    return normalize({
        "vendor": {"name": vendor, "tax_id": None, "address": None,
                   "email": None, "phone": None},
        "customer": {"name": "Us Ltd"},
        "invoice_number": number,
        "invoice_date": "2026-11-20",
        "due_date": "2026-12-20",
        "currency": currency,
        "purchase_order_reference": reference,
        "line_items": lines if lines is not None else [dict(INVOICE_LINE)],
        "subtotal": total,
        "tax": 0,
        "total": total,
        "confidence": {},
    })


def make_invoice(app, owner, document, *, supplier_id=None, name="inv.pdf"):
    """An extraction row written directly, so a test can set up a situation
    without going through the upload endpoint and its stubbed extractor."""
    from documents import apply_headline_fields
    from extensions import db
    from models import Extraction

    with app.app_context():
        row = Extraction(
            organization_id=owner["organization_id"],
            user_id=owner["id"],
            doc_type="invoice",
            file_name=name,
            file_type="application/pdf",
            file_size=1024,
            supplier_id=supplier_id,
            data="{}",
            status="completed",
        )
        apply_headline_fields(row, document)
        db.session.add(row)
        db.session.commit()
        return row.id


def upload(client, app, monkeypatch, headers, document, name="inv.pdf",
           content=b"bytes"):
    """Go through the real upload pipeline, with the extractor stubbed."""
    import routes.extract_routes as er
    monkeypatch.setattr(
        "openai_service.extract_document",
                        lambda pages, doc_type="invoice": document)
    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(content), name)},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def codes(comparison):
    return [finding["code"] for finding in comparison["findings"]]


def by_code(comparison, code):
    return next(f for f in comparison["findings"] if f["code"] == code)


def link(client, headers, eid, po_id):
    return client.post(f"/api/matching/invoices/{eid}/link",
                       json={"purchaseOrderId": po_id}, headers=headers)


# ─── Tolerance arithmetic ────────────────────────────────────────────────────
def test_an_exact_figure_is_within_tolerance_even_with_no_bounds_set(app):
    with app.app_context():
        from po_matching import within_tolerance

        assert within_tolerance("100.00", "100.00", percent=0, amount=0)


def test_an_absolute_bound_absorbs_a_rounding_cent_and_nothing_more(app):
    with app.app_context():
        from po_matching import within_tolerance

        assert within_tolerance("100.00", "100.02", percent=0, amount="0.02")
        assert not within_tolerance("100.00", "100.03", percent=0, amount="0.02")


def test_a_percentage_bound_scales_with_the_figure(app):
    with app.app_context():
        from po_matching import within_tolerance

        assert within_tolerance("1000.00", "1010.00", percent="1", amount=0)
        assert not within_tolerance("1000.00", "1011.00", percent="1", amount=0)


def test_either_bound_passing_is_enough(app):
    """The documented reason both exist: a percentage is meaningless on a small
    figure and an absolute amount is meaningless on a large one, so an
    organization sets whichever describes its tolerance and the other stays at
    zero without disabling the first."""
    with app.app_context():
        from po_matching import within_tolerance

        # Inside the absolute bound, far outside the percentage.
        assert within_tolerance("1.00", "1.02", percent="0.1", amount="0.02")
        # Inside the percentage, far outside the absolute bound.
        assert within_tolerance("1000000.00", "1005000.00",
                                percent="1", amount="0.02")


def test_tolerance_is_symmetric_about_the_expected_figure(app):
    with app.app_context():
        from po_matching import within_tolerance

        assert within_tolerance("100.00", "99.98", percent=0, amount="0.02")
        assert within_tolerance("100.00", "100.02", percent=0, amount="0.02")


def test_a_negative_bound_is_not_treated_as_a_tolerance(app):
    """Guards the API's own validation: even if a negative bound reached the
    engine it must not widen anything."""
    with app.app_context():
        from po_matching import within_tolerance

        assert not within_tolerance("100.00", "100.50", percent="-50",
                                    amount="-10")


# ─── Line pairing ────────────────────────────────────────────────────────────
def test_normalize_item_keeps_words_a_supplier_name_would_drop(app):
    """Separate from duplicates.normalize_supplier on purpose: "Ltd" is noise
    in a business name and meaningful in a product description."""
    with app.app_context():
        from duplicates import normalize_supplier
        from po_matching import normalize_item

        assert normalize_item("Hose, 1in x 3m (Ltd ed.)") == "hose 1in x 3m ltd ed"
        assert normalize_supplier("Acme Ltd") == "acme"
        assert normalize_item("Acme Ltd") == "acme ltd"


def _fake_po_line(line_no, description, sku=None):
    class Line:
        pass

    line = Line()
    line.id = f"line-{line_no}"
    line.line_no = line_no
    line.description = description
    line.sku = sku
    line.quantity = Decimal("1")
    line.unit_price = Decimal("1")
    line.tax_rate = Decimal("0")
    return line


def test_lines_pair_on_an_exact_sku(app):
    with app.app_context():
        from po_matching import BY_SKU, pair_lines

        pairs = pair_lines(
            [{"description": "Completely different words", "product_name": "HH-1003"}],
            [_fake_po_line(1, "Hydraulic hose assembly", "HH-1003")],
        )
        assert pairs[0]["poLine"].id == "line-1"
        assert pairs[0]["matchedBy"] == BY_SKU


def test_lines_pair_on_a_sku_written_inside_the_description(app):
    """What suppliers actually do: the order says HH-1003, the invoice says
    "Hydraulic hose HH-1003, 1in x 3m"."""
    with app.app_context():
        from po_matching import BY_SKU, pair_lines

        pairs = pair_lines(
            [{"description": "Hydraulic hose HH-1003, 1in x 3m",
              "product_name": None}],
            [_fake_po_line(1, "Hose", "HH-1003")],
        )
        assert pairs[0]["poLine"] is not None
        assert pairs[0]["matchedBy"] == BY_SKU


def test_lines_pair_on_description_containment_and_token_overlap(app):
    with app.app_context():
        from po_matching import pair_lines

        pairs = pair_lines(
            [{"description": "Marine grease, lithium complex, 18kg pail",
              "product_name": None},
             {"description": "grease lithium marine", "product_name": None}],
            [_fake_po_line(1, "Marine grease lithium complex")],
        )
        # Both resemble the order line; exactly one may have it.
        assert sum(1 for pair in pairs if pair["poLine"] is not None) == 1


def test_unrelated_lines_do_not_pair(app):
    """The failure that matters: a wrongly paired line compares two unrelated
    prices and reports a discrepancy nobody can explain."""
    with app.app_context():
        from po_matching import pair_lines

        pairs = pair_lines(
            [{"description": "Office chair, mesh back", "product_name": "CHR-1"}],
            [_fake_po_line(1, "Hydraulic hose assembly", "HH-1003")],
        )
        assert pairs[0]["poLine"] is None
        assert pairs[0]["matchedBy"] is None


def test_lines_do_not_pair_on_filler_words_alone(app):
    with app.app_context():
        from po_matching import pair_lines

        pairs = pair_lines(
            [{"description": "a box of the red ones", "product_name": None}],
            [_fake_po_line(1, "a box of the blue ones")],
        )
        # Nearly every token is shared, but "box", "the" and "ones" are not
        # evidence that these are the same product.
        assert pairs[0]["poLine"] is None or pairs[0]["score"] < 0.8


def test_one_order_line_is_claimed_by_at_most_one_invoice_line(app):
    with app.app_context():
        from po_matching import pair_lines

        pairs = pair_lines(
            [{"description": "Hydraulic hose", "product_name": "HH-1003"},
             {"description": "Hydraulic hose", "product_name": "HH-1003"}],
            [_fake_po_line(1, "Hydraulic hose", "HH-1003")],
        )
        claimed = [pair for pair in pairs if pair["poLine"] is not None]
        assert len(claimed) == 1


def test_pairing_is_deterministic(app):
    """Pure and deterministic is what lets quantity_invoiced be a cache rather
    than a running total."""
    with app.app_context():
        from po_matching import pair_lines

        invoice_lines = [
            {"description": "Hydraulic hose", "product_name": "HH-1003"},
            {"description": "Stainless bolts M16", "product_name": "BLT-1680"},
            {"description": "Marine grease 18kg", "product_name": None},
        ]
        po_lines = [
            _fake_po_line(1, "Marine grease, lithium complex, 18kg pail"),
            _fake_po_line(2, "Stainless bolts M16 x 80", "BLT-1680"),
            _fake_po_line(3, "Hydraulic hose assembly", "HH-1003"),
        ]
        first = [
            (p["index"], p["poLine"].id if p["poLine"] else None)
            for p in pair_lines(invoice_lines, po_lines)
        ]
        for _ in range(5):
            again = [
                (p["index"], p["poLine"].id if p["poLine"] else None)
                for p in pair_lines(invoice_lines, po_lines)
            ]
            assert again == first
        assert first == [(0, "line-3"), (1, "line-2"), (2, "line-1")]


def test_a_sku_match_outranks_a_description_match(app):
    """Evidence is ordered. The SKU is the identifier; the description is prose."""
    with app.app_context():
        from po_matching import pair_lines

        pairs = pair_lines(
            [{"description": "Hydraulic hose assembly", "product_name": "HH-1003"}],
            [_fake_po_line(1, "Hydraulic hose assembly", "OTHER-SKU"),
             _fake_po_line(2, "Something else entirely", "HH-1003")],
        )
        assert pairs[0]["poLine"].id == "line-2"


# ─── Settings ────────────────────────────────────────────────────────────────
def test_settings_default_to_rounding_only_on_price_and_total(app, client, owner):
    """The defaults are a position, not a placeholder: two cents of rounding on
    a price or a total, and exact on quantity, because shipping more than was
    ordered is a commercial event someone should see."""
    response = client.get("/api/matching/settings", headers=auth_header(app, owner))
    assert response.status_code == 200
    settings = response.get_json()["settings"]
    assert settings["priceToleranceAmount"] == "0.02"
    assert settings["totalToleranceAmount"] == "0.02"
    assert settings["quantityToleranceAmount"] == "0.00"
    assert settings["priceTolerancePercent"] == "0.00"
    assert settings["requirePoReference"] is False
    assert settings["blockUnapprovedPo"] is True
    assert settings["autoConfirmExact"] is True


def test_reading_settings_twice_does_not_create_two_rows(app, client, owner):
    headers = auth_header(app, owner)
    client.get("/api/matching/settings", headers=headers)
    client.get("/api/matching/settings", headers=headers)
    with app.app_context():
        from models import MatchingSettings

        assert MatchingSettings.query.filter_by(
            organization_id=owner["organization_id"]
        ).count() == 1


def test_tolerances_round_trip_exactly(app, client, owner):
    response = client.put(
        "/api/matching/settings",
        json={"priceTolerancePercent": "2.5", "priceToleranceAmount": "1.5000",
              "quantityTolerancePercent": "0.0001"},
        headers=auth_header(app, owner),
    )
    assert response.status_code == 200
    settings = response.get_json()["settings"]
    assert settings["priceTolerancePercent"] == "2.50"
    assert settings["quantityTolerancePercent"] == "0.00"  # 0.0001 at 2dp
    with app.app_context():
        from models import MatchingSettings

        row = MatchingSettings.query.filter_by(
            organization_id=owner["organization_id"]
        ).first()
        # The stored value keeps the 4 places the column holds, even where the
        # 2dp JSON rendering cannot show them.
        assert row.quantity_tolerance_percent == Decimal("0.0001")
        assert row.price_tolerance_amount == Decimal("1.5000")


def test_a_negative_tolerance_is_refused(app, client, owner):
    response = client.put("/api/matching/settings",
                          json={"priceToleranceAmount": "-5"},
                          headers=auth_header(app, owner))
    assert response.status_code == 400
    assert "priceToleranceAmount" in response.get_json()["fields"]


def test_a_percentage_over_one_hundred_is_refused(app, client, owner):
    """"Within 150% of the agreed price" is not a check."""
    response = client.put("/api/matching/settings",
                          json={"priceTolerancePercent": "150"},
                          headers=auth_header(app, owner))
    assert response.status_code == 400


def test_an_unparseable_tolerance_is_refused_rather_than_zeroed(app, client, owner):
    response = client.put("/api/matching/settings",
                          json={"priceToleranceAmount": "about a fiver"},
                          headers=auth_header(app, owner))
    assert response.status_code == 400
    with app.app_context():
        from models import MatchingSettings

        row = MatchingSettings.query.filter_by(
            organization_id=owner["organization_id"]
        ).first()
        assert row is None or row.price_tolerance_amount == Decimal("0.0200")


def test_changing_tolerances_needs_the_admin_gate_not_the_invoice_gate(
    app, client, owner
):
    """Widening a tolerance is how you switch the control off, so the people
    who process invoices all day cannot do it."""
    org = make_org(app, owner, name="Acme", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, org, clerk, ACCOUNTANT)
    headers = {**auth_header(app, clerk), **org_header(app, clerk, org)}

    assert client.get("/api/matching/settings", headers=headers).status_code == 200
    blocked = client.put("/api/matching/settings",
                         json={"priceTolerancePercent": "50"}, headers=headers)
    assert blocked.status_code == 403


def test_a_viewer_cannot_even_read_the_settings_of_another_organization(
    app, client, owner
):
    org = make_org(app, owner, name="Acme", plan="pro")
    outsider = make_user(app, email="outsider@example.com", plan="pro")
    response = client.get("/api/matching/settings",
                          headers={**auth_header(app, outsider),
                                   **{"X-Organization-Id": org["id"]}})
    assert response.status_code in (403, 404)


# ─── Candidates ──────────────────────────────────────────────────────────────
def test_an_exact_po_number_is_found(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])

    response = client.get(f"/api/matching/invoices/{eid}/candidates", headers=headers)
    assert response.status_code == 200
    found = response.get_json()["candidates"]
    assert found[0]["poNumber"] == po["poNumber"]
    assert found[0]["method"] == "po_number"
    assert found[0]["score"] == 1.0


def test_a_po_number_written_differently_still_reaches_the_order(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    assert po["poNumber"] == "PO-0001"
    eid = make_invoice(app, owner, invoice_doc(reference="po 0001"),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    assert [entry["poNumber"] for entry in found] == ["PO-0001"]


def test_an_unpadded_po_number_is_suggested_but_can_never_confirm_itself(
    app, client, owner, supplier
):
    """"PO 1" for PO-0001 is how people write these down, and it is genuinely
    ambiguous, so it scores below the auto-confirm threshold."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference="PO 1"),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    assert found[0]["poNumber"] == "PO-0001"
    with app.app_context():
        from po_matching import AUTO_CONFIRM_SCORE

        assert found[0]["score"] < AUTO_CONFIRM_SCORE


def test_a_nearby_number_is_not_mistaken_for_the_order(app, client, owner, supplier):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])          # PO-0001
    eid = make_invoice(app, owner, invoice_doc(reference="PO-0010"),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    # And emphatically NOT rescued by the supplier-and-amount fallback,
    # even though PO-0001 happens to be for exactly this amount. The
    # invoice named an order; offering a different one would paper over a
    # finding that needs a person.
    assert found == []


def test_the_requisition_reference_on_the_order_is_also_matched(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], reference="REQ-2026-0188")
    eid = make_invoice(app, owner, invoice_doc(reference="REQ-2026-0188"),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    assert found[0]["method"] == "po_reference"


def test_with_no_reference_an_open_order_for_the_same_amount_is_suggested(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=None),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    assert found[0]["method"] == "supplier_amount"
    assert found[0]["score"] == 0.5


def test_a_draft_order_is_not_suggested_on_amount_alone(app, client, owner, supplier):
    """Only open orders are candidates for a supplier-and-amount guess. A draft
    nobody approved should not be offered as the explanation for a bill that
    has already arrived."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], approve=False)
    eid = make_invoice(app, owner, invoice_doc(reference=None),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    assert found == []


def test_candidates_never_cross_an_organization_boundary(app, client, owner):
    other_owner = make_user(app, email="other@example.com", plan="pro")
    other_supplier = make_supplier(app, other_owner["organization_id"],
                                   name="Their Vendor")
    create_po(client, auth_header(app, other_owner), other_supplier["id"])

    supplier_here = make_supplier(app, owner["organization_id"], name="Our Vendor")
    eid = make_invoice(app, owner, invoice_doc(reference="PO-0001"),
                       supplier_id=supplier_here["id"])
    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=auth_header(app, owner)).get_json()["candidates"]
    assert found == []


# ─── Header comparison ───────────────────────────────────────────────────────
def test_a_clean_invoice_against_an_approved_order_matches(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    assert link(client, headers, eid, po["id"]).status_code == 200

    body = client.get(f"/api/matching/invoices/{eid}",
                      headers=headers).get_json()
    assert body["comparison"]["outcome"] == "matched"
    assert body["comparison"]["counts"]["blocking"] == 0
    assert body["comparison"]["counts"]["review"] == 0
    assert body["comparison"]["blocked"] is False


@pytest.mark.parametrize("approve,expected_code", [
    (False, "po_not_approved"),
])
def test_invoicing_against_an_unapproved_order_is_blocked(
    app, client, owner, supplier, approve, expected_code
):
    """The control that stops spend being committed after the fact."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], approve=approve)
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert expected_code in codes(comparison)
    assert by_code(comparison, expected_code)["severity"] == "blocking"
    assert comparison["outcome"] == "failed"
    assert comparison["blocked"] is True


def test_an_order_waiting_for_approval_is_also_blocked(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], approve=False)
    client.post(f"/api/purchase-orders/{po['id']}/submit", headers=headers)
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert "po_not_approved" in codes(comparison)


def test_turning_off_the_unapproved_block_downgrades_it_to_review(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    client.put("/api/matching/settings", json={"blockUnapprovedPo": False},
               headers=headers)
    po = create_po(client, headers, supplier["id"], approve=False)
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert by_code(comparison, "po_not_approved")["severity"] == "review"
    assert comparison["outcome"] == "discrepancy"
    assert comparison["blocked"] is False


def test_invoicing_against_a_cancelled_order_is_blocked(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])
    client.delete(f"/api/purchase-orders/{po['id']}", headers=headers)

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert "po_cancelled" in codes(comparison)
    assert comparison["outcome"] == "failed"


def test_a_late_invoice_against_a_closed_order_is_flagged_for_review(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    for status in ("sent", "fully_received", "closed"):
        moved = client.post(f"/api/purchase-orders/{po['id']}/status",
                            json={"status": status}, headers=headers)
        assert moved.status_code == 200, moved.get_json()
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert by_code(comparison, "po_closed")["severity"] == "review"


def test_an_invoice_from_a_different_supplier_is_blocked(app, client, owner, supplier):
    """The signature of invoice-redirection fraud, and of an ordinary filing
    error. Either way it must not be paid on the strength of someone else's
    purchase order."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    impostor = make_supplier(app, owner["organization_id"], name="Not Acme Ltd")
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"],
                                              vendor="Not Acme Ltd"),
                       supplier_id=impostor["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert by_code(comparison, "supplier_mismatch")["severity"] == "blocking"


def test_a_different_currency_is_blocked_rather_than_converted(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], currency="NGN")
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"],
                                              currency="USD"),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert by_code(comparison, "currency_mismatch")["severity"] == "blocking"


def test_an_invoice_with_no_lines_says_so_instead_of_matching_silently(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"], lines=[]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert "no_invoice_lines" in codes(comparison)
    assert comparison["outcome"] == "discrepancy"


# ─── Line comparison ─────────────────────────────────────────────────────────
def _invoice_line(**overrides):
    return {**INVOICE_LINE, **overrides}


def test_a_higher_unit_price_is_blocked_and_the_message_names_both_figures(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1250.00",
                    lines=[_invoice_line(unit_price=125, amount=1250)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "line_price_higher")
    assert finding["severity"] == "blocking"
    assert "125.00" in finding["message"]
    assert "100.00" in finding["message"]
    assert "25.00" in finding["message"]        # the difference, spelled out
    assert finding["lineNo"] == 1


def test_a_lower_unit_price_is_reported_but_does_not_block_payment(
    app, client, owner, supplier
):
    """Charging less than agreed is not a reason to hold a payment. It is still
    worth seeing: it is as often a line paired with the wrong order line as it
    is a discount."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="900.00",
                    lines=[_invoice_line(unit_price=90, amount=900)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert by_code(comparison, "line_price_lower")["severity"] == "info"
    assert comparison["counts"]["blocking"] == 0
    assert comparison["blocked"] is False


def test_a_price_inside_the_tolerance_raises_nothing(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1000.20",
                    lines=[_invoice_line(unit_price="100.02", amount="1000.20")]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert "line_price_higher" not in codes(comparison)


def test_a_configured_percentage_tolerance_is_honoured(app, client, owner, supplier):
    headers = auth_header(app, owner)
    client.put("/api/matching/settings", json={"priceTolerancePercent": "5"},
               headers=headers)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1040.00",
                    lines=[_invoice_line(unit_price=104, amount=1040)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert "line_price_higher" not in codes(comparison)

    # And the next cent outside it is still caught.
    eid2 = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1060.00", number="INV-002",
                    lines=[_invoice_line(unit_price=106, amount=1060)]),
        supplier_id=supplier["id"], name="inv2.pdf",
    )
    link(client, headers, eid2, po["id"])
    comparison2 = client.get(f"/api/matching/invoices/{eid2}",
                             headers=headers).get_json()["comparison"]
    assert "line_price_higher" in codes(comparison2)


def test_invoicing_more_than_was_ordered_is_blocked(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])     # 10 ordered
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1200.00",
                    lines=[_invoice_line(quantity=12, amount=1200)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "line_over_quantity")
    assert finding["severity"] == "blocking"
    assert "12" in finding["message"] and "10" in finding["message"]


def test_invoicing_less_than_was_ordered_is_a_partial_delivery_not_an_error(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert "line_over_quantity" not in codes(comparison)
    assert comparison["counts"]["blocking"] == 0
    assert "partial_invoice" in codes(comparison)


def test_a_different_tax_rate_is_flagged_for_review(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"],
                   lines=[{**PO_LINE, "taxRate": "7.5"}])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1200.00",
                    lines=[_invoice_line(tax_rate=20, amount=1000)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "line_tax_mismatch")
    assert finding["severity"] == "review"
    assert "20%" in finding["message"] and "7.5%" in finding["message"]


def test_a_line_that_is_not_on_the_order_at_all_is_blocked(
    app, client, owner, supplier
):
    """Billing for something nobody ordered is the whole reason this check
    exists."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00", lines=[
            _invoice_line(),
            {"description": "Expedited handling surcharge", "product_name": None,
             "quantity": 1, "unit_price": 500, "discount": None, "tax_rate": 0,
             "amount": 500},
        ]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "line_not_on_po")
    assert finding["severity"] == "blocking"
    assert finding["lineNo"] == 2
    assert "Expedited handling surcharge" in finding["message"]


def test_order_lines_absent_from_the_invoice_are_noted_without_blocking(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], lines=[
        PO_LINE,
        {"description": "Stainless bolts M16", "sku": "BLT-1680",
         "quantity": "5", "unitPrice": "200.00", "taxRate": "0"},
    ])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert by_code(comparison, "lines_not_invoiced")["severity"] == "info"
    assert comparison["counts"]["blocking"] == 0
    assert len(comparison["poLinesNotInvoiced"]) == 1


# ─── Totals and over-invoicing ───────────────────────────────────────────────
def test_an_invoice_above_the_order_total_is_blocked_with_the_overage_named(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])     # 1,000.00
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "total_over_po")
    assert finding["severity"] == "blocking"
    assert "500.00" in finding["message"]       # over by
    assert comparison["totals"]["invoiceTotal"] == "1500.00"
    assert comparison["totals"]["poTotal"] == "1000.00"
    assert comparison["totals"]["remainingBefore"] == "1000.00"


def test_an_added_charge_is_caught_even_when_every_line_price_is_right(
    app, client, owner, supplier
):
    """A total above what the invoiced lines cost at order prices catches a
    charge that was added rather than a price that was changed."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"],
                   lines=[{**PO_LINE, "quantity": "20"}])   # 2,000.00 ordered
    eid = make_invoice(
        app, owner,
        # Ten units at the agreed 100.00 is 1,000.00, but the invoice says
        # 1,150.00 and no line explains the rest.
        invoice_doc(reference=po["poNumber"], total="1150.00",
                    lines=[_invoice_line()]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "total_above_order_prices")
    assert finding["severity"] == "review"
    assert "1,000.00" in finding["message"]
    assert "1,150.00" in finding["message"]
    assert comparison["totals"]["expectedAtOrderPrices"] == "1000.00"


def test_a_second_invoice_is_measured_against_what_is_left_on_the_order(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])     # 10 @ 100 = 1,000.00

    first = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="600.00",
                    lines=[_invoice_line(quantity=6, amount=600)]),
        supplier_id=supplier["id"], name="a.pdf",
    )
    link(client, headers, first, po["id"])

    second = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00", number="INV-002",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"], name="b.pdf",
    )
    link(client, headers, second, po["id"])

    comparison = client.get(f"/api/matching/invoices/{second}",
                            headers=headers).get_json()["comparison"]
    assert comparison["totals"]["alreadyInvoiced"] == "600.00"
    assert comparison["totals"]["remainingBefore"] == "400.00"
    assert comparison["totals"]["remainingAfter"] == "0.00"
    assert comparison["counts"]["blocking"] == 0


def test_the_overage_is_caught_across_two_invoices_not_just_one(
    app, client, owner, supplier
):
    """Each invoice on its own is well inside the order. Together they bill
    more than was ordered, and that is the version of over-invoicing a
    single-document check misses entirely."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])     # 10 @ 100 = 1,000.00

    first = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="700.00",
                    lines=[_invoice_line(quantity=7, amount=700)]),
        supplier_id=supplier["id"], name="a.pdf",
    )
    link(client, headers, first, po["id"])

    second = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="700.00", number="INV-002",
                    lines=[_invoice_line(quantity=7, amount=700)]),
        supplier_id=supplier["id"], name="b.pdf",
    )
    link(client, headers, second, po["id"])

    comparison = client.get(f"/api/matching/invoices/{second}",
                            headers=headers).get_json()["comparison"]
    assert "total_over_po" in codes(comparison)
    assert "line_over_quantity" in codes(comparison)
    over = by_code(comparison, "total_over_po")
    assert "400.00" in over["message"]      # 700 billed against 300 remaining
    assert comparison["outcome"] == "failed"


def test_a_confirmed_invoice_is_not_measured_against_its_own_value(
    app, client, owner, supplier
):
    """The exclusion that makes the rest of it work. Without it, re-reading a
    confirmed invoice would find the order's value already consumed - by
    itself - and report every single invoice as over-invoicing."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    for _ in range(3):
        comparison = client.get(f"/api/matching/invoices/{eid}",
                                headers=headers).get_json()["comparison"]
        assert comparison["totals"]["alreadyInvoiced"] == "0.00"
        assert "total_over_po" not in codes(comparison)
        assert comparison["outcome"] == "matched"


def test_a_suggestion_nobody_confirmed_does_not_consume_the_order(
    app, client, owner, supplier, monkeypatch
):
    """Otherwise one bad auto-suggestion would make every later invoice on that
    order look like over-invoicing."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    client.put("/api/matching/settings", json={"autoConfirmExact": False},
               headers=headers)

    upload(client, app, monkeypatch, headers,
           invoice_doc(reference=po["poNumber"]), name="suggested.pdf")

    second = make_invoice(app, owner,
                          invoice_doc(reference=po["poNumber"], number="INV-002"),
                          supplier_id=supplier["id"], name="b.pdf")
    link(client, headers, second, po["id"])
    comparison = client.get(f"/api/matching/invoices/{second}",
                            headers=headers).get_json()["comparison"]
    assert comparison["totals"]["alreadyInvoiced"] == "0.00"
    assert "total_over_po" not in codes(comparison)


def test_a_large_commitment_compares_exactly(app, client, owner, supplier):
    """The figures a float would round. 9,007,199,254,740.99 is past the point
    where a double can hold cents."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"], lines=[{
        "description": "Turbine", "quantity": "1",
        "unitPrice": "9007199254740.99", "taxRate": "0",
    }])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="9007199254740.99", lines=[{
            "description": "Turbine", "product_name": None, "quantity": 1,
            "unit_price": "9007199254740.99", "discount": None, "tax_rate": 0,
            "amount": "9007199254740.99",
        }]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert comparison["totals"]["poTotal"] == "9007199254740.99"
    assert comparison["totals"]["remainingAfter"] == "0.00"
    assert comparison["outcome"] == "matched"


def test_per_line_rounding_does_not_manufacture_a_discrepancy(
    app, client, owner, supplier
):
    """The convention P2.2 shipped for exactly this moment: the order rounds
    each line before summing, which is what the supplier prints, so a clean
    invoice compares clean."""
    headers = auth_header(app, owner)
    lines = [{"description": f"Item {n}", "quantity": "1",
              "unitPrice": "0.335", "taxRate": "0"} for n in range(3)]
    po = create_po(client, headers, supplier["id"], lines=lines)
    assert po["total"] == "1.02"

    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1.02", lines=[
            {"description": f"Item {n}", "product_name": None, "quantity": 1,
             "unit_price": "0.335", "discount": None, "tax_rate": 0,
             "amount": "0.34"}
            for n in range(3)
        ]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert comparison["outcome"] == "matched"
    assert comparison["counts"]["blocking"] == 0


def test_a_reference_with_several_digit_groups_still_finds_its_order(
    app, client, owner, supplier
):
    """"REQ-2026-0188" has two digit runs. Narrowing the scan with the runs
    joined into one "20260188" would match nothing at all, because the stored
    reference has a hyphen between them."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"], reference="REQ-2026-0188")
    eid = make_invoice(app, owner, invoice_doc(reference="REQ 2026 0188"),
                       supplier_id=supplier["id"])

    found = client.get(f"/api/matching/invoices/{eid}/candidates",
                       headers=headers).get_json()["candidates"]
    assert [entry["poNumber"] for entry in found] == ["PO-0001"]


def test_past_the_invoice_scan_cap_the_figure_is_reported_as_partial(
    app, client, owner, supplier, monkeypatch
):
    """The one direction this must never fail in.

    The scan over an order's confirmed invoices is capped. Quietly returning a
    smaller "already invoiced" figure would UNDERSTATE what has been billed,
    which is exactly what over-invoicing is measured against - so past the cap
    the comparison says the figure is incomplete rather than handing anyone a
    number that is wrong in the dangerous direction.
    """
    import po_matching

    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    for index in range(2):
        eid = make_invoice(
            app, owner,
            invoice_doc(reference=po["poNumber"], total="400.00",
                        number=f"INV-{index}",
                        lines=[_invoice_line(quantity=4, amount=400)]),
            supplier_id=supplier["id"], name=f"f{index}.pdf",
        )
        link(client, headers, eid, po["id"])

    monkeypatch.setattr(po_matching, "MAX_CONFIRMED_SCAN", 1)
    third = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00", number="INV-3",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"], name="f3.pdf",
    )
    link(client, headers, third, po["id"])

    comparison = client.get(f"/api/matching/invoices/{third}",
                            headers=headers).get_json()["comparison"]
    finding = by_code(comparison, "too_many_invoices")
    assert finding["severity"] == "review"
    assert "cannot be relied on" in finding["message"]


# ─── quantity_invoiced is a cache, not a counter ─────────────────────────────
def _po_line_invoiced(app, po_id):
    from models import PurchaseOrderLine

    with app.app_context():
        rows = (
            PurchaseOrderLine.query.filter_by(purchase_order_id=po_id)
            .order_by(PurchaseOrderLine.line_no)
            .all()
        )
        return [str(row.quantity_invoiced) for row in rows]


def test_confirming_a_link_records_the_invoiced_quantity_on_the_order(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    assert _po_line_invoiced(app, po["id"]) == ["4.0000"]


def test_re_linking_the_same_invoice_does_not_double_count_it(
    app, client, owner, supplier
):
    """The reason the column is recomputed rather than incremented. An
    increment would have made this 8."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    link(client, headers, eid, po["id"])
    link(client, headers, eid, po["id"])
    assert _po_line_invoiced(app, po["id"]) == ["4.0000"]


def test_rejecting_a_match_releases_the_quantity(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    assert client.post(f"/api/matching/invoices/{eid}/reject",
                       headers=headers).status_code == 200
    assert _po_line_invoiced(app, po["id"]) == ["0.0000"]


def test_unlinking_releases_the_quantity(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="400.00",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    assert client.delete(f"/api/matching/invoices/{eid}",
                         headers=headers).status_code == 200
    assert _po_line_invoiced(app, po["id"]) == ["0.0000"]


def test_moving_a_link_to_another_order_moves_the_quantity_with_it(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"])
    second = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=first["poNumber"], total="400.00",
                    lines=[_invoice_line(quantity=4, amount=400)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, first["id"])
    assert _po_line_invoiced(app, first["id"]) == ["4.0000"]

    link(client, headers, eid, second["id"])
    assert _po_line_invoiced(app, first["id"]) == ["0.0000"]
    assert _po_line_invoiced(app, second["id"]) == ["4.0000"]


def test_a_deleted_invoice_stops_consuming_the_order(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="600.00",
                    lines=[_invoice_line(quantity=6, amount=600)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    client.delete(f"/api/extractions/{eid}", headers=headers)

    second = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], number="INV-002", total="1000.00"),
        supplier_id=supplier["id"], name="b.pdf",
    )
    link(client, headers, second, po["id"])
    comparison = client.get(f"/api/matching/invoices/{second}",
                            headers=headers).get_json()["comparison"]
    assert comparison["totals"]["alreadyInvoiced"] == "0.00"


# ─── Automatic matching on upload ────────────────────────────────────────────
def test_an_exact_reference_with_clean_figures_links_itself(
    app, client, owner, supplier, monkeypatch
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference=po["poNumber"]))

    assert body["poMatch"]["status"] == "confirmed"
    assert body["poMatch"]["method"] == "po_number"
    assert body["poMatch"]["outcome"] == "matched"
    assert body["poMatch"]["blocked"] is False


def test_the_system_is_recorded_as_the_confirmer_not_the_uploader(
    app, client, owner, supplier, monkeypatch
):
    """Putting the uploader's name against a decision they never made would be
    a false audit trail."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    upload(client, app, monkeypatch, headers, invoice_doc(reference=po["poNumber"]))

    with app.app_context():
        from models import InvoiceMatch

        match = InvoiceMatch.query.first()
        assert match.status == "confirmed"
        assert match.confirmed_by_user_id is None
        assert match.confirmed_at is not None


def test_an_exact_reference_with_a_discrepancy_waits_for_a_person(
    app, client, owner, supplier, monkeypatch
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference=po["poNumber"], total="1500.00",
                              lines=[_invoice_line(unit_price=150, amount=1500)]))

    assert body["poMatch"]["status"] == "suggested"
    assert body["poMatch"]["outcome"] == "failed"
    assert body["poMatch"]["blocked"] is True
    assert "line_price_higher" in [f["code"] for f in body["poMatch"]["findings"]]


def test_auto_confirmation_can_be_switched_off(
    app, client, owner, supplier, monkeypatch
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    client.put("/api/matching/settings", json={"autoConfirmExact": False},
               headers=headers)
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference=po["poNumber"]))
    assert body["poMatch"]["status"] == "suggested"
    assert body["poMatch"]["outcome"] == "matched"


def test_a_supplier_and_amount_guess_is_never_confirmed_automatically(
    app, client, owner, supplier, monkeypatch
):
    """Two orders to the same supplier for the same amount are common, and
    picking the wrong one is invisible."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    body = upload(client, app, monkeypatch, headers, invoice_doc(reference=None))
    assert body["poMatch"]["status"] == "suggested"
    assert body["poMatch"]["method"] == "supplier_amount"


def test_an_invoice_citing_an_order_that_does_not_exist_is_blocked(
    app, client, owner, supplier, monkeypatch
):
    """Either the reference is wrong or somebody is billing against a purchase
    order they invented. Both need a person."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference="PO-9999"))

    assert body["poMatch"]["purchaseOrderId"] is None
    assert body["poMatch"]["blocked"] is True
    finding = [f for f in body["poMatch"]["findings"] if f["code"] == "po_not_found"]
    assert finding and finding[0]["severity"] == "blocking"
    assert "PO-9999" in finding[0]["message"]


def test_an_invoice_with_no_reference_is_a_review_by_default_not_a_block(
    app, client, owner, supplier, monkeypatch
):
    """Plenty of legitimate spend - utilities, rent, a taxi - never carries a
    purchase order."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"],
              lines=[{**PO_LINE, "unitPrice": "999.00"}])   # so amount differs
    body = upload(client, app, monkeypatch, headers, invoice_doc(reference=None))

    findings = body["poMatch"]["findings"]
    assert [f["code"] for f in findings] == ["no_po_reference"]
    assert findings[0]["severity"] == "review"
    assert body["poMatch"]["blocked"] is False


def test_requiring_a_po_reference_turns_that_into_a_block(
    app, client, owner, supplier, monkeypatch
):
    headers = auth_header(app, owner)
    client.put("/api/matching/settings", json={"requirePoReference": True},
               headers=headers)
    create_po(client, headers, supplier["id"],
              lines=[{**PO_LINE, "unitPrice": "999.00"}])
    body = upload(client, app, monkeypatch, headers, invoice_doc(reference=None))

    findings = body["poMatch"]["findings"]
    assert findings[0]["code"] == "no_po_reference"
    assert findings[0]["severity"] == "blocking"
    assert body["poMatch"]["blocked"] is True


def test_an_organization_with_no_purchase_orders_is_not_told_about_matching(
    app, client, owner, monkeypatch
):
    """A customer using this only for extraction should not start seeing "no PO
    reference" exceptions on every document they upload."""
    body = upload(client, app, monkeypatch, auth_header(app, owner),
                  invoice_doc(reference=None))
    assert body["poMatch"] is None


def test_a_receipt_is_not_matched_against_purchase_orders(
    app, client, owner, supplier, monkeypatch
):
    import routes.extract_routes as er
    from receipt_schema import normalize as normalize_receipt

    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    monkeypatch.setattr(
        "openai_service.extract_document",
        lambda pages, doc_type="invoice": normalize_receipt({
            "merchant": {"name": "Acme Supplies Ltd"},
            "receipt_number": "R-1", "receipt_date": "2026-11-20",
            "currency": "NGN", "total": "1000.00", "line_items": [],
        }),
    )
    response = client.post(
        "/api/extract",
        data={"file": (io.BytesIO(b"receipt"), "r.pdf"), "doc_type": "receipt"},
        headers=headers,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.get_json().get("poMatch") is None
    with app.app_context():
        from models import InvoiceMatch

        assert InvoiceMatch.query.count() == 0


def test_a_matching_failure_does_not_lose_the_upload(
    app, client, owner, supplier, monkeypatch
):
    """The customer has already paid to process this document."""
    import routes.extract_routes as er

    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])

    def explode(*args, **kwargs):
        raise RuntimeError("matching is broken")

    monkeypatch.setattr(er, "auto_match", explode)
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference=po["poNumber"]))
    assert body["id"]
    assert body["invoice"]["total"] == "1000.00"


# ─── Linking, rejecting, overriding ──────────────────────────────────────────
def test_an_unmatched_invoice_reports_what_is_missing(app, client, owner, supplier):
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=None),
                       supplier_id=supplier["id"])

    body = client.get(f"/api/matching/invoices/{eid}", headers=headers).get_json()
    assert body["match"] is None
    assert body["comparison"]["matched"] is False
    assert codes(body["comparison"]) == ["no_po_reference"]


def test_a_person_naming_the_order_is_confirmed_outright(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=None),
                       supplier_id=supplier["id"])

    body = link(client, headers, eid, po["id"]).get_json()
    assert body["match"]["status"] == "confirmed"
    assert body["match"]["method"] == "manual"
    assert body["match"]["confirmedBy"] == "Test"


def test_confirming_a_link_does_not_approve_the_invoice(app, client, owner, supplier):
    """The distinction the whole module rests on. Saying which order an invoice
    belongs to is bookkeeping; a blocking finding still blocks."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=None, total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    body = link(client, headers, eid, po["id"]).get_json()
    assert body["match"]["status"] == "confirmed"
    assert body["comparison"]["blocked"] is True
    assert body["comparison"]["outcome"] == "failed"


def test_linking_to_an_order_that_does_not_exist_is_a_404(app, client, owner):
    eid = make_invoice(app, owner, invoice_doc(reference=None))
    assert link(client, auth_header(app, owner), eid, "nope").status_code == 404


def test_linking_without_naming_an_order_is_a_field_error(app, client, owner):
    eid = make_invoice(app, owner, invoice_doc(reference=None))
    response = client.post(f"/api/matching/invoices/{eid}/link", json={},
                           headers=auth_header(app, owner))
    assert response.status_code == 400
    assert "purchaseOrderId" in response.get_json()["fields"]


def test_an_invoice_cannot_be_linked_to_another_organizations_order(
    app, client, owner, supplier
):
    other_owner = make_user(app, email="other@example.com", plan="pro")
    other_supplier = make_supplier(app, other_owner["organization_id"],
                                   name="Their Vendor")
    their_po = create_po(client, auth_header(app, other_owner), other_supplier["id"])

    eid = make_invoice(app, owner, invoice_doc(reference=None),
                       supplier_id=supplier["id"])
    assert link(client, auth_header(app, owner), eid,
                their_po["id"]).status_code == 404


def test_a_viewer_cannot_link_an_invoice_to_an_order(app, client, owner, supplier):
    org = make_org(app, owner, name="Acme", plan="pro")
    watcher = make_user(app, email="watcher@example.com", plan="pro")
    join_org(app, org, watcher, VIEWER)
    po = create_po(client, auth_header(app, owner), supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=None))

    headers = {**auth_header(app, watcher), **org_header(app, watcher, org)}
    # 403 and not 404: the permission decorator runs before the handler
    # looks anything up, so a viewer is refused rather than told whether
    # the invoice exists.
    assert client.post(f"/api/matching/invoices/{eid}/link",
                       json={"purchaseOrderId": po["id"]},
                       headers=headers).status_code == 403


def test_an_accountant_can_link_because_that_is_their_job(app, client, owner):
    """Linking needs documents:write, not purchase_orders:write: it is a fact
    about the invoice, and accounts payable is who establishes it."""
    org = make_org(app, owner, name="Acme", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, org, clerk, ACCOUNTANT)
    owner_headers = {**auth_header(app, owner), **org_header(app, owner, org)}
    supplier_here = make_supplier(app, org["id"], name="Shared Vendor")
    po = create_po(client, owner_headers, supplier_here["id"])

    from documents import apply_headline_fields
    from extensions import db
    from models import Extraction

    with app.app_context():
        row = Extraction(organization_id=org["id"], user_id=clerk["id"],
                         doc_type="invoice", file_name="i.pdf",
                         file_type="application/pdf", file_size=10,
                         data="{}", status="completed")
        apply_headline_fields(row, invoice_doc(reference=None))
        db.session.add(row)
        db.session.commit()
        eid = row.id

    headers = {**auth_header(app, clerk), **org_header(app, clerk, org)}
    assert client.post(f"/api/matching/invoices/{eid}/link",
                       json={"purchaseOrderId": po["id"]},
                       headers=headers).status_code == 200


def test_rejecting_a_suggestion_keeps_the_record_that_someone_looked(
    app, client, owner, supplier, monkeypatch
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    client.put("/api/matching/settings", json={"autoConfirmExact": False},
               headers=headers)
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference=po["poNumber"]))
    eid = body["id"]

    rejected = client.post(f"/api/matching/invoices/{eid}/reject", headers=headers)
    assert rejected.status_code == 200
    assert rejected.get_json()["match"]["status"] == "rejected"
    with app.app_context():
        from models import InvoiceMatch

        assert InvoiceMatch.query.filter_by(extraction_id=eid).count() == 1


def test_a_rejected_match_reads_as_unmatched(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])
    client.post(f"/api/matching/invoices/{eid}/reject", headers=headers)

    comparison = client.get(f"/api/matching/invoices/{eid}",
                            headers=headers).get_json()["comparison"]
    assert comparison["matched"] is False


def test_rejecting_an_unlinked_invoice_is_a_404(app, client, owner):
    eid = make_invoice(app, owner, invoice_doc(reference=None))
    response = client.post(f"/api/matching/invoices/{eid}/reject",
                           headers=auth_header(app, owner))
    assert response.status_code == 404
    assert response.get_json()["code"] == "NOT_LINKED"


def test_accepting_discrepancies_requires_a_written_reason(
    app, client, owner, supplier
):
    """"Approved anyway" with no reason is not an audit trail."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    blank = client.post(f"/api/matching/invoices/{eid}/override",
                        json={"note": "   "}, headers=headers)
    assert blank.status_code == 400
    assert blank.get_json()["code"] == "NOTE_REQUIRED"


def test_an_accepted_discrepancy_names_the_person_and_keeps_the_findings(
    app, client, owner, supplier
):
    """An override does not make the finding go away. What changed is that
    somebody took responsibility for it."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    body = client.post(f"/api/matching/invoices/{eid}/override",
                       json={"note": "Price rise agreed by phone on 18 Nov."},
                       headers=headers).get_json()
    assert body["match"]["overridden"] is True
    assert body["match"]["overriddenBy"] == "Test"
    assert body["match"]["overrideNote"].startswith("Price rise agreed")
    # Still failed, still reported - just no longer blocking.
    assert body["comparison"]["outcome"] == "failed"
    assert "line_price_higher" in codes(body["comparison"])
    assert body["comparison"]["blocked"] is False


def test_accepting_discrepancies_needs_approval_authority(app, client, owner):
    """Gated on approvals:act, not on the permission used to process invoices:
    clearing a blocking finding is a decision somebody signs."""
    org = make_org(app, owner, name="Acme", plan="pro")
    clerk = make_user(app, email="clerk@example.com", plan="pro")
    join_org(app, org, clerk, ACCOUNTANT)
    supplier_here = make_supplier(app, org["id"], name="Shared Vendor")
    owner_headers = {**auth_header(app, owner), **org_header(app, owner, org)}
    po = create_po(client, owner_headers, supplier_here["id"])

    from documents import apply_headline_fields
    from extensions import db
    from models import Extraction

    with app.app_context():
        row = Extraction(organization_id=org["id"], user_id=clerk["id"],
                         doc_type="invoice", file_name="i.pdf",
                         file_type="application/pdf", file_size=10,
                         data="{}", status="completed")
        apply_headline_fields(
            row, invoice_doc(reference=None, total="1500.00",
                             lines=[_invoice_line(unit_price=150, amount=1500)]))
        db.session.add(row)
        db.session.commit()
        eid = row.id

    clerk_headers = {**auth_header(app, clerk), **org_header(app, clerk, org)}
    assert client.post(f"/api/matching/invoices/{eid}/link",
                       json={"purchaseOrderId": po["id"]},
                       headers=clerk_headers).status_code == 200
    assert client.post(f"/api/matching/invoices/{eid}/override",
                       json={"note": "fine"},
                       headers=clerk_headers).status_code == 403

    approver = make_user(app, email="approver@example.com", plan="pro")
    join_org(app, org, approver, APPROVER)
    approver_headers = {**auth_header(app, approver),
                        **org_header(app, approver, org)}
    assert client.post(f"/api/matching/invoices/{eid}/override",
                       json={"note": "Price rise agreed."},
                       headers=approver_headers).status_code == 200


def test_there_is_nothing_to_accept_on_a_clean_match(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    response = client.post(f"/api/matching/invoices/{eid}/override",
                           json={"note": "just in case"}, headers=headers)
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOTHING_TO_OVERRIDE"


def test_discrepancies_cannot_be_accepted_before_the_invoice_is_linked(
    app, client, owner
):
    eid = make_invoice(app, owner, invoice_doc(reference=None))
    response = client.post(f"/api/matching/invoices/{eid}/override",
                           json={"note": "fine"}, headers=auth_header(app, owner))
    assert response.status_code == 409
    assert response.get_json()["code"] == "NOT_LINKED"


def test_accepting_an_unconfirmed_suggestion_confirms_it_too(
    app, client, owner, supplier, monkeypatch
):
    """Accepting the figures means accepting the link they were measured
    against; leaving it unconfirmed would keep the invoice out of the order's
    invoiced total it was just checked against."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    body = upload(client, app, monkeypatch, headers,
                  invoice_doc(reference=po["poNumber"], total="1500.00",
                              lines=[_invoice_line(unit_price=150, amount=1500)]))
    eid = body["id"]
    assert body["poMatch"]["status"] == "suggested"

    accepted = client.post(f"/api/matching/invoices/{eid}/override",
                           json={"note": "Agreed increase."},
                           headers=headers).get_json()
    assert accepted["match"]["status"] == "confirmed"
    assert _po_line_invoiced(app, po["id"]) == ["10.0000"]


def test_an_acceptance_can_be_withdrawn(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    client.post(f"/api/matching/invoices/{eid}/override",
                json={"note": "Agreed."}, headers=headers)

    withdrawn = client.delete(f"/api/matching/invoices/{eid}/override",
                              headers=headers)
    assert withdrawn.status_code == 200
    assert withdrawn.get_json()["match"]["overridden"] is False
    assert withdrawn.get_json()["comparison"]["blocked"] is True


def test_moving_the_link_to_a_different_order_clears_the_acceptance(
    app, client, owner, supplier
):
    """The discrepancies somebody accepted were about the old order. Carrying
    their acceptance across to a different one would launder it."""
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"])
    second = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=None, total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, first["id"])
    client.post(f"/api/matching/invoices/{eid}/override",
                json={"note": "Agreed for this order."}, headers=headers)

    body = link(client, headers, eid, second["id"]).get_json()
    assert body["match"]["overridden"] is False
    assert body["match"]["overrideNote"] is None
    assert body["comparison"]["blocked"] is True


def test_rejecting_a_match_clears_the_acceptance_with_it(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    client.post(f"/api/matching/invoices/{eid}/override",
                json={"note": "Agreed."}, headers=headers)
    body = client.post(f"/api/matching/invoices/{eid}/reject",
                       headers=headers).get_json()
    assert body["match"]["overridden"] is False


# ─── The exception list ──────────────────────────────────────────────────────
def test_an_invoice_with_no_match_row_still_appears_in_the_list(
    app, client, owner, supplier
):
    """The single most important thing this list has to show. An invoice nobody
    has tied to an order is invisible to every query that starts from the match
    table."""
    headers = auth_header(app, owner)
    create_po(client, headers, supplier["id"])
    make_invoice(app, owner, invoice_doc(reference=None), supplier_id=supplier["id"])

    body = client.get("/api/matching/invoices?state=unmatched",
                      headers=headers).get_json()
    assert body["total"] == 1
    assert body["items"][0]["match"] is None


def test_the_exception_filter_shows_unmatched_and_unresolved_together(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])

    clean = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                         supplier_id=supplier["id"], name="clean.pdf")
    link(client, headers, clean, po["id"])

    bad = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], number="INV-002", total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"], name="bad.pdf",
    )
    link(client, headers, bad, po["id"])
    client.get(f"/api/matching/invoices/{bad}", headers=headers)  # refresh cache

    orphan = make_invoice(app, owner,
                          invoice_doc(reference=None, number="INV-003"),
                          supplier_id=supplier["id"], name="orphan.pdf")

    body = client.get("/api/matching/invoices?state=exceptions",
                      headers=headers).get_json()
    ids = {item["extractionId"] for item in body["items"]}
    assert ids == {bad, orphan}
    assert clean not in ids


def test_an_accepted_discrepancy_leaves_the_exception_list(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    client.get(f"/api/matching/invoices/{eid}", headers=headers)
    assert client.get("/api/matching/invoices?state=exceptions",
                      headers=headers).get_json()["total"] == 1

    client.post(f"/api/matching/invoices/{eid}/override",
                json={"note": "Agreed."}, headers=headers)
    assert client.get("/api/matching/invoices?state=exceptions",
                      headers=headers).get_json()["total"] == 0
    assert client.get("/api/matching/invoices?state=overridden",
                      headers=headers).get_json()["total"] == 1


def test_the_blocked_filter_finds_what_must_not_be_paid(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    client.get(f"/api/matching/invoices/{eid}", headers=headers)

    body = client.get("/api/matching/invoices?state=blocked",
                      headers=headers).get_json()
    assert [item["extractionId"] for item in body["items"]] == [eid]
    assert body["items"][0]["match"]["blockingCount"] >= 1
    assert body["items"][0]["match"]["poNumber"] == po["poNumber"]


def test_the_list_can_be_filtered_by_order_and_searched_by_invoice_number(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    first = create_po(client, headers, supplier["id"])
    second = create_po(client, headers, supplier["id"])
    a = make_invoice(app, owner, invoice_doc(reference=first["poNumber"],
                                             number="INV-AAA"),
                     supplier_id=supplier["id"], name="a.pdf")
    b = make_invoice(app, owner, invoice_doc(reference=second["poNumber"],
                                             number="INV-BBB"),
                     supplier_id=supplier["id"], name="b.pdf")
    link(client, headers, a, first["id"])
    link(client, headers, b, second["id"])

    by_po = client.get(f"/api/matching/invoices?poId={first['id']}",
                       headers=headers).get_json()
    assert [item["extractionId"] for item in by_po["items"]] == [a]

    by_number = client.get("/api/matching/invoices?q=INV-BBB",
                           headers=headers).get_json()
    assert [item["extractionId"] for item in by_number["items"]] == [b]


def test_the_list_is_paginated(app, client, owner, supplier):
    headers = auth_header(app, owner)
    for n in range(5):
        make_invoice(app, owner, invoice_doc(reference=None, number=f"INV-{n}"),
                     supplier_id=supplier["id"], name=f"f{n}.pdf")

    first = client.get("/api/matching/invoices?pageSize=2", headers=headers).get_json()
    assert first["total"] == 5
    assert len(first["items"]) == 2
    assert first["hasMore"] is True
    last = client.get("/api/matching/invoices?pageSize=2&page=3",
                      headers=headers).get_json()
    assert len(last["items"]) == 1
    assert last["hasMore"] is False


def test_the_list_never_shows_another_organizations_invoices(app, client, owner):
    other = make_user(app, email="other@example.com", plan="pro")
    other_supplier = make_supplier(app, other["organization_id"], name="Theirs")
    make_invoice(app, other, invoice_doc(reference=None),
                 supplier_id=other_supplier["id"])

    body = client.get("/api/matching/invoices",
                      headers=auth_header(app, owner)).get_json()
    assert body["total"] == 0


def test_a_deleted_invoice_leaves_the_list(app, client, owner, supplier):
    headers = auth_header(app, owner)
    eid = make_invoice(app, owner, invoice_doc(reference=None),
                       supplier_id=supplier["id"])
    assert client.get("/api/matching/invoices", headers=headers).get_json()["total"] == 1
    client.delete(f"/api/extractions/{eid}", headers=headers)
    assert client.get("/api/matching/invoices", headers=headers).get_json()["total"] == 0


# ─── Summary ─────────────────────────────────────────────────────────────────
def test_the_summary_leads_with_what_somebody_has_to_act_on(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])

    clean = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                         supplier_id=supplier["id"], name="clean.pdf")
    link(client, headers, clean, po["id"])

    bad = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], number="INV-002", total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"], name="bad.pdf",
    )
    link(client, headers, bad, po["id"])
    client.get(f"/api/matching/invoices/{bad}", headers=headers)

    make_invoice(app, owner, invoice_doc(reference=None, number="INV-003"),
                 supplier_id=supplier["id"], name="orphan.pdf")

    body = client.get("/api/matching/summary", headers=headers).get_json()
    assert body["invoices"] == 3
    assert body["unmatched"] == 1
    assert body["blocked"] == 1
    assert body["byOutcome"]["matched"] == 1
    assert body["byOutcome"]["failed"] == 1


def test_the_summary_counts_nothing_from_another_organization(app, client, owner):
    other = make_user(app, email="other@example.com", plan="pro")
    other_supplier = make_supplier(app, other["organization_id"], name="Theirs")
    make_invoice(app, other, invoice_doc(reference=None),
                 supplier_id=other_supplier["id"])

    body = client.get("/api/matching/summary",
                      headers=auth_header(app, owner)).get_json()
    assert body["invoices"] == 0
    assert body["unmatched"] == 0


# ─── From the order's side ───────────────────────────────────────────────────
def test_an_order_lists_the_invoices_billed_against_it(app, client, owner, supplier):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    first = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="600.00",
                    lines=[_invoice_line(quantity=6, amount=600)]),
        supplier_id=supplier["id"], name="a.pdf",
    )
    link(client, headers, first, po["id"])

    body = client.get(f"/api/matching/purchase-orders/{po['id']}/invoices",
                      headers=headers).get_json()
    assert body["poTotal"] == "1000.00"
    assert body["invoiced"] == "600.00"
    assert body["remaining"] == "400.00"
    assert len(body["items"]) == 1
    assert body["items"][0]["status"] == "confirmed"


def test_the_remaining_value_counts_confirmed_invoices_only(
    app, client, owner, supplier, monkeypatch
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    client.put("/api/matching/settings", json={"autoConfirmExact": False},
               headers=headers)
    upload(client, app, monkeypatch, headers,
           invoice_doc(reference=po["poNumber"], total="600.00",
                       lines=[_invoice_line(quantity=6, amount=600)]))

    body = client.get(f"/api/matching/purchase-orders/{po['id']}/invoices",
                      headers=headers).get_json()
    assert body["items"][0]["status"] == "suggested"
    assert body["invoiced"] == "0.00"
    assert body["remaining"] == "1000.00"


def test_another_organizations_order_cannot_be_queried(app, client, owner):
    other = make_user(app, email="other@example.com", plan="pro")
    other_supplier = make_supplier(app, other["organization_id"], name="Theirs")
    their_po = create_po(client, auth_header(app, other), other_supplier["id"])

    response = client.get(
        f"/api/matching/purchase-orders/{their_po['id']}/invoices",
        headers=auth_header(app, owner),
    )
    assert response.status_code == 404


# ─── The cached verdict stays honest ─────────────────────────────────────────
def test_correcting_a_figure_on_the_invoice_changes_the_verdict(
    app, client, owner, supplier
):
    """Findings are recomputed from the live document, so fixing a misread
    price clears the exception instead of leaving it open forever."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    document = invoice_doc(reference=po["poNumber"], total="1500.00",
                           lines=[_invoice_line(unit_price=150, amount=1500)])
    eid = make_invoice(app, owner, document, supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    before = client.get(f"/api/matching/invoices/{eid}",
                        headers=headers).get_json()["comparison"]
    assert before["outcome"] == "failed"

    corrected = client.patch(
        f"/api/extractions/{eid}",
        json={"invoice": {
            "vendor": {"name": "Acme Supplies Ltd"},
            "invoice_number": "INV-001",
            "invoice_date": "2026-11-20",
            "currency": "NGN",
            "purchase_order_reference": po["poNumber"],
            "line_items": [dict(INVOICE_LINE)],
            "subtotal": "1000.00", "tax": 0, "total": "1000.00",
        }},
        headers=headers,
    )
    assert corrected.status_code == 200
    assert corrected.get_json()["poMatch"]["outcome"] == "matched"

    after = client.get(f"/api/matching/invoices/{eid}",
                       headers=headers).get_json()["comparison"]
    assert after["outcome"] == "matched"
    assert after["counts"]["blocking"] == 0


def test_the_cached_verdict_is_written_back_so_the_list_agrees_with_the_detail(
    app, client, owner, supplier
):
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])
    client.get(f"/api/matching/invoices/{eid}", headers=headers)

    with app.app_context():
        from models import InvoiceMatch

        match = InvoiceMatch.query.filter_by(extraction_id=eid).first()
        assert match.outcome == "failed"
        assert match.blocking_count >= 1


def test_is_blocked_is_the_single_question_approval_will_ask(app, client, owner,
                                                             supplier):
    """P2.5's approval engine calls this and nothing else. A blocking finding
    stops an invoice unless a named person has accepted it."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(
        app, owner,
        invoice_doc(reference=po["poNumber"], total="1500.00",
                    lines=[_invoice_line(unit_price=150, amount=1500)]),
        supplier_id=supplier["id"],
    )
    link(client, headers, eid, po["id"])

    with app.app_context():
        from documents import load_document
        from models import Extraction, InvoiceMatch
        from po_matching import evaluate, is_blocked

        record = Extraction.query.filter_by(id=eid).first()
        match = InvoiceMatch.query.filter_by(extraction_id=eid).first()
        comparison = evaluate(record, load_document(record), match=match)
        assert is_blocked(match, comparison) is True

        match.overridden_at = __import__("datetime").datetime.utcnow()
        assert is_blocked(match, comparison) is False


def test_money_crosses_the_api_as_decimal_strings_never_numbers(
    app, client, owner, supplier
):
    """A JSON number is read back as a double by every JavaScript client, which
    would undo the precision the Numeric columns exist to preserve."""
    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])

    body = client.get(f"/api/matching/invoices/{eid}", headers=headers).get_json()
    totals = body["comparison"]["totals"]
    for key in ("invoiceTotal", "poTotal", "alreadyInvoiced", "remainingBefore",
                "remainingAfter", "expectedAtOrderPrices"):
        assert isinstance(totals[key], str), key
    for line in body["comparison"]["lines"]:
        assert isinstance(line["unitPrice"], str)
        assert isinstance(line["poLine"]["quantityOutstanding"], str)


def test_the_order_endpoint_still_reports_bank_details_nowhere(
    app, client, owner, supplier
):
    """A match is about what was ordered. Bank details are gated behind
    suppliers:bank:read on the supplier endpoints, and must not leak through a
    comparison payload."""
    from extensions import db
    from models import Supplier

    with app.app_context():
        row = Supplier.query.filter_by(id=supplier["id"]).first()
        row.bank_account_number = "0123456789"
        row.bank_name = "Example Bank"
        db.session.commit()

    headers = auth_header(app, owner)
    po = create_po(client, headers, supplier["id"])
    eid = make_invoice(app, owner, invoice_doc(reference=po["poNumber"]),
                       supplier_id=supplier["id"])
    link(client, headers, eid, po["id"])
    raw = client.get(f"/api/matching/invoices/{eid}", headers=headers).get_data(
        as_text=True)
    assert "0123456789" not in raw
    assert "Example Bank" not in raw


def test_a_finance_manager_and_a_procurement_officer_can_both_read_matches(
    app, client, owner, supplier
):
    org = make_org(app, owner, name="Acme", plan="pro")
    for email, role in (("fm@example.com", FINANCE_MANAGER),
                        ("po@example.com", PROCUREMENT)):
        member = make_user(app, email=email)
        join_org(app, org, member, role)
        headers = {**auth_header(app, member), **org_header(app, member, org)}
        assert client.get("/api/matching/summary", headers=headers).status_code == 200
