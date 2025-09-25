from __future__ import annotations
import re
from io import BytesIO
from typing import Optional

# быстрый: PyMuPDF
try:
    import fitz  # pip install pymupdf
except Exception:
    fitz = None

# фолбэки
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

def _normalize(text: str) -> str:
    if not text: return ""
    text = text.replace("\xa0", " ").replace("\x00", "")
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_text_from_pdf(blob: bytes, max_chars: Optional[int] = 200_000) -> str:
    text = ""
    if fitz is not None:
        try:
            doc = fitz.open(stream=blob, filetype="pdf")
            text = "\n\n".join(page.get_text("text") or "" for page in doc)
        except Exception:
            text = ""
    if not text and pdfminer_extract_text is not None:
        try:
            text = pdfminer_extract_text(BytesIO(blob)) or ""
        except Exception:
            text = ""
    if not text and PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(blob))
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception:
            text = ""
    text = _normalize(text)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text
