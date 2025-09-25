import os, json, time, requests
from typing import List, Dict, Tuple

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://188.124.55.172:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_0")
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048"))            # 2048 для 6ГБ VRAM, 4096 для 16ГБ
TEMPERATURE = float(os.getenv("OLLAMA_TEMPERATURE", "0.0"))
CHARS_PER_TOKEN = float(os.getenv("CHARS_PER_TOKEN", "3.2"))  # RU ≈ 3–4
BUDGET_RATIO = float(os.getenv("BUDGET_RATIO", "0.70"))       # доля контекста под документ (раньше было 0.85)
TIMEOUT_CONNECT = float(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5"))
TIMEOUT_READ = float(os.getenv("OLLAMA_TIMEOUT_READ", "600")) # подняли до 600
RETRIES = int(os.getenv("OLLAMA_RETRIES", "2"))
KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE_REQ", "24h")        # держать модель в памяти (дополнительно к сервису)
NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "160"))     # JSON короткий — ограничим
DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "medaudit:kz")

DEFAULT_SYS = (
  "Ты — аудитор медицинских документов Республики Казахстан. "
  "Проверяешь соответствие стандартам МЗ РК (стационар, дневной стационар, хирургия, анестезиология, "
  "инфекционные, неонатология, кардиология, пульмонология и др.). "
  "Всегда отвечай СТРОГО JSON-ом без пояснений вне JSON."
)

def _preflight() -> None:
    r = requests.get(f"{OLLAMA_URL}/api/version", timeout=(TIMEOUT_CONNECT, 3))
    r.raise_for_status()

def _budget_chars() -> int:
    budget_tokens = max(512, int(NUM_CTX * BUDGET_RATIO))
    return int(budget_tokens * CHARS_PER_TOKEN)

def _post_chat(body: dict) -> dict:
    last_err = None
    for attempt in range(1, RETRIES + 2):
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/chat",
                json=body,
                timeout=(TIMEOUT_CONNECT, TIMEOUT_READ),
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ReadTimeout as e:
            last_err = e
            time.sleep(min(5 * attempt, 15))
        except Exception as e:
            last_err = e
            break
    raise RuntimeError(f"Ollama chat error: {last_err}")
# app/ollama_client.py (замени соответствующие функции)

def _budget_tokens() -> int:
    # сколько токенов можно занять "всем" (документ + инструкции + ответ)
    return max(512, int(NUM_CTX * BUDGET_RATIO))

def _slice_doc_for_prompt(prompt_head: str, doc_text: str, reserve_tokens: int = 256) -> str:
    """
    prompt_head: уже сформированная часть промпта (инструкции, список правил) — в символах
    doc_text: исходный текст документа
    reserve_tokens: запас под ответ и непредвиденный оверхед
    """
    # сколько примерно токенов уже занято "шапкой"
    head_tokens = int(len(prompt_head) / CHARS_PER_TOKEN)
    max_doc_tokens = max(0, _budget_tokens() - head_tokens - reserve_tokens)
    max_doc_chars = int(max_doc_tokens * CHARS_PER_TOKEN)
    return (doc_text or "")[:max_doc_chars]

def chat_ollama(system: str, question: str, text: str,
                model: str | None = None,
                temperature: float = 0.2,
                num_predict: int | None = None,
                num_ctx: int | None = None,
                timeout: int | None = None) -> str:
    body = {
        "model": model or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system or ""},
            {"role": "user", "content": f"{question}\n\n-----\n{text}"}
        ],
        "options": {
            "temperature": temperature,
        },
        "stream": False,
    }
    if num_predict is not None:
        body["options"]["num_predict"] = num_predict
    if num_ctx is not None:
        body["options"]["num_ctx"] = num_ctx

    t_read = timeout or int(os.getenv("OLLAMA_TIMEOUT_READ", "600"))
    t_conn = int(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5"))
    r = requests.post(f"{OLLAMA_URL}/api/chat", json=body, timeout=(t_conn, t_read))
    r.raise_for_status()
    data = r.json()
    return (data.get("message") or {}).get("content", "").strip()

def chat_ollama_batch(system: str, rules: List[Dict[str, str]], doc_text: str) -> str:
    _preflight()
    # минимальный список правил (убрали title ради экономии токенов)
    lines = [
        "Проверь несколько требований сразу. Для КАЖДОГО правила верни ровно объект:",
        '{"id":"<ID>","status":"PASS|FAIL","evidence":"короткая цитата или пусто"}',
        'Ответ ДОЛЖЕН быть строго JSON без текста вне JSON в формате: {"results":[...]}',
        "",
        "Список правил (каждое правило приведено как 'ID: <id>' и 'Q: <вопрос>'):",
    ]
    for r in rules:
        lines.append(f"ID: {r['id']}\nQ: {r['question']}")
    head = "\n".join(lines) + "\n\n---\nТЕКСТ ДОКУМЕНТА (усечён):\n"
    chunk = _slice_doc_for_prompt(head, doc_text)

    body = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system or DEFAULT_SYS},
            {"role": "user", "content": head + chunk},
        ],
        "options": {
            "temperature": TEMPERATURE,
            "num_ctx": NUM_CTX,
            "num_predict": NUM_PREDICT
        },
        "keep_alive": KEEP_ALIVE,
        "stream": False
    }
    data = _post_chat(body)
    return data["message"]["content"]

def parse_json(s: str) -> Tuple[str, str]:
    try:
        obj = json.loads(s)
        status = str(obj.get("status", "")).upper()
        if status not in ("PASS", "FAIL"):
            status = "FAIL"
        evidence = str(obj.get("evidence", "")).strip()
        return status, evidence
    except Exception:
        up = (s or "").upper()
        if "PASS" in up and "FAIL" not in up:
            return "PASS", ""
        return "FAIL", ""

def parse_batch_json(s: str) -> Dict[str, Tuple[str, str]]:
    """
    Возвращает mapping: rule_id -> (status, evidence)
    """
    out: Dict[str, Tuple[str, str]] = {}
    try:
        obj = json.loads(s)
        results = obj.get("results", obj)
        if isinstance(results, dict) and "results" in results:
            results = results["results"]
        if isinstance(results, list):
            for item in results:
                rid = str(item.get("id", "")).strip()
                status = str(item.get("status", "")).upper()
                evidence = str(item.get("evidence", "")).strip()
                if rid and status in ("PASS", "FAIL"):
                    out[rid] = (status, evidence)
        return out
    except Exception:
        return out
