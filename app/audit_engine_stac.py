from __future__ import annotations
import os, re, json, sys
from pathlib import Path
from .ollama_client import chat_ollama
from .focus_text import focus_text
from .utils_json import coerce_json
from .timeline_extractor import extract_timeline
from .validator_stac_det import validate_stac_det
from .info_extractor_gen import extract_general
from .validator_gen_det import validate_gen_det

STAC_MODEL = os.getenv("STAC_MODEL", "medaudit:stac-strict")

_EXPECTED = {"expected_rule_ids": []}
try:
    _EXPECTED = json.loads(Path(__file__).with_name("expected_rules_stac.json").read_text(encoding="utf-8"))
except Exception:
    pass

EXPECTED_RULE_IDS: list[str] = _EXPECTED.get("expected_rule_ids", [])

def _ensure_status(data: dict) -> dict:
    for it in data.get("passes", []):
        it.setdefault("status", "PASS")
    for it in data.get("violations", []):
        it.setdefault("status", "FAIL")
    return data

def _idx(items: list[dict]) -> dict[str, dict]:
    return {str(it.get("rule_id","")).strip(): it for it in (items or [])}

def _append_violation(data: dict, rule_id: str, title: str = "", order: str = "", where: str = "", evidence: str = ""):
    data.setdefault("violations", [])
    data["violations"].append({
        "rule_id": rule_id, "title": title or rule_id, "severity": "major", "required": True,
        "order": order or "", "where": where or "", "evidence": evidence or "не оценено моделью / не найдено в документе"
    })

def _overlay_diet_regimen_violation(raw_text: str, data: dict):
    rid = "STAC-27-PRESCRIPTION-DIET-REGIMEN"
    vmap = _idx(data.get("violations", [])); pmap = _idx(data.get("passes", []))
    if rid in vmap or rid in pmap: return
    m_diet = re.search(r"диет[аы]\s*:\s*([^\n\r]+)", raw_text, re.I)
    m_reg  = re.search(r"режим\s*:\s*([^\n\r]+)", raw_text, re.I)
    bad, ev = [], []
    if not m_diet: bad.append("Диета не найдена")
    else:
        d = m_diet.group(1).strip(); ev.append(f"Диета:{d}")
        if d.lower().startswith("не указ"): bad.append("Диета: Не указано")
    if not m_reg: bad.append("Режим не найден")
    else:
        r = m_reg.group(1).strip(); ev.append(f"Режим:{r}")
        if r.lower().startswith("не указ"): bad.append("Режим: Не указано")
    if bad:
        _append_violation(data, rid, "Лист назначений/выписка — Диета и Режим обязательно", "Приказ 27",
                          "лист назначений / рекомендации", "; ".join(ev) if ev else "; ".join(bad))
    else:
        data.setdefault("passes", []).append({
            "rule_id": rid, "title":"Лист назначений/выписка — Диета и Режим обязательно",
            "severity":"minor", "required":True, "order":"Приказ 27", "where":"лист назначений / рекомендации",
            "evidence":"; ".join(ev) if ev else "найдены"
        })

def _enforce_coverage(data: dict):
    pmap = _idx(data.get("passes", [])); vmap = _idx(data.get("violations", []))
    assessed = set(pmap) | set(vmap)
    missing = [rid for rid in EXPECTED_RULE_IDS if rid not in assessed]
    for rid in missing:
        _append_violation(data, rid, evidence="не оценено моделью (принудительный FAIL)")
    data["assessed_rule_ids"] = sorted(list(assessed | set(missing)))

def _retry_fix_json(condensed: str) -> dict | None:
    raw2 = chat_ollama(
        system="Ты отвечаешь СТРОГО JSON-объектом без пояснений и без markdown.",
        question=("Сформируй ответ по той же схеме (timeline, passes, violations, assessed_rule_ids). "
                  "Evidence ≤120 символов, без переводов строк. Верни ТОЛЬКО JSON."),
        text=condensed, temperature=0.0,
        num_predict=int(os.getenv("NUM_PREDICT", "512")),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
        use_json_format=True, timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
    )
    try:
        return coerce_json(raw2)
    except Exception:
        return None

def audit_stac(text: str) -> dict:
    condensed = focus_text(text)

    # LLM
    raw = chat_ollama(
        system="",  # правила в модели
        question="Проверь документ по зашитым правилам (стационар + общие) и верни СТРОГО JSON.",
        text=condensed, model=STAC_MODEL, temperature=0.0,
        num_predict=int(os.getenv("NUM_PREDICT", "512")),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
        keep_alive=os.getenv("KEEP_ALIVE", "30m"),
        use_json_format=True, timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
    )
    try:
        data = coerce_json(raw)
    except Exception as e:
        fixed = _retry_fix_json(condensed)
        if fixed is not None:
            data = fixed
        else:
            return {
                "doc_profile_hint": ["STAC","GEN"], "passes": [],
                "violations": [{
                    "rule_id":"SYSTEM-JSON","title":"Парсинг ответа","severity":"major","required":True,
                    "order":"system","where":"LLM output","evidence": f"LLM non-JSON: {type(e).__name__}: {e}"
                }],
                "llm_raw_snippet": (raw or "")[:800]
            }

    data.setdefault("passes", []); data.setdefault("violations", []); data.setdefault("doc_profile_hint", ["STAC","GEN"])

    # Детерминатор: стационар
    tl = extract_timeline(text)
    det_stac = validate_stac_det(tl, full_text=text)

    # Детерминатор: общие
    gen = extract_general(text)
    det_gen = validate_gen_det(gen)

    # Слияние: FAIL детерминистический всегда главнее PASS LLM
    def merge(det):
        pmap = _idx(data.get("passes", [])); vmap = _idx(data.get("violations", []))
        for it in det.get("violations", []):
            rid = it["rule_id"]
            if rid in pmap:
                data["passes"] = [x for x in data["passes"] if str(x.get("rule_id","")) != rid]
            if rid not in vmap:
                it["evidence"] = (it.get("evidence",""))[:200]
                data["violations"].append(it)
        existing = set(_idx(data.get("passes", [])).keys()) | set(_idx(data.get("violations", [])).keys())
        for it in det.get("passes", []):
            rid = it["rule_id"]
            if rid not in existing:
                it["evidence"] = (it.get("evidence",""))[:200]
                data["passes"].append(it)

    merge(det_stac)
    merge(det_gen)

    # Доп. оверлей (Диета/Режим)
    _overlay_diet_regimen_violation(text, data)

    # Принудительное покрытие
    if EXPECTED_RULE_IDS:
        _enforce_coverage(data)

    # Бонус: краткий таймлайн/ген-инфо для дебага
    data["timeline_det"] = {
        k: tl.get(k) for k in ("admission_dt_str","er_exam_dt_str","ward_exam_dt_str","head_primary_dt_str",
                               "diag_justify_dt_str","anes_protocol_dt_str","op_protocol_dt_str",
                               "clinical_diag_dt_str","stage_epicrisis_dt_str","note_times","severe_present")
    }
    data["gen_info_det"] = {
        k: gen.get(k) for k in ("fio_line","iin","dob_or_age","sex","hist_no","org_present",
                                "admission_dt_str","discharge_dt_str","icd10_codes","signatures_count")
    }
    return _ensure_status(data)
