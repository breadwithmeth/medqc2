# app/pdf_text.py
from __future__ import annotations
import re
from io import BytesIO
from typing import Optional

# Основной парсер — pdfminer.six
try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text
except Exception:
    pdfminer_extract_text = None  # type: ignore

# Фолбэк — pypdf (бывш. PyPDF2)
try:
    from pypdf import PdfReader  # pip install pypdf
except Exception:
    PdfReader = None  # type: ignore


def _normalize(text: str) -> str:
    """Чистим и нормализуем текст после извлечения."""
    if not text:
        return ""
    # неразрывные пробелы → обычные
    text = text.replace("\xa0", " ")
    # убираем \x00 и прочий мусор
    text = text.replace("\x00", "")
    # склейка переноcов со знаком дефиса: "га-\nстро" -> "гастро"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    # нормальные переводы строк
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # сжимаем избыточные пробелы
    text = re.sub(r"[ \t]+", " ", text)
    # сжимаем пустые строки до максимум одной
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_text_from_pdf(blob: bytes, max_chars: Optional[int] = 250_000) -> str:
    """
    Возвращает нормализованный текст из PDF (bytes).
    По умолчанию ограничиваем результат ~250k символов (чтобы не упираться в контекст модели).
    """
    text = ""

    # 1) pdfminer — лучший по качеству извлечения
    if pdfminer_extract_text is not None:
        try:
            text = pdfminer_extract_text(BytesIO(blob)) or ""
        except Exception:
            text = ""

    # 2) Фолбэк — pypdf, если pdfminer не сработал/не установлен
    if not text and PdfReader is not None:
        try:
            reader = PdfReader(BytesIO(blob))
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            text = "\n\n".join(pages)
        except Exception:
            text = ""

    if not text:
        # Ничего не смогли извлечь
        return ""

    text = _normalize(text)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars]
    return text
