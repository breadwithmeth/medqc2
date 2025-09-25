# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re

CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I | re.M)
TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _strip_code_fences(s: str) -> str:
    return CODE_FENCE_RE.sub("", s or "").strip()


def _extract_balanced_json_strict(s: str) -> str | None:
    """
    Ищем самую длинную сбалансированную {}-структуру, учитывая строки и экранирование.
    """
    i = 0
    n = len(s)
    best = None
    while i < n:
        if s[i] == "{":
            depth = 0
            j = i
            in_str = False
            esc = False
            while j < n:
                ch = s[j]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == "\"":
                        in_str = False
                else:
                    if ch == "\"":
                        in_str = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            cand = s[i : j + 1]
                            if best is None or len(cand) > len(best):
                                best = cand
                            break
                j += 1
        i += 1
    return best


def _fix_trailing_commas(s: str) -> str:
    # ", }" или ", ]" -> "}" или "]"
    return TRAILING_COMMA_RE.sub(r"\1", s)


def _sanitize(s: str) -> str:
    return (s or "").replace("\r", "").replace("\ufeff", "").replace("\u200b", "").strip()


def coerce_json(raw: str) -> dict:
    """
    Стабильный «ремонтный» парсер ответа LLM → dict.
    Порядок попыток:
      1) прямой json.loads
      2) снять ```json-ограждения
      3) вырезать самый длинный сбалансированный {...}
      4) фиксануть висячие запятые
    """
    if not raw:
        raise ValueError("empty LLM content")

    txt = _sanitize(raw)

    try:
        return json.loads(txt)
    except Exception:
        pass

    txt2 = _strip_code_fences(txt)
    try:
        return json.loads(txt2)
    except Exception:
        pass

    blob = _extract_balanced_json_strict(txt2)
    if blob:
        try:
            return json.loads(blob)
        except Exception:
            fixed = _fix_trailing_commas(blob)
            try:
                return json.loads(fixed)
            except Exception as e:
                raise ValueError(f"json parse failed after repair: {e}; snippet={fixed[:220]!r}")

    fixed2 = _fix_trailing_commas(txt2)
    try:
        return json.loads(fixed2)
    except Exception as e:
        raise ValueError(f"json parse failed: {e}; raw_snippet={txt[:220]!r}")


def is_likely_truncated_json(txt: str) -> bool:
    """
    Грубая эвристика: начинаем с '{', но суммарно скобки не сошлись.
    Игнорируем символы внутри строк с экранированием.
    """
    s = (txt or "").strip()
    if not s.startswith("{"):
        return False
    depth = 0
    in_str = False
    esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == "\"":
                in_str = False
        else:
            if ch == "\"":
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    # нашли закрывающую скобку всего объекта — не обрезан
                    return False
    # дошли до конца без depth==0 -> похоже, оборванный
    return True