# app/utils_json.py
from __future__ import annotations
import json
import re
from typing import Optional


def _extract_from_fence(s: str) -> Optional[str]:
    """Вытащить JSON из блока ```json ... ``` или ``` ... ```."""
    # ```json ... ```
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.S | re.I)
    if m:
        return m.group(1).strip()
    # ``` ... ```
    m = re.search(r"```\s*(\{.*?\})\s*```", s, re.S)
    if m:
        return m.group(1).strip()
    return None


def _extract_balanced_object(s: str) -> Optional[str]:
    """Найти первый сбалансированный JSON-объект { ... } с учётом кавычек/эскейпов."""
    start = s.find("{")
    if start == -1:
        return None

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return s[start : i + 1]
    return None


def _sanitize(s: str) -> str:
    """Небольшая санитарная обработка, не ломающая корректный JSON."""
    # вырежем нулевые байты/управляющие, лишние \x0b и т.п.
    s = s.replace("\x00", " ").replace("\x0b", " ").replace("\x0c", " ")
    # уберём невидимые теги markdown вне фигурных скобок (редко)
    s = s.strip()
    return s


def coerce_json(s: str) -> dict:
    """
    Попробовать распарсить ответ модели к dict:
    1) прямая попытка json.loads
    2) из ```json ... ```
    3) из сбалансированного блока {...}
    4) после незначительной санации
    Бросает ValueError, если не удалось.
    """
    if not s:
        raise ValueError("empty response")

    # Быстрый путь
    try:
        return json.loads(s)
    except Exception:
        pass

    # Попробовать вытащить из ```json ... ```
    fenced = _extract_from_fence(s)
    if fenced:
        try:
            return json.loads(fenced)
        except Exception:
            # попробуем ещё и сбалансированный поиск внутри fenced
            inner = _extract_balanced_object(fenced)
            if inner:
                return json.loads(inner)

    # Попробовать сбалансированный поиск в целом ответе
    balanced = _extract_balanced_object(s)
    if balanced:
        try:
            return json.loads(balanced)
        except Exception:
            # финальная попытка — легкая санация
            balanced2 = _sanitize(balanced)
            return json.loads(balanced2)

    # Санируем и снова пытаемся прямой парс
    s2 = _sanitize(s)
    return json.loads(s2)
