# app/ollama_client.py
from __future__ import annotations
import os
import requests

# URL Ollama (GPU-сервер)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Модель по умолчанию (для стационара)
DEFAULT_MODEL = os.getenv("STAC_MODEL", "medaudit:stac-fast")

# Держим один Session для keep-alive
_session = requests.Session()


def chat_ollama(
    system: str,
    # поддерживаем оба варианта — question ИЛИ user (взаимозаменяемые)
    question: str | None = None,
    text: str = "",
    model: str | None = None,
    *,
    user: str | None = None,
    temperature: float = 0.0,
    num_predict: int | None = None,
    num_ctx: int | None = None,
    keep_alive: str | None = "30m",
    timeout: int | None = None,
    use_json_format: bool = True,
    stop: list[str] | None = None,
) -> str:
    """
    Универсальный клиент Ollama /api/chat.
    - Совместим с вызовами вида chat_ollama(system, question=..., text=..., ...)
      и chat_ollama(system, user=..., text=..., ...).
    - Возвращает строку content из ответа модели.
    """

    prompt = (user or question or "").strip()
    if text:
        # привычный формат "инструкция + разделитель + текст документа"
        user_content = f"{prompt}\n\n-----\n{text}" if prompt else text
    else:
        user_content = prompt

    body = {
        "model": model or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system or ""},
            {"role": "user", "content": user_content},
        ],
        "options": {
            "temperature": temperature,
        },
        "stream": False,
    }

    # JSON-формат (строго)
    if use_json_format:
        body["format"] = "json"

    # Дополнительные опции
    if num_predict is not None:
        body["options"]["num_predict"] = int(num_predict)
    if num_ctx is not None:
        body["options"]["num_ctx"] = int(num_ctx)
    if keep_alive:
        body["keep_alive"] = keep_alive
    if stop:
        body["options"]["stop"] = list(stop)

    # Таймауты
    t_read = timeout or int(os.getenv("OLLAMA_TIMEOUT_READ", "180"))
    t_conn = int(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5"))

    r = _session.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(t_conn, t_read))
    r.raise_for_status()
    data = r.json()

    # Стандартная форма ответа Ollama
    msg = data.get("message") or {}
    content = (msg.get("content") or "").strip()
    return content
