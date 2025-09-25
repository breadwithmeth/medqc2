# -*- coding: utf-8 -*-
from __future__ import annotations
import json, re

CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)
TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")

def _strip_code_fences(s: str) -> str:
    return CODE_FENCE_RE.sub("", s or "").strip()

def _extract_balanced_json(s: str) -> str | None:
    """
    Берём самую большую сбалансированную {}-скобочную область.
    """
    first = s.find("{")
    if first < 0:
        return None
    stack = 0
    end = -1
    for i, ch in enumerate(s[first:], start=first):
        if ch == "{":
            stack += 1
        elif ch == "}":
            stack -= 1
            if stack == 0:
                end = i
                break
    if end > first:
        return s[first:end+1]
    return None

def _fix_trailing_commas(s: str) -> str:
    # ", }" или ", ]" -> "}" / "]"
    return TRAILING_COMMA_RE.sub(r"\1", s)

def _sanitize(s: str) -> str:
    s = s.replace("\r", "")
    # убрать невидимые BOM/zero-width
    s = s.replace("\ufeff", "").replace("\u200b", "")
    return s

def coerce_json(raw: str) -> dict:
    """
    Пытается распарсить ответ модели в dict.
    1) прямой json.loads
    2) снять код-блоки и попробовать снова
    3) вытащить сбалансированный {...}
    4) поправить висячие запятые
    Если всё плохо — поднимает ValueError с усечённым фрагментом.
    """
    if not raw:
        raise ValueError("empty LLM content")
    txt = _sanitize(raw)

    # 1) строгий парс
    try:
        return json.loads(txt)
    except Exception:
        pass

    # 2) без код-блоков
    txt2 = _strip_code_fences(txt)
    try:
        return json.loads(txt2)
    except Exception:
        pass

    # 3) largest balanced {...}
    blob = _extract_balanced_json(txt2)
    if blob:
        try:
            return json.loads(blob)
        except Exception:
            # 4) починка висячих запятых
            fixed = _fix_trailing_commas(blob)
            try:
                return json.loads(fixed)
            except Exception as e:
                raise ValueError(f"json parse failed after repair: {e}; snippet={fixed[:200]!r}")

    # крайний случай: ещё раз попробуем убрать висячие запятые из всего текста
    fixed2 = _fix_trailing_commas(txt2)
    try:
        return json.loads(fixed2)
    except Exception as e:
        raise ValueError(f"json parse failed: {e}; raw_snippet={txt[:200]!r}")
