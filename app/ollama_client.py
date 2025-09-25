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
    mdl = model or os.getenv("STAC_MODEL", "medaudit:stac-strict")

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

    if json_schema is not None:
        body["format"] = json_schema
    elif grammar:
        body["options"]["grammar"] = grammar
    elif use_json_format:
        body["format"] = "json"

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
                raise RuntimeError(f"Ollama empty content (dt={dt}ms)")
            return content
        except Exception as e:
            last_err = e
            time.sleep(0.2)
    raise RuntimeError(f"Ollama error: {last_err}")


def get_tags(timeout: int = 5, connect_timeout: int = 3) -> dict:
    r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=(connect_timeout, timeout))
    r.raise_for_status()
    return r.json()


def schema_smoke_test(timeout: int = 12, connect_timeout: int = 3) -> bool:
    """
    Проверяет поддержку structured outputs (JSON-Schema) у текущей версии Ollama.
    """
    body = {
        "model": os.getenv("STAC_MODEL", "llama3.1:8b-instruct-q4_0"),
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
            "model": os.getenv("STAC_MODEL", "llama3.1:8b-instruct-q4_0"),
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
        return {"ok": ok, "duration_ms": dt, "model": os.getenv("STAC_MODEL", "")}
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        return {"ok": ok, "duration_ms": dt, "model": os.getenv("STAC_MODEL", ""), "error": err}
