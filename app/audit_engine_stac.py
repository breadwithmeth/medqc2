from __future__ import annotations
import os, re, json
from pathlib import Path
from .ollama_client import chat_ollama
from .focus_text import focus_text
from .utils_json import coerce_json

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

def _idx_by_rule(items: list[dict]) -> dict[str, dict]:
    return {str(it.get("rule_id","")).strip(): it for it in items or []}

def _append_violation(data: dict, rule_id: str, title: str = "", order: str = "", where: str = "", evidence: str = ""):
    data.setdefault("violations", [])
    data["violations"].append({
        "rule_id": rule_id,
        "title": title or rule_id,
        "severity": "major",
        "required": True,
        "order": order or "",
        "where": where or "",
        "evidence": evidence or "не оценено моделью / не найдено в документе"
    })

_DIETA_RX = re.compile(r"диета\s*:\s*([^;\n\r]+)", re.I | re.U)
_REGIMEN_RX = re.compile(r"режим\s*:\s*([^;\n\r]+)", re.I | re.U)

def _overlay_diet_regimen_violation(raw_text: str, data: dict):
    rid = "STAC-27-PRESCRIPTION-DIET-REGIMEN"
    vmap = _idx_by_rule(data.get("violations", []))
    pmap = _idx_by_rule(data.get("passes", []))
    if rid in vmap or rid in pmap:
        return
    txt = raw_text or ""
    dieta = _DIETA_RX.search(txt)
    regimen = _REGIMEN_RX.search(txt)
    bad, ev = [], []
    if not dieta:
        bad.append("Диета не найдена")
    else:
        dval = dieta.group(1).strip()
        ev.append(f"Диета: {dval}")
        if dval.lower().startswith("не указано"):
            bad.append("Диета: Не указано")
    if not regimen:
        bad.append("Режим не найден")
    else:
        rval = regimen.group(1).strip()
        ev.append(f"Режим: {rval}")
        if rval.lower().startswith("не указано"):
            bad.append("Режим: Не указано")
    if bad:
        _append_violation(
            data, rid,
            title="Лист назначений/выписка — Диета и Режим обязательно",
            order="Приказ 27",
            where="лист назначений / рекомендации / проведённое лечение",
            evidence="; ".join(ev) if ev else "; ".join(bad)
        )
    else:
        data.setdefault("passes", [])
        data["passes"].append({
            "rule_id": rid,
            "title": "Лист назначений/выписка — Диета и Режим обязательно",
            "severity": "minor",
            "required": True,
            "order": "Приказ 27",
            "where": "лист назначений / рекомендации / проведённое лечение",
            "evidence": "; ".join(ev) if ev else "найдены"
        })

def _enforce_coverage(data: dict):
    pmap = _idx_by_rule(data.get("passes", []))
    vmap = _idx_by_rule(data.get("violations", []))
    assessed = set(pmap) | set(vmap)
    missing = [rid for rid in EXPECTED_RULE_IDS if rid not in assessed]
    for rid in missing:
        _append_violation(data, rid, evidence="не оценено моделью (принудительный FAIL)")
    data["assessed_rule_ids"] = sorted(list(assessed | set(missing)))

def audit_stac(text: str) -> dict:
    condensed = focus_text(text)
    raw = chat_ollama(
        system="",  # правила в модели
        question="Проверь документ по зашитым правилам (стационар + общие) и верни СТРОГО JSON.",
        text=condensed,
        model=STAC_MODEL,
        temperature=0.0,
        num_predict=int(os.getenv("NUM_PREDICT", "256")),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
        keep_alive=os.getenv("KEEP_ALIVE", "30m"),
        use_json_format=True,
        timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
        stop=["```"],
    )
    try:
        data = coerce_json(raw)
    except Exception as e:
        return {
            "doc_profile_hint": ["STAC","GEN"],
            "passes": [],
            "violations": [{
                "rule_id":"SYSTEM-JSON","title":"Парсинг ответа",
                "severity":"major","required":True,"order":"system","where":"LLM output",
                "evidence": f"LLM non-JSON: {type(e).__name__}: {e}"
            }],
            "llm_raw_snippet": (raw or "")[:800]
        }
    data.setdefault("passes", [])
    data.setdefault("violations", [])
    data.setdefault("doc_profile_hint", ["STAC","GEN"])

    _overlay_diet_regimen_violation(text, data)
    if EXPECTED_RULE_IDS:
        _enforce_coverage(data)
    return _ensure_status(data)
