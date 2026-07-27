"""Phase 5b.2 OCR parser for image-only PDFs.

Some bank statements (older ones, especially from smaller credit unions)
are scanned PDFs \u2014 they have NO text layer. ``pdfplumber`` returns
``record_count == 0`` for these, and the core ``parse_pdf_file`` doesn't
extract anything. Phase 5b.2 adds this OCR parser that:

1. Opens the PDF with pdfplumber.
2. For each page, rasterises via ``page.to_image(resolution=300)``
   (gives tesseract a high-quality input).
3. Runs ``pytesseract.image_to_string()`` on each rendered image.
4. Returns the concatenated text lines under the same response shape
   as ``parse_pdf_file`` (file_type='pdf', record_count=N, preview=...).

The OCR output is NOT a structured table \u2014 tesseract returns a string
that needs further parsing (Phase 5b.3 lift). Phase 5b.2 ships as
**preview-only**; once the text is in the DB, Phase 5b.3 lifts a
heuristic line-parser.

When to use this parser:

- The Phase 5 routes/imports.py calls ``parse_uploaded_statement`` first.
- If that returns ``record_count == 0`` (text-less PDF), the route
  falls back to ``ocr_parse_statement`` (defined below).
- Caller is ``routes/imports.py::upload_statement`` \u2014 see the
  ``try_ocr_fallback`` branch in that route.

Tests:

- ``tests/test_ocr_parser.py`` uses pypdf + Pillow to render an image
  to a PDF on the fly so we test the real pdfplumber \u2192 pytesseract
  integration without a 50+ MB fixture file.
"""
import shutil
from typing import Any

import pdfplumber
import pytesseract


def ocr_parse_statement(upload_file: Any) -> dict[str, Any]:
    """OCR fallback for image-only PDFs.

    Returns the same response shape as ``parse_pdf_file``:
    ``{file_type, record_count, preview, filename}``. ``record_count``
    is the count of non-blank OCR-output lines; ``preview`` is the
    first 10 of those lines.

    Falls through with ``record_count == 0`` only if pytesseract can't
    read any text (e.g., the PDF is actually a corrupt or empty scan).
    In that case callers should surface \"Could not OCR statement\" to
    the user.
    """
    # Probe the tesseract binary early so the user gets a clear,
    # actionable error message ("server is missing the tesseract
    # binary") instead of a confusing pytesseract stack trace when
    # tesseract isn't on the system PATH. shutil.which returns None
    # for "not found"; passing the explicit binary path to
    # pytesseract.image_to_string surfaces a clean error too.
    if shutil.which("tesseract") is None:
        raise ValueError(
            "Tesseract OCR is not installed on the server. "
            "Install with `brew install tesseract` (macOS) or "
            "`apt-get install -y tesseract-ocr` (Linux) and restart "
            "the rules-service."
        )

    upload_file.file.seek(0)
    try:
        rendered_lines: list[str] = []
        with pdfplumber.open(upload_file.file) as pdf:
            for page in pdf.pages:
                # ``to_image`` returns a ``PIL.Image`` at the requested
                # resolution; 300 DPI is the SWEET SPOT for tesseract
                # accuracy without blowing memory.
                page_image = page.to_image(resolution=300)
                page_text = pytesseract.image_to_string(page_image.original)
                rendered_lines.extend(
                    [line.strip() for line in page_text.splitlines() if line.strip()]
                )
    except pytesseract.TesseractNotFoundError as exc:
        # Defensive — the PATH probe above should catch this, but if
        # tesseract disappears at runtime we still surface a friendly
        # message instead of pytesseract's "TesseractNotFoundError".
        raise ValueError(
            "Tesseract OCR is not installed on the server. "
            "Install with `brew install tesseract` (macOS) or "
            "`apt-get install -y tesseract-ocr` (Linux) and restart "
            "the rules-service."
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        # Narrow catch: surface a clear "OCR failed" message for the
        # common pdfplumber/tesseract error surfaces (rasterisation
        # raises RuntimeError, missing binary raises OSError, malformed
        # content raises ValueError) WITHOUT masking unrelated bugs.
        # ``TesseractNotFoundError`` is an ``OSError`` subclass so it's
        # covered here too — but it's caught above to surface the
        # actionable brew/apt install hint instead of a generic
        # "OCR failed" message.
        raise ValueError(f"Could not OCR PDF file: {exc}")

    preview = rendered_lines[:10]
    return {
        "file_type": "pdf",
        "record_count": len(rendered_lines),
        "preview": preview,
        # Phase 8.1: expose the FULL OCR-extracted line list (not just
        # ``preview[:10]``) so the route layer can run the heuristic
        # PDF\u2192transaction parser on every line. ``preview`` is
        # preserved for backwards compatibility (clients reading it
        # still see the first 10 lines for display).
        "text_lines": rendered_lines,
        "filename": upload_file.filename,
        "ocr": True,  # marker so callers know this came through OCR (vs text-layer)
    }
