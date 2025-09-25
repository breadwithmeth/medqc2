# -*- coding: utf-8 -*-
from __future__ import annotations
import os, sys, time, json
from typing import Optional, Dict, Any
import requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

def _join_messages(system: str, question: str, text: str) -> list[dict]:
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    # чтобы модель видела и вопрос, и текст — кладём в один user-месседж
    u = question.strip() if question else "Проверь документ по правилам и ответь JSON."
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
) -> str:
    """
    Возвращает content (str) из /api/chat. При ошибке — поднимает исключение.
    """
    model = model or os.getenv("STAC_MODEL", "medaudit:stac-strict")
    body: Dict[str, Any] = {
        "model": model,
        "messages": _join_messages(system, question, text),
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
        "keep_alive": keep_alive,
        "stream": False,
    }
    if use_json_format:
        body["format"] = "json"

    last_err = None
    for attempt in range(retries + 1):
        t0 = time.time()
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=body,
                timeout=(connect_timeout, timeout),
            )
            dt = int((time.time() - t0) * 1000)
            if r.status_code != 200:
                raise RuntimeError(f"Ollama {r.status_code}: {r.text[:400]}")
            payload = r.json()
            # ожидаем {"message": {"content": "..."}}
            msg = (payload.get("message") or {})
            content = msg.get("content") or ""
            if not content:
                # иногда модель кладёт ответ в top-level "content" (редко)
                content = payload.get("content") or ""
            if not content:
                raise RuntimeError(f"Ollama empty content (dt={dt}ms)")
            return content
        except Exception as e:
            last_err = e
            print(f"[ollama_client] attempt {attempt+1} failed: {e}", file=sys.stderr)
            time.sleep(0.2)
    # если сюда дошли — все попытки провалились
    raise RuntimeError(f"Ollama error: {last_err}")

def quick_ping(model: Optional[str] = None) -> dict:
    """
    Минимальная проверка JSON-режима.
    """
    try:
        out = chat_ollama(
            system="Ты отвечаешь строго JSON без каких-либо комментариев.",
            question="Верни {\"ok\": true} ровно в таком виде.",
            text="",
            model=model,
            temperature=0.0,
            num_predict=16,
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "2048")),
            use_json_format=True,
            timeout=30,
            connect_timeout=3,
            retries=0,
        )
        data = json.loads(out)
        return {"ok": True, "raw": out[:160], "json": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}
