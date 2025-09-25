from pdfminer.high_level import extract_text
import tempfile, os, re

def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    if not pdf_bytes:
        return ""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tf:
        tf.write(pdf_bytes)
        tmp = tf.name
    try:
        try:
            text = extract_text(tmp) or ""
        except Exception:
            # иногда помогает второй проход
            text = extract_text(tmp) or ""
    finally:
        try: os.remove(tmp)
        except: pass
    return normalize_text(text)

def normalize_text(text: str) -> str:
    txt = (text or "").replace("\x00", " ")
    # сохраняем переносы для эвиденса, убираем лишние пробелы
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\r?\n[ \t]+", "\n", txt)
    return txt
