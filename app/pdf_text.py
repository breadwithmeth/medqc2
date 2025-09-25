from __future__ import annotations
import fitz  # PyMuPDF

def extract_text_from_pdf(blob: bytes) -> str:
    try:
        doc = fitz.open(stream=blob, filetype="pdf")
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
        txt = "\n".join(parts)
        return txt.strip()
    except Exception as e:
        return ""
