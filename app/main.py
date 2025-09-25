import os
from fastapi import FastAPI, UploadFile, File, Body, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .pdf_utils import extract_text_from_pdf_bytes, normalize_text
from .rules_loader import load_llm_rules
from .audit_engine_llm import run_llm_rules_batched, run_llm_rules
from .models import AuditResponse, TextReq

RULES_DIR = os.getenv("RULES_DIR", "./rules")
USE_BATCH = os.getenv("USE_BATCH", "1") not in ("0", "false", "False")

llm_rules = load_llm_rules(RULES_DIR)

app = FastAPI(title="Med-Audit KZ (Ollama API)", version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"ok": True, "rules": len(llm_rules), "batch": USE_BATCH}

@app.get("/rules")
def rules():
    return {"count": len(llm_rules), "rules": [r.model_dump() for r in llm_rules]}

def _run(text: str):
    try:
        if USE_BATCH:
            return run_llm_rules_batched(text, llm_rules)
        return run_llm_rules(text, llm_rules)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")

@app.post("/audit/text", response_model=AuditResponse)
async def audit_text(req: TextReq = Body(...)):
    t = normalize_text(req.text or "")
    passes, violations = _run(t)
    return AuditResponse(ok=True, doc_name=None, rules_total=len(llm_rules),
                         violations=violations, passes=passes)

@app.post("/audit/pdf", response_model=AuditResponse)
async def audit_pdf(file: UploadFile = File(...)):
    data = await file.read()
    t = extract_text_from_pdf_bytes(data)
    passes, violations = _run(t)
    return AuditResponse(ok=True, doc_name=file.filename, rules_total=len(llm_rules),
                         violations=violations, passes=passes)
