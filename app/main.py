from __future__ import annotations
import os, time
from fastapi import FastAPI, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .pdf_text import extract_text_from_pdf
from .audit_engine_stac import audit_stac
from .timeline_extractor import extract_timeline
from .audit_engine_stac import audit_stac
from .pdf_smart_reader import smart_focus_for_llm, chunk_text
from .pdf_ocr_fallback import has_tesseract
from .localize import localize_result

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

    focus = smart_focus_for_llm(blob)  # уже ограничивает вход под num_ctx
    llm_text = focus["focused_text"]

    full_text = extract_text_from_pdf(blob)  # для детерминированных проверок
    base_text = full_text if full_text else llm_text

    result = audit_stac(base_text, llm_text=llm_text)
    result.setdefault("debug_focus", {}).update({
        "pages_used": focus["pages_used"],
        "token_estimate": focus["token_estimate"],
        "was_reduced": focus["was_reduced"],
    })
    return result
# опционально: дебаг просмотра сфокусированного текста
from .focus_text import focus_text
@app.post("/debug/focus_pdf")
async def debug_focus(file: UploadFile = File(...)):
    blob = await file.read()
    txt = extract_text_from_pdf(blob)
    return {"raw_len": len(txt), "focused_len": len(focus_text(txt)), "focused_head": focus_text(txt)[:1200]}


from .timeline_extractor import extract_timeline

@app.post("/debug/timeline_pdf")
async def debug_timeline(file: UploadFile = File(...)):
    blob = await file.read()
    text = extract_text_from_pdf(blob)
    tl = extract_timeline(text)
    # компактный вывод
    keys = ["admission_dt_str","er_exam_dt_str","ward_exam_dt_str","head_primary_dt_str",
            "diag_justify_dt_str","anes_protocol_dt_str","op_protocol_dt_str",
            "clinical_diag_dt_str","stage_epicrisis_dt_str","note_times","severe_present"]
    out = {k: tl.get(k) for k in keys}
    return out


@app.post("/debug/ocr_check")
async def debug_ocr(file: UploadFile = File(...)):
    blob = await file.read()
    focus = smart_focus_for_llm(blob)
    return {
        "tesseract_available": has_tesseract(),
        "pages_used": focus["pages_used"],
        "token_estimate": focus["token_estimate"],
        "was_reduced": focus["was_reduced"],
        "focused_head": focus["focused_text"][:400]
    }