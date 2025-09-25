from __future__ import annotations
import os, re
from .ollama_client import chat_ollama
from .focus_text import focus_text
from .utils_json import coerce_json

STAC_MODEL = os.getenv("STAC_MODEL", "medaudit:stac-fast")

def _pluck_json_like(s: str) -> str:
    # Оставляем как есть — иногда модель всё же даёт чистый JSON.
    # Эту функцию больше не используем напрямую для json.loads,
    # но пусть останется как «быстрый вырезатель» последнего {..}.
    m = re.search(r"\{.*\}\s*$", s, re.S)
    return m.group(0) if m else s

def _ensure_status(data: dict) -> dict:
    for it in data.get("passes", []):
        it.setdefault("status", "PASS")
    for it in data.get("violations", []):
        it.setdefault("status", "FAIL")
    return data

def audit_stac(text: str) -> dict:
    condensed = focus_text(text)
    raw = chat_ollama(
        system="",  # правила уже в модели
        question="Проверь документ по зашитым правилам (стационар + общие) и верни СТРОГО JSON.",
        text=condensed,
        model=STAC_MODEL,
        temperature=0.0,
        num_predict=int(os.getenv("NUM_PREDICT", "90")),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
        keep_alive=os.getenv("KEEP_ALIVE", "30m"),
        use_json_format=True,
        timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
    )

    # Надёжно извлечём JSON, даже если модель прислала «мусор» вокруг
    try:
        data = coerce_json(raw)
    except Exception as e:
        # Вернём диагностическую структуру - пусть фронт покажет «ошибку парсинга», не 500
        snippet = (raw or "")[:600]
        return {
            "doc_profile_hint": ["STAC", "GEN"],
            "passes": [],
            "violations": [],
            "parse_error": f"LLM returned non-JSON: {type(e).__name__}: {e}",
            "llm_raw_snippet": snippet
        }

    data.setdefault("passes", [])
    data.setdefault("violations", [])
    return _ensure_status(data)
