"""Extract plain text from uploaded documents.

Supported: PDF, Word (.docx), Excel (.xlsx/.xls), CSV, and plain text/Markdown.
The heavy parsers (pypdf, python-docx, openpyxl) are optional imports: if one
isn't installed we return a clear, actionable message for that file type
instead of crashing.

Extraction is deliberately dependency-light and produces clean-ish text that
the DSPy `CompileNote` module then turns into a structured Markdown note.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from pathlib import Path

# Only extract a bounded amount of text so a giant file can't blow up the
# model context or memory. The compiler further truncates / map-reduces.
MAX_CHARS = 200_000


@dataclass
class Extracted:
    filename: str
    kind: str          # "pdf" | "docx" | "xlsx" | "csv" | "text"
    text: str
    meta: dict         # e.g. {"pages": 12} or {"sheets": ["Sheet1"]}


class UnsupportedFile(Exception):
    pass


class MissingParser(Exception):
    """Raised when the optional library for a file type isn't installed."""


def _extract_pdf(data: bytes) -> tuple[str, dict]:
    try:
        from pypdf import PdfReader
    except Exception as exc:  # pragma: no cover - env dependent
        raise MissingParser(
            "PDF support needs `pypdf` (pip install pypdf)."
        ) from exc
    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            parts.append("")
    return "\n\n".join(parts), {"pages": len(reader.pages)}


def _extract_docx(data: bytes) -> tuple[str, dict]:
    try:
        import docx  # python-docx
    except Exception as exc:  # pragma: no cover - env dependent
        raise MissingParser(
            "Word support needs `python-docx` (pip install python-docx)."
        ) from exc
    document = docx.Document(io.BytesIO(data))
    parts = [p.text for p in document.paragraphs if p.text.strip()]
    # Include tables as pipe-separated rows.
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts), {"paragraphs": len(document.paragraphs)}


def _extract_xlsx(data: bytes) -> tuple[str, dict]:
    try:
        from openpyxl import load_workbook
    except Exception as exc:  # pragma: no cover - env dependent
        raise MissingParser(
            "Excel support needs `openpyxl` (pip install openpyxl)."
        ) from exc
    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts = []
    for ws in wb.worksheets:
        parts.append(f"## Sheet: {ws.title}")
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts), {"sheets": wb.sheetnames}


def _extract_csv(data: bytes) -> tuple[str, dict]:
    text = data.decode("utf-8", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    lines = [" | ".join(r) for r in rows if any(cell.strip() for cell in r)]
    return "\n".join(lines), {"rows": len(rows)}


def extract(filename: str, data: bytes) -> Extracted:
    """Dispatch on file extension and return extracted text."""
    suffix = Path(filename).suffix.lower()

    if suffix == ".pdf":
        text, meta = _extract_pdf(data)
        kind = "pdf"
    elif suffix in {".docx", ".doc"}:
        text, meta = _extract_docx(data)
        kind = "docx"
    elif suffix in {".xlsx", ".xlsm", ".xls"}:
        text, meta = _extract_xlsx(data)
        kind = "xlsx"
    elif suffix == ".csv":
        text, meta = _extract_csv(data)
        kind = "csv"
    elif suffix in {".txt", ".md", ".markdown", ".rst", ".log", ""}:
        text, meta = data.decode("utf-8", errors="replace"), {}
        kind = "text"
    else:
        raise UnsupportedFile(
            f"Unsupported file type '{suffix}'. "
            "Supported: PDF, Word (.docx), Excel (.xlsx), CSV, text/Markdown."
        )

    text = (text or "").strip()
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS] + "\n\n[…truncated…]"
    return Extracted(filename=filename, kind=kind, text=text, meta=meta)
