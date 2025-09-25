# -*- coding: utf-8 -*-
from __future__ import annotations
import io, os, sys
from typing import Optional
from PIL import Image, ImageOps, ImageFilter

# мягкая проверка наличия pytesseract и бинарника tesseract
def has_tesseract() -> bool:
    try:
        import pytesseract as _pt  # noqa
    except Exception:
        return False
    # доп.проверка на бинарник
    from shutil import which
    return which("tesseract") is not None

def _pil_from_fitz_pixmap(pixmap) -> Image.Image:
    mode = "RGBA" if pixmap.alpha else "RGB"
    img = Image.frombytes(mode, [pixmap.width, pixmap.height], pixmap.samples)
    if mode == "RGBA":
        img = img.convert("RGB")
    return img

def _preprocess(img: Image.Image) -> Image.Image:
    # базовая обработка: контраст, бимодальное порог. без OpenCV
    g = ImageOps.grayscale(img)
    # лёгкое повышение резкости и контраста
    g = g.filter(ImageFilter.MedianFilter(size=3))
    g = ImageOps.autocontrast(g, cutoff=2)
    return g

def ocr_image(img: Image.Image, lang: Optional[str] = None) -> str:
    try:
        import pytesseract as pt
    except Exception:
        return ""
    lang = lang or os.getenv("OCR_LANGS", "rus+kaz+eng")
    try:
        text = pt.image_to_string(img, lang=lang, config="--psm 4")
    except Exception as e:
        print(f"[OCR] pytesseract error: {e}", file=sys.stderr)
        return ""
    # легкая пост-обработка
    text = text.replace("-\n", "").replace("\r", "")
    return text

def ocr_page_fitz(page, dpi: int = 300, lang: Optional[str] = None) -> str:
    """
    Рендерим страницу PyMuPDF → PIL → OCR. dpi=300 по умолчанию.
    """
    try:
        import fitz  # noqa
    except Exception:
        return ""
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pm = page.get_pixmap(matrix=mat, alpha=False)  # без альфы → быстрее
    img = _pil_from_fitz_pixmap(pm)
    img = _preprocess(img)
    return ocr_image(img, lang=lang)

def maybe_ocr_page_text(page, current_text: str, min_chars: int = 60, dpi: int = 300, lang: Optional[str] = None) -> str:
    """
    Если текущий текст короткий — включаем OCR. Иначе возвращаем current_text.
    """
    txt = (current_text or "").strip()
    if len(txt) >= int(os.getenv("OCR_MIN_CHARS", str(min_chars))):
        return current_text
    if not has_tesseract():
        return current_text
    return ocr_page_fitz(page, dpi=int(os.getenv("OCR_DPI", str(dpi))), lang=lang)
