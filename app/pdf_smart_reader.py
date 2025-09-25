# -*- coding: utf-8 -*-
from __future__ import annotations
import io, re, os, sys
from typing import List, Tuple, Iterable, Dict, Any, Optional
from .pdf_ocr_fallback import has_tesseract, maybe_ocr_page_text

# ключевые маркеры для стационара
KEYWORDS = [
    r"при(е|ё)мн[ао]м?\s+отделен", r"осмотр\s+врача\s+отделен", r"первичн\w+\s+осмотр",
    r"обосновани[ея]\s+диагноз", r"предоперационн\w*\s+эпикриз",
    r"протокол\s+анестез", r"анестезиологическ\w*\s+пособи\w*",
    r"протокол\s+операц", r"послеоперационн\w*\s+дневник",
    r"предтрансфузионн\w*\s+эпикриз", r"консилиум",
    r"клинич\w*\s+диагноз", r"этапн\w*\s+эпикриз",
    r"выписн\w*\s+эпикриз", r"лист\s+назнач", r"диет[аы]\s*:", r"режим\s*:",
    r"сердечно[-\s]*легочн\w*\s+реанимац|СЛР"
]
KW_RE = re.compile("|".join(KEYWORDS), re.I)

def _estimate_tokens(chars: int) -> int:
    return max(1, chars // 4)

def _iter_page_texts_pymupdf(blob: bytes, use_ocr: bool) -> Iterable[Tuple[int, str]]:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=blob, filetype="pdf")
    for i in range(doc.page_count):
        page = doc.load_page(i)
        txt = page.get_text("text") or ""
        if use_ocr:
            txt = maybe_ocr_page_text(page, txt)
        yield i, txt

def _iter_page_texts_pdfminer(blob: bytes) -> Iterable[Tuple[int, str]]:
    from pdfminer.high_level import extract_text_to_fp
    from pdfminer.layout import LAParams
    buff = io.BytesIO()
    extract_text_to_fp(io.BytesIO(blob), buff, laparams=LAParams(), output_type="text", codec="utf-8")
    text = buff.getvalue().decode("utf-8", errors="ignore")
    pages = text.split("\x0c")
    for i, p in enumerate(pages):
        yield i, p or ""

def iter_page_texts(blob: bytes, use_ocr: bool = True) -> Iterable[Tuple[int, str]]:
    # сначала PyMuPDF (быстро), по страницам с опциональным OCR
    try:
        yield from _iter_page_texts_pymupdf(blob, use_ocr=use_ocr and bool(int(os.getenv("USE_OCR", "1"))))
        return
    except Exception as e:
        print(f"[pdf_smart_reader] PyMuPDF failed: {e}", file=sys.stderr)
    # fallback pdfminer (без OCR, но даёт текст если он встроен)
    try:
        yield from _iter_page_texts_pdfminer(blob)
    except Exception as e:
        print(f"[pdf_smart_reader] pdfminer failed: {e}", file=sys.stderr)
        yield from []

def find_relevant_pages(blob: bytes, neighbor: int = 1, max_pages: int = 40) -> List[int]:
    hits: List[int] = []
    # первичный проход (без принудительного OCR, но с локальным на «пустых» страницах)
    for i, txt in iter_page_texts(blob, use_ocr=True):
        if KW_RE.search(txt or ""):
            hits.append(i)

    if not hits:
        # вторичный выборочный OCR-поиск (если тессеракт есть)
        if has_tesseract():
            step = int(os.getenv("OCR_SAMPLING_STEP", "10"))
            sec_max = int(os.getenv("OCR_SECOND_PASS_PAGES", "30"))
            checked = 0
            import fitz
            doc = fitz.open(stream=blob, filetype="pdf")
            for i in range(0, doc.page_count, max(1, step)):
                if checked >= sec_max:
                    break
                page = doc.load_page(i)
                # принудительный OCR этой страницы
                txt = maybe_ocr_page_text(page, "", min_chars=999999)  # заставим OCR
                if KW_RE.search(txt or ""):
                    hits.append(i)
                checked += 1

    if not hits:
        # ничего не нашли — возьмём обложку/хвост/середину
        fallback = {0, 1, 2, 3, 4, -1, -2, -3}
        return sorted([p if p >= 0 else 0 for p in fallback])[:max_pages]

    # добавим соседние
    ext = set()
    for h in hits:
        for j in range(h - neighbor, h + neighbor + 1):
            if j >= 0:
                ext.add(j)
    pages = sorted(list(ext))
    return pages[:max_pages]

def extract_text_from_pages(blob: bytes, pages: List[int], join_with_headers: bool = True) -> str:
    out: List[str] = []
    pages_set = set(pages)
    for i, txt in iter_page_texts(blob, use_ocr=True):
        if i in pages_set:
            if join_with_headers:
                out.append(f"\n===== СТРАНИЦА {i+1} =====\n")
            out.append((txt or "").strip())
    return "\n".join(out).strip()

def smart_focus_for_llm(blob: bytes,
                        ctx_limit: int = None,
                        safety_ratio: float = 0.7,
                        neighbor: int = 1,
                        max_pages: int = None) -> Dict[str, Any]:
    ctx_limit = ctx_limit or int(os.getenv("OLLAMA_NUM_CTX", "3072"))
    max_pages = max_pages or int(os.getenv("FOCUS_MAX_PAGES", "40"))
    neighbor = int(os.getenv("FOCUS_NEIGHBOR", str(neighbor)))

    pages = find_relevant_pages(blob, neighbor=neighbor, max_pages=max_pages)
    focused = extract_text_from_pages(blob, pages)
    tokens = _estimate_tokens(len(focused))

    max_tokens = int(ctx_limit * safety_ratio)
    if tokens > max_tokens:
        max_chars = max_tokens * 4
        focused = focused[:max_chars]
        tokens = _estimate_tokens(len(focused))
        reduced = True
    else:
        reduced = False

    return {
        "focused_text": focused,
        "token_estimate": tokens,
        "pages_used": pages,
        "was_reduced": reduced
    }

def chunk_text(text: str, max_chars: int = 12000, overlap: int = 800) -> List[str]:
    if not text:
        return []
    res: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + max_chars)
        res.append(text[i:j])
        if j >= n:
            break
        i = j - overlap
        if i < 0:
            i = 0
    return res
