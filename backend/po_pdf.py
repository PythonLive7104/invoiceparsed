"""Render a purchase order as a PDF.

A PO is a document you send to a supplier, so it has to survive leaving the
application: printed, emailed, filed. PDF is what suppliers expect to receive
and the only format that looks the same everywhere.

Isolated in its own module with one entry point, `render_purchase_order`, so
the renderer can be replaced without touching the route, and so the import of
reportlab stays optional — a server that has not been rebuilt since this landed
returns a clear 503 instead of a 500 traceback.

Figures are formatted from Decimal with `money.as_json`, never float: a penny
of drift on a document a supplier will invoice against is a real dispute.
"""
import logging
from decimal import Decimal

from money import as_json, to_decimal

logger = logging.getLogger(__name__)

try:  # pragma: no cover - import guard, exercised by deployment not tests
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        KeepTogether,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    REPORTLAB_AVAILABLE = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False


INK = "#0f172a"
MUTED = "#64748b"
RULE = "#cbd5e1"
ACCENT = "#1d4ed8"

STATUS_LABELS = {
    "draft": "DRAFT - NOT YET APPROVED",
    "pending_approval": "PENDING APPROVAL - NOT YET APPROVED",
    "approved": "APPROVED",
    "sent": "APPROVED",
    "partially_received": "APPROVED - PARTIALLY RECEIVED",
    "fully_received": "APPROVED - RECEIVED IN FULL",
    "closed": "CLOSED",
    "cancelled": "CANCELLED",
}

# Statuses where the document must not read as an authorization to supply.
# Printing a draft that looks approved is how an unapproved commitment becomes
# a real one, so the banner says so in words rather than relying on a colour.
UNAUTHORIZED = {"draft", "pending_approval", "cancelled"}


def _fmt(value, currency: str) -> str:
    rendered = as_json(value)
    return f"{currency} {rendered}" if rendered is not None else "-"


def _qty(value) -> str:
    """Quantity without trailing noise: 3 rather than 3.0000, 2.5 rather than
    2.5000. The unit column carries the meaning; the zeros carry nothing."""
    parsed = to_decimal(value)
    if parsed is None:
        return "-"
    normalized = parsed.normalize()
    # normalize() turns 300 into 3E+2, which is correct and unreadable.
    if normalized == normalized.to_integral_value():
        return str(normalized.quantize(Decimal(1)))
    return format(normalized, "f")


def render_purchase_order(po, *, organization, supplier) -> bytes:
    """The purchase order as PDF bytes.

    `po` is a PurchaseOrder, `organization` an Organization and `supplier` a
    Supplier. Raises RuntimeError if reportlab is unavailable so the caller can
    answer with a useful message.
    """
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError(
            "PDF rendering is unavailable on this server: the reportlab "
            "package is not installed."
        )

    import io

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Purchase Order {po.po_number}",
        author=organization.name if organization else "",
        subject=f"Purchase order {po.po_number}",
    )

    sheet = getSampleStyleSheet()
    base = ParagraphStyle(
        "po_base", parent=sheet["Normal"], fontName="Helvetica",
        fontSize=9, leading=12.5, textColor=colors.HexColor(INK),
    )
    small = ParagraphStyle("po_small", parent=base, fontSize=7.6, leading=10,
                           textColor=colors.HexColor(MUTED))
    label = ParagraphStyle("po_label", parent=small, fontName="Helvetica-Bold")
    title = ParagraphStyle("po_title", parent=base, fontSize=19, leading=23,
                           fontName="Helvetica-Bold")
    heading = ParagraphStyle("po_heading", parent=base, fontSize=8.4,
                             fontName="Helvetica-Bold", leading=11)
    right = ParagraphStyle("po_right", parent=base, alignment=TA_RIGHT)
    right_bold = ParagraphStyle("po_right_b", parent=right,
                                fontName="Helvetica-Bold")

    currency = po.currency or ""
    story = []

    # ── Header: who is ordering, and what this document is ──────────────────
    org_name = (organization.name if organization else "") or "Purchase order"
    status_note = STATUS_LABELS.get(po.status, po.status.replace("_", " ").upper())
    status_colour = ACCENT if po.status not in UNAUTHORIZED else "#b91c1c"

    story.append(Table(
        [[
            Paragraph(f"<b>{_esc(org_name)}</b>", base),
            Paragraph("PURCHASE ORDER", title),
        ]],
        colWidths=[None, 62 * mm],
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]),
    ))
    story.append(Paragraph(
        f'<font color="{status_colour}"><b>{_esc(status_note)}</b></font>', small
    ))
    story.append(Spacer(1, 7 * mm))

    # ── Meta: number, dates, references ─────────────────────────────────────
    meta = [
        ("PO number", po.po_number),
        ("Order date", po.order_date),
        ("Expected delivery", po.expected_delivery_date),
        ("Payment terms", po.payment_terms),
        ("Your reference", po.reference),
        ("Department", po.department),
        ("Cost centre", po.cost_center),
        ("Project", po.project),
    ]
    present = [(key, value) for key, value in meta if value]
    story.append(Table(
        _meta_rows(present, label, base) or [[Paragraph("", base)] * 4],
        colWidths=[doc.width / 4.0] * 4,
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]),
    ))
    story.append(Spacer(1, 6 * mm))

    # ── Supplier and delivery ───────────────────────────────────────────────
    supplier_lines = []
    if supplier is not None:
        supplier_lines = [
            supplier.name,
            supplier.contact_name,
            supplier.address,
            supplier.email,
            supplier.phone,
            f"Tax ID: {supplier.tax_id}" if supplier.tax_id else None,
        ]
    supplier_block = "<br/>".join(_esc(x) for x in supplier_lines if x) or "-"
    delivery_block = _esc(po.delivery_address) if po.delivery_address else "-"

    story.append(Table(
        [[
            Paragraph("SUPPLIER", label),
            Paragraph("DELIVER TO", label),
        ], [
            Paragraph(supplier_block, base),
            Paragraph(delivery_block.replace("\n", "<br/>"), base),
        ]],
        colWidths=[doc.width / 2.0] * 2,
        style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
        ]),
    ))
    story.append(Spacer(1, 7 * mm))

    # ── Lines ───────────────────────────────────────────────────────────────
    header = ["#", "Description", "Qty", "Unit", "Unit price", "Tax", "Amount"]
    rows = [[Paragraph(f"<b>{_esc(cell)}</b>", heading) for cell in header]]
    for line in po.lines:
        description = _esc(line.description)
        if line.sku:
            description += f'<br/><font color="{MUTED}" size="7.4">SKU {_esc(line.sku)}</font>'
        rows.append([
            Paragraph(str(line.line_no), base),
            Paragraph(description, base),
            Paragraph(_qty(line.quantity), right),
            Paragraph(_esc(line.unit or "-"), base),
            Paragraph(as_json(line.unit_price) or "-", right),
            Paragraph(f"{_qty(line.tax_rate)}%", right),
            # The NET line amount, not the tax-inclusive total: this column has
            # to add up to the Subtotal printed below it, or the document does
            # not foot and anyone checking it finds the figures disagree.
            Paragraph(as_json(line.line_subtotal) or "-", right),
        ])
    if len(rows) == 1:
        rows.append([Paragraph("No lines on this order.", small)] + [""] * 6)

    widths = [8 * mm, None, 16 * mm, 15 * mm, 24 * mm, 14 * mm, 26 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, colors.HexColor(INK)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, colors.HexColor(RULE)),
        ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ("ALIGN", (4, 0), (-1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    # ── Totals ──────────────────────────────────────────────────────────────
    totals = [
        ("Subtotal", po.subtotal, False),
        ("Tax", po.tax_total, False),
        ("Total", po.total, True),
    ]
    total_rows = [
        [
            Paragraph(name, right_bold if strong else right),
            Paragraph(_fmt(value, currency), right_bold if strong else right),
        ]
        for name, value, strong in totals
    ]
    story.append(Table(
        total_rows,
        colWidths=[doc.width - 48 * mm, 48 * mm],
        hAlign="RIGHT",
        style=TableStyle([
            ("LINEABOVE", (1, len(total_rows) - 1), (1, len(total_rows) - 1),
             0.9, colors.HexColor(INK)),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]),
    ))

    # ── Notes and footer ────────────────────────────────────────────────────
    if po.notes:
        story.append(Spacer(1, 7 * mm))
        story.append(KeepTogether([
            Paragraph("NOTES", label),
            Spacer(1, 1.5 * mm),
            Paragraph(_esc(po.notes).replace("\n", "<br/>"), base),
        ]))

    story.append(Spacer(1, 9 * mm))
    footer = f"Purchase order {_esc(po.po_number)}"
    if po.status == "cancelled" and po.cancelled_at:
        # A cancelled order may well have been approved once. Leading with
        # "Approved ..." on it would be true and badly misleading.
        footer += f" &middot; Cancelled {po.cancelled_at.strftime('%d %b %Y')}"
    elif po.approved_at and po.status not in UNAUTHORIZED:
        footer += f" &middot; Approved {po.approved_at.strftime('%d %b %Y')}"
    if po.status in UNAUTHORIZED:
        footer += (" &middot; This document is not an authorization to supply "
                   "goods or services.")
    story.append(Paragraph(footer, small))

    doc.build(story, onLaterPages=_page_number, onFirstPage=_page_number)
    return buffer.getvalue()


def _meta_rows(present, label_style, base_style):
    """Lay the meta pairs out four to a row, label above value."""
    rows = []
    for index in range(0, len(present), 4):
        chunk = present[index:index + 4]
        padded = chunk + [("", "")] * (4 - len(chunk))
        rows.append([
            Paragraph(_esc(key).upper(), label_style) if key else Paragraph("", base_style)
            for key, _ in padded
        ])
        rows.append([
            Paragraph(_esc(str(value)), base_style) if value else Paragraph("", base_style)
            for _, value in padded
        ])
    return rows


def _page_number(canvas, doc):  # pragma: no cover - drawing callback
    canvas.saveState()
    canvas.setFont("Helvetica", 7.6)
    canvas.setFillColor(colors.HexColor(MUTED))
    canvas.drawRightString(
        doc.pagesize[0] - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}"
    )
    canvas.restoreState()


def _esc(value) -> str:
    """Escape for reportlab's mini-markup.

    Everything here is user-supplied - supplier names, line descriptions, notes
    - and reportlab parses its own tag subset, so an unescaped '<' in a
    description would either vanish or abort the whole render.
    """
    if value is None:
        return ""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
