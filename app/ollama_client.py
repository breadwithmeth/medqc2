# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

import requests

# Базовый URL Ollama (GPU-сервер)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")


def _join_messages(system: str, question: str, text: str) -> list[dict]:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    u = (question or "").strip() or "Проверь документ и верни требуемый JSON."
    if text:
        u = f"{u}\n\n=== ДОКУМЕНТ ===\n{text}"
    msgs.append({"role": "user", "content": u})
    return msgs


def chat_ollama(
    system: str,
    question: str,
    text: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    num_predict: int = 512,
    num_ctx: int = 3072,
    keep_alive: str = "30m",
    use_json_format: bool = False,
    timeout: int = 180,
    connect_timeout: int = 5,
    retries: int = 1,
    grammar: Optional[str] = None,
    json_schema: Optional[dict] = None,
) -> str:
    """
    Универсальный вызов Ollama /api/chat.
    Приоритет вывода: JSON-Schema > grammar > format=json.
    """
    mdl = model or os.getenv("STAC_MODEL", "gpt-oss:latest")

    body: Dict[str, Any] = {
        "model": mdl,
        "messages": _join_messages(system, question, text),
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
        "keep_alive": keep_alive,
        "stream": False,
    }

    # Дополнительные тюнинги через окружение (если заданы)
    try:
        _top_p = os.getenv("OLLAMA_TOP_P")
        if _top_p is not None:
            body["options"]["top_p"] = float(_top_p)
    except Exception:
        pass
    try:
        _top_k = os.getenv("OLLAMA_TOP_K")
        if _top_k is not None:
            body["options"]["top_k"] = int(_top_k)
    except Exception:
        pass
    try:
        _rp = os.getenv("OLLAMA_REPEAT_PENALTY")
        if _rp is not None:
            body["options"]["repeat_penalty"] = float(_rp)
    except Exception:
        pass

    if json_schema is not None:
        body["format"] = json_schema
    elif grammar:
        body["options"]["grammar"] = grammar
    elif use_json_format:
        body["format"] = "json"

    # Возможность принудительно использовать /api/generate вместо /api/chat
    use_chat_env = os.getenv("OLLAMA_USE_CHAT", "1").lower() in ("1", "true", "yes", "on")
    if not use_chat_env and json_schema is None and grammar is None:
        return generate_ollama(system, question, text, mdl, body.get("options", {}), keep_alive, timeout, connect_timeout, retries)

    last_err: Optional[Exception] = None
    for _ in range(max(1, retries + 1)):
        t0 = time.time()
        try:
            r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(connect_timeout, timeout))
            dt = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                raise RuntimeError(f"Ollama {r.status_code}: {r.text[:400]}")
            payload = r.json()
            msg = (payload.get("message") or {})
            content = msg.get("content") or payload.get("content") or ""
            if not content:
                raise RuntimeError(f"Ollama empty content (dt={dt}ms, model={mdl})")
            return content
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise RuntimeError(f"Ollama error: {last_err}")


def generate_ollama(
    system: str,
    question: str,
    text: str,
    model: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
    keep_alive: str = "30m",
    timeout: int = 180,
    connect_timeout: int = 5,
    retries: int = 1,
) -> str:
    """
    Вызов Ollama /api/generate. Собирает prompt из system + question + text. Без structured outputs.
    Используйте как фолбэк, если /api/chat даёт пустые ответы на некоторых моделях (например, gpt-oss).
    """
    mdl = model or os.getenv("STAC_MODEL", "gpt-oss:latest")
    prompt_parts = []
    if system:
        prompt_parts.append(system)
    if question:
        prompt_parts.append(question)
    if text:
        prompt_parts.append("=== ДОКУМЕНТ ===\n" + text)
    prompt = "\n\n".join(p.strip() for p in prompt_parts if p.strip())

    body: Dict[str, Any] = {
        "model": mdl,
        "prompt": prompt,
        "options": options or {},
        "keep_alive": keep_alive,
        "stream": False,
    }

    last_err: Optional[Exception] = None
    for _ in range(max(1, retries + 1)):
        try:
            r = requests.post(f"{OLLAMA_URL}/api/generate", json=body, timeout=(connect_timeout, timeout))
            if r.status_code != 200:
                raise RuntimeError(f"Ollama generate {r.status_code}: {r.text[:400]}")
            payload = r.json()
            content = payload.get("response") or payload.get("content") or ""
            if not content:
                raise RuntimeError("Ollama generate empty content")
            return content
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise RuntimeError(f"Ollama generate error: {last_err}")


def get_tags(timeout: int = 5, connect_timeout: int = 3) -> dict:
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=(connect_timeout, timeout))
    r.raise_for_status()
    return r.json()


def schema_smoke_test(timeout: int = 12, connect_timeout: int = 3) -> bool:
    """
    Проверяет поддержку structured outputs (JSON-Schema) у текущей версии Ollama.
    """
    body = {
    "model": os.getenv("STAC_MODEL", "gpt-oss:latest"),
        "messages": [{"role": "user", "content": "schema test"}],
        "format": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
        "stream": False,
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(connect_timeout, timeout))
        r.raise_for_status()
        data = r.json()
        msg = (data.get("message") or {})
        content = msg.get("content") or ""
        # Ожидаем {"ok": true}
        return content.strip().startswith("{") and '"ok"' in content
    except Exception:
        return False


def quick_ping() -> dict:
    """
    Мини-пинг к модели: проверяет доступность и базовый JSON-ответ (через минимальную схему).
    """
    ok = False
    err = ""
    dt = 0
    try:
        t0 = time.time()
        body = {
            "model": os.getenv("STAC_MODEL", "gpt-oss:latest"),
            "messages": [{"role": "user", "content": "ping"}],
            "format": {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]},
            "stream": False,
        }
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(5, 12))
        dt = int((time.time() - t0) * 1000)
        r.raise_for_status()
        payload = r.json()
        msg = (payload.get("message") or {})
        content = msg.get("content") or ""
        ok = content.strip().startswith("{") and '"ok"' in content
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return {"ok": ok, "duration_ms": dt, "model": os.getenv("STAC_MODEL", ""), "error": err}
    return {"ok": ok, "duration_ms": dt, "model": os.getenv("STAC_MODEL", "")}


def grammar_smoke_test(timeout: int = 12, connect_timeout: int = 3) -> bool:
    """
    Быстрая проверка поддержки grammar: навязываем минимальный JSON {"ok": true}.
    Если сервер/модель игнорирует grammar, вернётся произвольный текст.
    """
    GRAMMAR = r'''
root ::= ws obj ws
obj  ::= "{" ws "\"ok\"" ws ":" ws "true" ws "}"
ws   ::= ([ \t\n\r])*
'''
    body = {
        "model": os.getenv("STAC_MODEL", "gpt-oss:latest"),
        "messages": [{"role": "user", "content": "grammar test"}],
        "options": {"grammar": GRAMMAR},
        "stream": False,
    }
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(connect_timeout, timeout))
        r.raise_for_status()
        data = r.json()
        msg = (data.get("message") or {})
        content = msg.get("content") or ""
        s = content.strip()
        return s.startswith("{") and '"ok"' in s and 'true' in s
    except Exception:
        return False
