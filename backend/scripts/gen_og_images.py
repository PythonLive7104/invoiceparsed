"""Generate branded placeholder OG/social images + logo for InvoiceParsed.

These are functional placeholders (correct dimensions, on-brand colours and
wordmark) so meta/schema image references resolve and social cards render.
Swap them for designed assets before a big launch.

    python scripts/gen_og_images.py
"""
import os

from PIL import Image, ImageDraw, ImageFont

# Brand palette (matches the app's dark theme).
INK = (11, 15, 26)        # #0b0f1a
PANEL = (15, 20, 34)      # #0f1422
WHITE = (255, 255, 255)
BRAND = (129, 140, 248)   # #818cf8 (indigo-400)
MUTED = (148, 163, 184)   # slate-400

FRONTEND_PUBLIC = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public")
)


def _font(size, bold=True):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _wordmark(draw, x, y, size):
    """Draw 'Invoice' (white) + 'Parsed' (brand) at (x, y)."""
    f = _font(size)
    draw.text((x, y), "Invoice", font=f, fill=WHITE)
    w = draw.textlength("Invoice", font=f)
    draw.text((x + w, y), "Parsed", font=f, fill=BRAND)
    return f


def og_image(path, title, subtitle):
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), INK)
    d = ImageDraw.Draw(img)

    # Subtle panel + accent bar.
    d.rounded_rectangle([48, 48, W - 48, H - 48], radius=28, fill=PANEL)
    d.rectangle([48, 48, 60, H - 48], fill=BRAND)

    _wordmark(d, 96, 110, 52)

    # Title (wrap by hand at ~22 chars/line).
    tf = _font(64)
    words, line, lines = title.split(), "", []
    for word in words:
        trial = (line + " " + word).strip()
        if d.textlength(trial, font=tf) > W - 220:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    y = 230
    for ln in lines:
        d.text((96, y), ln, font=tf, fill=WHITE)
        y += 78

    d.text((96, H - 150), subtitle, font=_font(30, bold=False), fill=MUTED)

    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG")
    print("✓", path)


def logo(path, size=512):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size, size], radius=int(size * 0.22), fill=PANEL)
    d.rounded_rectangle([0, 0, size, size], radius=int(size * 0.22), outline=BRAND, width=8)
    # Big "IP" monogram.
    f = _font(int(size * 0.42))
    text = "IP"
    tw = d.textlength(text, font=f)
    bbox = d.textbbox((0, 0), text, font=f)
    th = bbox[3] - bbox[1]
    d.text(((size - tw) / 2, (size - th) / 2 - bbox[1]), "I", font=f, fill=WHITE)
    iw = d.textlength("I", font=f)
    d.text(((size - tw) / 2 + iw, (size - th) / 2 - bbox[1]), "P", font=f, fill=BRAND)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, "PNG")
    print("✓", path)


if __name__ == "__main__":
    pub = FRONTEND_PUBLIC
    og_image(
        os.path.join(pub, "og", "invoiceparsed-og.png"),
        "AI invoice data extraction",
        "Turn any invoice PDF or image into clean JSON or CSV in seconds.",
    )
    og_image(
        os.path.join(pub, "og", "blog", "extract-invoice-pdf.png"),
        "How to extract data from an invoice PDF",
        "A 2026 guide · InvoiceParsed",
    )
    og_image(
        os.path.join(pub, "og", "blog", "invoice-ocr-tools.png"),
        "7 best invoice OCR tools in 2026",
        "Compared · InvoiceParsed",
    )
    logo(os.path.join(pub, "logo-512.png"))
