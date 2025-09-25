# -*- coding: utf-8 -*-
from __future__ import annotations
import io, os, sys
from typing import Optional, List
from .pdf_ocr_fallback import has_tesseract, maybe_ocr_page_text

def extract_text_from_pdf(blob: bytes) -> str:
    """
    1) PyMuPDF постранично: собираем текст.
       Для страниц с «пустым» текстом — OCR (если включён и доступен).
    2) Если PyMuPDF целиком не сработал — fallback на pdfminer.six.
    """
    total = []
    used_ocr = 0
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=blob, filetype="pdf")
        use_ocr = bool(int(os.getenv("USE_OCR", "1"))) and has_tesseract()
        min_chars = int(os.getenv("OCR_MIN_CHARS", "60"))
        for i in range(doc.page_count):
            page = doc.load_page(i)
            t = page.get_text("text") or ""
            if use_ocr and (len((t or "").strip()) < min_chars):
                t2 = maybe_ocr_page_text(page, t)
                if t2 and len(t2.strip()) > len(t.strip()):
                    t = t2
                    used_ocr += 1
            total.append(t.strip())
        joined = "\n".join(total).strip()
        if len(joined) >= 10:
            if used_ocr:
                print(f"[pdf_text] OCR used on {used_ocr} pages", file=sys.stderr)
            return joined
    except Exception as e:
        print(f"[pdf_text] PyMuPDF failed: {e}", file=sys.stderr)

    # pdfminer fallback
    try:
        from pdfminer.high_level import extract_text
        text = (extract_text(io.BytesIO(blob)) or "").strip()
        if text:
            return text
    except Exception as e:
        print(f"[pdf_text] pdfminer failed: {e}", file=sys.stderr)

    # последняя надежда — чистый OCR первых N страниц (очень медленно, поэтому ограничено)
    if has_tesseract():
        try:
            import fitz
            doc = fitz.open(stream=blob, filetype="pdf")
            limit = min(doc.page_count, int(os.getenv("OCR_MAX_PAGES_DOC", "20")))
            agg = []
            for i in range(limit):
                page = doc.load_page(i)
                t = maybe_ocr_page_text(page, "", min_chars=999999)
                agg.append(t.strip())
            return "\n".join(agg).strip()
        except Exception as e:
            print(f"[pdf_text] emergency OCR failed: {e}", file=sys.stderr)
    return ""
