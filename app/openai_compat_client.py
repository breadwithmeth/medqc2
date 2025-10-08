# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

import requests


OPENAI_COMPAT_BASE_URL = os.getenv("OPENAI_COMPAT_BASE_URL", "https://api.openai.com")
OPENAI_COMPAT_API_KEY = os.getenv("OPENAI_API_KEY", "")


def _join_messages(system: str, question: str, text: str) -> list[dict]:
    msgs: list[dict] = []
    if system:
        msgs.append({"role": "system", "content": system})
    u = (question or "").strip() or "Проанализируй документ и верни строгий JSON."
    if text:
        u = f"{u}\n\n=== ДОКУМЕНТ ===\n{text}"
    msgs.append({"role": "user", "content": u})
    return msgs


def chat_openai_compat(
    system: str,
    question: str,
    text: str,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 800,
    top_p: Optional[float] = None,
    keep_alive: Optional[str] = None,  # не используется для openai-совместимого
    use_json_format: bool = True,
    timeout: int = 180,
    connect_timeout: int = 10,
    retries: int = 1,
) -> str:
    """
    Вызов OpenAI-совместимого /v1/chat/completions (OpenAI, Azure OpenAI, OpenRouter и пр.).
    Поддержка строгого JSON через response_format={"type":"json_object"} если use_json_format=True.
    """
    base = OPENAI_COMPAT_BASE_URL.rstrip("/")
    mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    headers = {
        "Authorization": f"Bearer {OPENAI_COMPAT_API_KEY}",
        "Content-Type": "application/json",
    }

    body: Dict[str, Any] = {
        "model": mdl,
        "messages": _join_messages(system, question, text),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if top_p is not None:
        body["top_p"] = float(top_p)
    # Можно отключить строгий JSON-ответ, если совместимый сервер не поддерживает response_format
    use_json_env = os.getenv("OPENAI_USE_JSON_OBJECT", "1").lower() in ("1", "true", "yes", "on")
    if use_json_format and use_json_env:
        # OpenAI/совместимые поддерживают строгий JSON через этот флаг
        body["response_format"] = {"type": "json_object"}

    last_err: Optional[Exception] = None
    for _ in range(max(1, retries + 1)):
        t0 = time.time()
        try:
            r = requests.post(
                f"{base}/v1/chat/completions",
                headers=headers,
                json=body,
                timeout=(connect_timeout, timeout),
            )
            dt = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                raise RuntimeError(f"OpenAI-compat {r.status_code}: {r.text[:400]}")
            data = r.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError(f"OpenAI-compat empty choices (dt={dt}ms)")
            msg = (choices[0].get("message") or {})
            content = msg.get("content") or ""
            if not content or not content.strip():
                raise RuntimeError(f"OpenAI-compat empty content (dt={dt}ms)")
            return content
        except Exception as e:
            last_err = e
            time.sleep(0.3)
    raise RuntimeError(f"OpenAI-compat error: {last_err}")


def ping_openai_compat() -> dict:
    ok, err, dt = False, "", 0
    try:
        t0 = time.time()
        # минимальный запрос с json_object
        _ = chat_openai_compat("system", "верни {\"ok\": true}", "", use_json_format=True, max_tokens=12, retries=0)
        dt = int((time.time() - t0) * 1000)
        ok = True
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
    return {
        "ok": ok,
        "duration_ms": dt,
        "base_url": OPENAI_COMPAT_BASE_URL,
        "model": os.getenv("OPENAI_MODEL", ""),
        "has_api_key": bool(OPENAI_COMPAT_API_KEY),
        "error": err,
    }
