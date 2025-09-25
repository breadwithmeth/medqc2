from __future__ import annotations
import os, requests

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
DEFAULT_MODEL = os.getenv("STAC_MODEL", "medaudit:stac-strict")

_session = requests.Session()

def chat_ollama(
    system: str,
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
    prompt = (user or question or "").strip()
    user_content = f"{prompt}\n\n-----\n{text}" if (prompt and text) else (text or prompt)

    body = {
        "model": model or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system or ""},
            {"role": "user", "content": user_content},
        ],
        "options": {"temperature": temperature},
        "stream": False,
    }
    if use_json_format: body["format"] = "json"
    if num_predict is not None: body["options"]["num_predict"] = int(num_predict)
    if num_ctx is not None: body["options"]["num_ctx"] = int(num_ctx)
    if keep_alive: body["keep_alive"] = keep_alive
    if stop: body["options"]["stop"] = list(stop)

    t_read = timeout or int(os.getenv("OLLAMA_TIMEOUT_READ", "180"))
    t_conn = int(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5"))
    r = _session.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(t_conn, t_read))
    r.raise_for_status()
    data = r.json()
    return (data.get("message", {}) or {}).get("content", "").strip()
