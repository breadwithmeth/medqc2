# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import time

from fastapi import FastAPI, File, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .audit_engine_stac import audit_stac
from .ollama_client import quick_ping, get_tags, schema_smoke_test, grammar_smoke_test
from .openai_compat_client import ping_openai_compat
from .pdf_smart_reader import smart_focus_for_llm
from .pdf_text import extract_text_from_pdf
from .humanize import build_human_report
from .localize import localize_result


APP_TITLE = "medqc2"
app = FastAPI(title=APP_TITLE)

# CORS
ALLOW_ORIGINS = os.getenv("CORS_ALLOW_ORIGINS", "*")
allow_list = [s.strip() for s in ALLOW_ORIGINS.split(",")] if ALLOW_ORIGINS else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Static UI (simple front)
try:
    app.mount("/ui", StaticFiles(directory="web", html=True), name="ui")
except Exception:
    # папка может отсутствовать в некоторых окружениях — игнорируем
    pass


# измерение времени запроса
@app.middleware("http")
async def timing_mw(request: Request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    resp.headers["X-Elapsed-ms"] = str(int((time.time() - t0) * 1000))
    return resp


@app.post("/audit/pdf_stac")
async def audit_pdf_stac(
    file: UploadFile = File(...),
    human: bool = Query(False, description="Человекочитаемый компактный ответ"),
    format: str = Query("json", description="Формат человека: json|text|markdown", regex="^(json|text|markdown)$"),
    use_full: bool = Query(False, description="Отдать LLM полный текст (медленнее, но шире покрытие)"),
    model: str | None = Query(None, description="Переопределить модель Ollama для этого запроса"),
):
    blob = await file.read()

    # 1) фокусированный текст для LLM (ограничивает вход под num_ctx)
    focus = smart_focus_for_llm(blob)
    llm_text = focus["focused_text"]

    # 2) полный текст (для детерминированных проверок и как запасной вход)
    full_text = extract_text_from_pdf(blob)
    base_text = full_text if full_text else llm_text

    # приоритеты выбора входа для LLM: явный use_full параметр → env LLM_USE_FULL_TEXT → фокусированный текст
    use_full_env = (os.getenv("LLM_USE_FULL_TEXT", "0").lower() in ("1", "true", "yes", "on"))
    llm_in = full_text if (use_full or use_full_env) else llm_text

    result = audit_stac(base_text, llm_text=llm_in, model=model)
    result.setdefault("debug_focus", {}).update(
        {
            "pages_used": focus.get("pages_used"),
            "token_estimate": focus.get("token_estimate"),
            "was_reduced": focus.get("was_reduced"),
        }
    )
    if human:
        report = build_human_report(result)
        if format == "json":
            return JSONResponse(report)
        # text or markdown — вернём простой текст (markdown совместим в большинстве UI)
        return PlainTextResponse(report["pretty_text"], media_type="text/markdown" if format == "markdown" else "text/plain")

    # По умолчанию возвращаем локализованный JSON (на русском)
    return JSONResponse(localize_result(result))


# ---------- DEBUG ----------
@app.get("/debug/env")
def dbg_env():
    keys = [
        "OLLAMA_URL",
        "STAC_MODEL",
        "SKIP_LLM",
        "OLLAMA_USE_SCHEMA",
        "OLLAMA_USE_GRAMMAR",
        "NUM_PREDICT",
        "OLLAMA_NUM_CTX",
        "OLLAMA_TIMEOUT_CONNECT",
        "OLLAMA_TIMEOUT_READ",
        "LLM_LIMIT_ITEMS",
        "EVIDENCE_MAX_CHARS",
    ]
    return {k: os.getenv(k) for k in keys}


@app.get("/debug/ollama/tags")
def dbg_tags():
    try:
        return get_tags()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


@app.get("/debug/ollama/schema")
def dbg_schema():
    try:
        ok = schema_smoke_test()
        return {"schema_supported": bool(ok)}
    except Exception as e:
        return JSONResponse({"schema_supported": False, "error": str(e)}, status_code=502)


@app.get("/debug/ollama/grammar")
def dbg_grammar():
    try:
        ok = grammar_smoke_test()
        return {"grammar_supported": bool(ok)}
    except Exception as e:
        return JSONResponse({"grammar_supported": False, "error": str(e)}, status_code=502)


@app.get("/debug/llm_ping")
def llm_ping():
    return quick_ping()


@app.get("/debug/provider")
def dbg_provider():
    """Показывает доступность провайдеров (Ollama/OpenAI-совместимый)."""
    out = {"ollama": quick_ping()}
    try:
        out["openai_compat"] = ping_openai_compat()
    except Exception as e:
        out["openai_compat"] = {"ok": False, "error": str(e)}
    return out
