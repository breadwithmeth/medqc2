# MedAudit KZ — API документация

Дата: 2025-10-07
Бэкенд: FastAPI (`app/main.py`), заголовок приложения: `medqc2`
База: http://localhost:8000 (по умолчанию)

Доступны интерактивные страницы:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`


## Быстрый старт

- Локально (без LLM):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export SKIP_LLM=1
export CORS_ALLOW_ORIGINS="*"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- Локально (с Ollama):
```bash
export OLLAMA_URL="http://127.0.0.1:11434"
export STAC_MODEL="medaudit:stac-strict"   # замените на вашу из `ollama list`
export OLLAMA_NUM_CTX=3072
export NUM_PREDICT=768
uvicorn app.main:app --host 0.0.0.0 --port 8000
```
- Docker (если API в контейнере, а Ollama — на хосте macOS):
```bash
docker run --rm -p 8000:8000 \
  -e OLLAMA_URL="http://host.docker.internal:11434" \
  -e STAC_MODEL="medaudit:stac-strict" \
  -e CORS_ALLOW_ORIGINS="*" \
  medqc2:local
```


## Эндпоинты

### POST /audit/pdf_stac — аудит PDF (стационар GEN+STAC)

Принимает PDF и возвращает JSON с результатами детерминированных и LLM-проверок.

- Content-Type: `multipart/form-data`
- Параметры формы:
  - `file` (обязателен): PDF-файл для анализа
- Query-параметры (опционально):
  - `human` (bool, default: false): вернуть человекочитаемый компактный отчёт вместо «сырых» полей.
  - `format` (string, default: json): формат человека — `json|text|markdown`.
- Успешный ответ: `200 application/json`
- Возможные ошибки: `422` (не передан файл), внутренние ошибки парсинга/LLM (ответ 200 с полем `llm_status.error`)

Пример запроса:
```bash
curl -s -X POST http://localhost:8000/audit/pdf_stac \
  -F "file=@test.pdf" | jq .
```

Человекочитаемый JSON:
```bash
curl -s -X POST "http://localhost:8000/audit/pdf_stac?human=true&format=json" \
  -F "file=@test.pdf" | jq .
```

Плэйн-текст (подходит для чат-ответов/логов):
```bash
curl -s -X POST "http://localhost:8000/audit/pdf_stac?human=true&format=text" \
  -F "file=@test.pdf"
```

Markdown (для фронта/рендереров):
```bash
curl -s -X POST "http://localhost:8000/audit/pdf_stac?human=true&format=markdown" \
  -F "file=@test.pdf"
```

Пример ответа (усечённый):
```json
{
  "doc_profile_hint": ["STAC", "GEN"],
  "passes": [
    {
      "rule_id": "GEN-001",
      "title": "ФИО, ИИН и дата рождения указаны",
      "severity": "critical",
      "required": true,
      "order": "Идентификация пациента",
      "where": "Общие требования",
      "evidence": "..."
    }
  ],
  "violations": [
    {
      "rule_id": "STAC-002",
      "title": "Диагноз при поступлении и при выписке",
      "severity": "critical",
      "required": true,
      "order": "Диагнозы",
      "where": "стационар",
      "evidence": "не найдено в документе"
    }
  ],
  "llm_status": {
    "ok": true,
    "model": "medaudit:stac-strict",
    "duration_ms": 5230,
    "bytes": 12456,
    "chunks": 8,
    "raw_samples": ["{\"viol\":...}"]
  },
  "debug_focus": {
    "pages_used": [1,2,3],
    "token_estimate": 2900,
    "was_reduced": true
  }
}
```

Поля ответа (для стандартного режима):
- `doc_profile_hint`: подсказка профилей документа (обычно `["STAC","GEN"]`).
- `passes[]`: список правил, прошедших проверки.
  - `rule_id`, `title`, `severity` (`critical|major|minor`), `required`, `order`, `where`, `evidence`.
- `violations[]`: список нарушений в таком же формате, что и `passes`.
- `llm_status`: статус работы LLM-части (модель, время, объём, примеры сырых ответов). При `SKIP_LLM=1` будет `error: skipped by env (SKIP_LLM=1)`.
- `debug_focus`: отладочная информация о сжатии текста (страницы, оценка токенов, был ли тримминг).

Замечания:

Поля ответа в человекочитаемом JSON (`human=true&format=json`):
```json
{
  "summary": { "passes": 12, "violations": 3, "by_severity": {"критично": 1, "существенно": 2, "незначительно": 0} },
  "violations_compact": [ { "id": "STAC-002", "title": "Диагноз при поступлении и при выписке", "severity": "критично", "evidence": "..." } ],
  "pretty_text": "Итог проверки...\nСписок нарушений: ..."
}
```
- Если LLM недоступен, можно выставить `SKIP_LLM=1` — будут только детерминированные проверки.
- OCR включён по умолчанию в Docker-образе. Локально можно отключить `USE_OCR=0`.


### GET /debug/env — переменные среды

Возвращает значения ключевых переменных окружения, которые использует сервис.

Пример:
```bash
curl -s http://localhost:8000/debug/env | jq .
```

Поля включают: `OLLAMA_URL`, `STAC_MODEL`, `SKIP_LLM`, `OLLAMA_USE_SCHEMA`, `OLLAMA_USE_GRAMMAR`, `NUM_PREDICT`, `OLLAMA_NUM_CTX`, `OLLAMA_TIMEOUT_CONNECT`, `OLLAMA_TIMEOUT_READ`, `LLM_LIMIT_ITEMS`, `EVIDENCE_MAX_CHARS`.


### GET /debug/ollama/tags — список моделей Ollama

Проксирует запрос к `OLLAMA_URL/api/tags`.
- Успешный ответ: `200` JSON от Ollama
- При ошибке сети/подключения: `502` + `{ "error": "..." }`

```bash
curl -s http://localhost:8000/debug/ollama/tags | jq .
```


### GET /debug/ollama/schema — поддержка JSON Schema

Проверяет, поддерживает ли текущая версия Ollama "structured outputs" (format = JSON Schema).
- Успех: `{ "schema_supported": true }`
- Иначе: `{ "schema_supported": false, "error": "..." }` (HTTP 502)

```bash
curl -s http://localhost:8000/debug/ollama/schema | jq .
```


### GET /debug/llm_ping — быстрый пинг LLM

Мини-проверка доступности и базового JSON-ответа.

```bash
curl -s http://localhost:8000/debug/llm_ping | jq .
```

Ответ (пример):
```json
{ "ok": true, "duration_ms": 180, "model": "medaudit:stac-strict" }
```


## Переменные окружения

LLM и производительность:
- `OLLAMA_URL` — адрес Ollama (например, `http://127.0.0.1:11434`).
- `STAC_MODEL` — имя модели в Ollama (по умолчанию `medaudit:stac-strict`).
- `OLLAMA_NUM_CTX` — размер контекста (по умолчанию 3072).
- `NUM_PREDICT` — максимальная длина вывода (по умолчанию 512–768).
- `OLLAMA_TIMEOUT_CONNECT` (сек), `OLLAMA_TIMEOUT_READ` (сек), `OLLAMA_RETRIES` — таймауты/повторы.
- `LLM_RULES_PER_CALL` — размер чанка правил (по умолчанию 6).
- `LLM_LIMIT_ITEMS` — ограничение числа возвращаемых нарушений (по умолчанию 10).
- `EVIDENCE_MAX_CHARS` — ограничение длины цитаты-доказательства (по умолчанию 90).
- `KEEP_ALIVE` — TTL сессии в Ollama (например, `30m`).
- `SKIP_LLM` — `1` отключает LLM-проверки (по умолчанию `0`).

CORS:
- `CORS_ALLOW_ORIGINS` — список доменов фронта через запятую (в коде читается именно эта переменная). Примеры: `*` или `http://localhost:5173,https://qa.example.com`.

OCR (если включён):
- `USE_OCR` (1/0), `OCR_LANGS` (например, `rus+kaz+eng`), `OCR_DPI`, `OCR_MIN_CHARS`, `OCR_SAMPLING_STEP`, `OCR_SECOND_PASS_PAGES`, `OCR_MAX_PAGES_DOC`.

Прочее:
- `API_LANG` — язык ответов (по умолчанию `ru`).


## Замечания по безопасности

- Аутентификации нет: размещайте сервис за доверенным прокси/файрволом или добавьте авторизацию на уровне платформы.
- Ограничьте CORS доменами, а не `*`, для прод-окружения.


## Производительность и ограничения

- OCR и большие PDF повышают время ответа. В Dockerfile по умолчанию стоят ограничения OCR (например, `OCR_MAX_PAGES_DOC=20`).
- Для стабильности LLM лучше держать `LLM_RULES_PER_CALL` небольшим (6–8) и ограничивать `NUM_PREDICT`.


## Экспорт OpenAPI

Сохранить спецификацию:
```bash
curl -s http://localhost:8000/openapi.json > docs/openapi.json
```

---
Если нужно, могу добавить Makefile/VS Code task для одношагового запуска/деплоя и автогенерации OpenAPI/Markdown.
