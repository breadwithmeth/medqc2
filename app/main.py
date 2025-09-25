from __future__ import annotations
import os, time
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .pdf_text import extract_text_from_pdf
from .audit_engine_stac import audit_stac

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS","*").split(",") if o.strip()]

app = FastAPI(title="MedAudit STAC")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if ALLOWED_ORIGINS != ["*"] else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def timing_mw(request: Request, call_next):
    t0 = time.time()
    resp = await call_next(request)
    resp.headers["X-Elapsed-ms"] = str(int((time.time()-t0)*1000))
    return resp

class TextIn(BaseModel):
    text: str

@app.get("/health")
def health():
    return {
        "ok": True,
        "model": os.getenv("STAC_MODEL","medaudit:stac-strict"),
        "ollama_url": os.getenv("OLLAMA_URL","http://127.0.0.1:11434")
    }

@app.post("/audit/text_stac")
def audit_text_stac(payload: TextIn):
    return audit_stac(payload.text)

@app.post("/audit/pdf_stac")
async def audit_pdf_stac(file: UploadFile = File(...)):
    blob = await file.read()
    text = extract_text_from_pdf(blob)
    return audit_stac(text)

# опционально: дебаг просмотра сфокусированного текста
from .focus_text import focus_text
@app.post("/debug/focus_pdf")
async def debug_focus(file: UploadFile = File(...)):
    blob = await file.read()
    txt = extract_text_from_pdf(blob)
    return {"raw_len": len(txt), "focused_len": len(focus_text(txt)), "focused_head": focus_text(txt)[:1200]}
