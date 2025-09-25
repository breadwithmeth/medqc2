# app/main.py
from __future__ import annotations
import os, time, uuid
from typing import Any, Dict
from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.audit_engine_stac import audit_stac
from app.pdf_text import extract_text_from_pdf

APP_NAME = "Med-Audit KZ (STAC)"
APP_VERSION = "1.0.0"

app = FastAPI(title=APP_NAME, version=APP_VERSION)

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS","").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],  # на проде лучше перечислить фронты
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        t0 = time.perf_counter()
        resp = await call_next(request)
        dt = (time.perf_counter()-t0)*1000
        print(f"[{request.method}] {request.url.path} {round(dt,1)}ms from {request.client.host}")
        return resp

app.add_middleware(TimingMiddleware)

def _ok(**extra: Any) -> Dict[str, Any]:
    return {"ok": True, **extra}

@app.get("/", response_class=PlainTextResponse)
def root() -> str:
    return f"{APP_NAME} v{APP_VERSION}"

@app.get("/health")
def health():
    return _ok(
        profile="STAC",
        model=os.getenv("STAC_MODEL", "medaudit:stac-fast"),
        ollama_url=os.getenv("OLLAMA_URL",""),
        ctx=int(os.getenv("OLLAMA_NUM_CTX","3072")),
        num_predict=int(os.getenv("NUM_PREDICT","90")),
        allowed_origins=origins or ["*"]
    )

@app.post("/audit/text_stac")
async def audit_text_stac(payload: dict):
    text = (payload or {}).get("text","").strip()
    if not text:
        raise HTTPException(400, "text is required")
    t0 = time.perf_counter()
    data = audit_stac(text)
    data["doc_name"] = ""
    data["elapsed_ms"] = round((time.perf_counter()-t0)*1000,1)
    return JSONResponse(data)

@app.post("/audit/pdf_stac")
async def audit_pdf_stac(file: UploadFile = File(...)):
    fname = (file.filename or "").lower()
    if not fname.endswith(".pdf"):
        raise HTTPException(400, "PDF required")
    blob = await file.read()
    trace_id = uuid.uuid4().hex[:8]
    t0 = time.perf_counter()
    t_pdf = time.perf_counter()
    text = extract_text_from_pdf(blob)
    pdf_ms = round((time.perf_counter() - t_pdf)*1000, 1)
    if not text.strip():
        raise HTTPException(400, "empty PDF text")

    data = audit_stac(text)
    data["doc_name"] = file.filename
    data["pdf_extract_ms"] = pdf_ms
    data["elapsed_ms"] = round((time.perf_counter()-t0)*1000,1)

    resp = JSONResponse(data)
    resp.headers["X-Trace-Id"] = trace_id
    return resp

@app.exception_handler(HTTPException)
async def http_exc_handler(_: Request, exc: HTTPException):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

@app.exception_handler(Exception)
async def unhandled_exc_handler(_: Request, exc: Exception):
    return JSONResponse({"detail": f"internal error: {type(exc).__name__}"}, status_code=500)
