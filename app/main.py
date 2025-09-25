# app/main.py (фрагмент)
import os
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from .rules_loader import load_llm_rules
from .audit_engine_llm import run_llm_rules
from .pdf_text import extract_text_from_pdf
from .router_llm import detect_profiles

RULES_DIR = os.getenv("RULES_DIR", "rules")
AUTO_ROUTING = os.getenv("AUTO_ROUTING", "1") == "1"

llm_rules = load_llm_rules(RULES_DIR)

def _prefix(rule_id: str) -> str:
    return (rule_id or "").split("-")[0].upper() if rule_id else ""

def _filter_rules_by_profiles(rules, profiles):
    if not profiles:
        return rules
    keep = set([p.upper() for p in profiles] + ["GEN"])
    out = []
    for r in rules:
        pref = _prefix(r.id if hasattr(r, "id") else r.get("id"))
        if pref in keep:
            out.append(r)
    return out

app = FastAPI()

origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS","*").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/health")
def health():
    return {
        "ok": True,
        "rules": len(llm_rules),
        "auto_routing": AUTO_ROUTING,
        "router_model": os.getenv("ROUTER_MODEL") or os.getenv("OLLAMA_MODEL")
    }

def _route_and_audit(text: str, doc_name: str | None = None):
    profiles, conf, reason, from_llm = ([], {}, "", False)
    rules_to_use = llm_rules
    if AUTO_ROUTING:
        profiles, conf, reason, from_llm = detect_profiles(text, limit=int(os.getenv("ROUTER_LIMIT","6")))
        rules_to_use = _filter_rules_by_profiles(llm_rules, profiles)

    passes, violations = run_llm_rules(text, rules_to_use)
    return {
        "doc_name": doc_name or "",
        "profiles_detected": profiles,
        "profiles_confidence": conf,
        "profiles_reason": reason,
        "profiles_source": "llm" if from_llm else "heuristic",
        "rules_total": len(rules_to_use),
        "passes": passes,
        "violations": violations,
    }

@app.post("/audit/text")
async def audit_text(payload: dict):
    text = (payload or {}).get("text", "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    return _route_and_audit(text, doc_name="")

@app.post("/audit/pdf")
async def audit_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "PDF required")
    data = await file.read()
    text = extract_text_from_pdf(data)
    if not text.strip():
        raise HTTPException(400, "empty PDF text")
    return _route_and_audit(text, doc_name=file.filename)
