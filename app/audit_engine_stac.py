from __future__ import annotations
import os, re, json, time
from pathlib import Path
from typing import Any, Dict
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

def _append_violation(data: dict, rule_id: str, title: str = "", order: str = "", where: str = "", evidence: str = "", severity="major"):
    data.setdefault("violations", [])
    data["violations"].append({
        "rule_id": rule_id, "title": title or rule_id, "severity": severity, "required": True,
        "order": order or "", "where": where or "", "evidence": evidence or "нет данных"
    })

def _overlay_diet_regimen_violation(raw_text: str, data: dict):
    # ... (оставь как было у тебя ранее) ...
    pass  # если уже реализовано — оставь. Иначе можно удалить этот вызов ниже.

def _enforce_coverage(data: dict):
    pmap = _idx(data.get("passes", [])); vmap = _idx(data.get("violations", []))
    assessed = set(pmap) | set(vmap)
    missing = [rid for rid in EXPECTED_RULE_IDS if rid not in assessed]
    for rid in missing:
        _append_violation(data, rid, evidence="не оценено моделью (принудительный FAIL)")
    data["assessed_rule_ids"] = sorted(list(assessed | set(missing)))

def _merge_into(base: dict, addon: dict):
    """Приоритет FAIL из addon над PASS в base, новые PASS/FAIL добавляем."""
    pmap = _idx(base.get("passes", [])); vmap = _idx(base.get("violations", []))
    # FAIL
    for it in addon.get("violations", []) or []:
        rid = str(it.get("rule_id","")).strip()
        if rid in pmap:
            base["passes"] = [x for x in base["passes"] if str(x.get("rule_id","")) != rid]
        if rid not in vmap:
            base.setdefault("violations", []).append(it)
            vmap[rid] = it
    # PASS
    existing = set(_idx(base.get("passes", [])).keys()) | set(vmap.keys())
    for it in addon.get("passes", []) or []:
        rid = str(it.get("rule_id","")).strip()
        if rid not in existing:
            base.setdefault("passes", []).append(it)

def audit_stac(text: str, llm_text: str | None = None) -> dict:
    # text — полный текст для дет. проверок; llm_text — уже сфокусированный
    result: Dict[str, Any] = {"passes": [], "violations": [], "doc_profile_hint": ["STAC","GEN"]}

    # 1) дет-проверки на полном тексте
    tl = extract_timeline(text)
    det_stac = validate_stac_det(tl, full_text=text)
    gen = extract_general(text)
    det_gen = validate_gen_det(gen)
    _merge_into(result, det_stac)
    _merge_into(result, det_gen)

    # 2) LLM
    condensed = llm_text if llm_text is not None else focus_text(text)

    t0 = time.time()
    try:
        raw = chat_ollama(
            system="",
            question="Проверь документ по зашитым правилам (стационар + общие) и верни СТРОГО JSON.",
            text=condensed,
            model=STAC_MODEL,
            temperature=0.0,
            num_predict=int(os.getenv("NUM_PREDICT", "512")),
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
            keep_alive=os.getenv("KEEP_ALIVE", "30m"),
            use_json_format=True,
            timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
            connect_timeout=int(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5")),
            retries=int(os.getenv("OLLAMA_RETRIES", "0")),
        )
        dt = int((time.time() - t0) * 1000)
        data = coerce_json(raw)
        llm_ok = True
        result = _ensure_status(result)
        _merge_into(result, {"passes": data.get("passes", []), "violations": data.get("violations", [])})
        result["llm_status"] = {"ok": llm_ok, "duration_ms": dt, "model": STAC_MODEL}
    except Exception as e:
        dt = int((time.time() - t0) * 1000)
        _append_violation(result, "SYSTEM-LLM", "LLM недоступен/пустой ответ", "system", "LLM", str(e), severity="minor")
        result["llm_status"] = {"ok": False, "duration_ms": dt, "model": STAC_MODEL, "error": f"{type(e).__name__}: {e}"}

    return _ensure_status(result)