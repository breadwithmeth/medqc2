# -*- coding: utf-8 -*-
from __future__ import annotations
import os, time
from typing import Any, Dict, List, Tuple

from .ollama_client import chat_ollama
from .utils_json import coerce_json
from .timeline_extractor import extract_timeline
from .validator_stac_det import validate_stac_det
from .info_extractor_gen import extract_general
from .validator_gen_det import validate_gen_det
from .json_schema import (
    RULE_ID_ENUM, ORDER_ENUM, WHERE_ENUM,
    RULE_TITLES, RULE_SEVERITY,
    COMPACT_AUDIT_SCHEMA,
)
from .focus_text import focus_text

STAC_MODEL = os.getenv("STAC_MODEL", "medaudit:stac-strict")

# ---------- утилиты ----------
def _ensure_status(data: dict) -> dict:
    for it in data.get("passes", []) or []:
        it.setdefault("status", "PASS")
    for it in data.get("violations", []) or []:
        it.setdefault("status", "FAIL")
    return data

def _append_violation(data: dict, rule_id: str, title: str, order: str, where: str, evidence: str, severity: str = "major"):
    data.setdefault("violations", [])
    data["violations"].append({
        "rule_id": rule_id, "title": title, "severity": severity, "required": True,
        "order": order, "where": where, "evidence": evidence
    })

def _append_pass(data: dict, rule_id: str, title: str, severity: str, order: str = "timeline", where: str = "история болезни"):
    data.setdefault("passes", [])
    data["passes"].append({
        "rule_id": rule_id, "title": title, "severity": severity, "required": True,
        "order": order, "where": where, "evidence": "соответствует требованиям"
    })

def _chunks(lst: List[str], n: int) -> List[List[str]]:
    return [lst[i:i+n] for i in range(0, len(lst), n)]

def _compact_question(rules_this_chunk: List[str], limit_items: int, ev_max: int) -> str:
    ids = ", ".join(rules_this_chunk)
    where_opts = ", ".join(WHERE_ENUM)
    order_opts = ", ".join(ORDER_ENUM)
    return (
        "Ты аудитор меддокументов РК. Проверь ТОЛЬКО эти rule_id и верни ТОЛЬКО валидный JSON по схеме:\n"
        '{"viol":[{"r":"<rule_id>","s":"critical|major|minor","o":"<order>","w":"<where>","e":"<краткое доказательство>"}],'
        '"assessed":["<rule_id>", "..."]}\n'
        f"Оцени ТОЛЬКО: {ids}. "
        f"Поле order выбери из: {order_opts}. Поле where из: {where_opts}. "
        f"Суммарно не более {limit_items} нарушений; evidence ≤ {ev_max} символов. "
        "Не добавляй никаких комментариев и текста вне JSON. Отвечай на русском языке."
    )

# ---------- основной аудит ----------
def audit_stac(text: str, llm_text: str | None = None) -> dict:
    """
    Единый аудит стационара: детерминированные проверки + LLM (чанки, компактный JSON).
    """
    result: Dict[str, Any] = {"passes": [], "violations": [], "doc_profile_hint": ["STAC", "GEN"]}

    # 1) Детерминированные проверки (быстрые, без ЛЛМ)
    tl = extract_timeline(text)
    det1 = validate_stac_det(tl, full_text=text)
    result["passes"] += det1.get("passes", [])
    result["violations"] += det1.get("violations", [])

    gen = extract_general(text)
    det2 = validate_gen_det(gen)
    result["passes"] += det2.get("passes", [])
    result["violations"] += det2.get("violations", [])

    # 2) Вход для ЛЛМ (фокус)
    condensed = llm_text if llm_text is not None else focus_text(text)

    # 3) LLM выключаем по окружению
    llm_status: Dict[str, Any] = {"ok": False, "model": STAC_MODEL, "duration_ms": 0, "bytes": 0, "error": "not-called"}
    if os.getenv("SKIP_LLM", "0") == "1":
        llm_status["error"] = "skipped by env (SKIP_LLM=1)"
        result["llm_status"] = llm_status
        return _ensure_status(result)

    # 4) Чанкинг: разбиваем правила на группы и вызываем модель по кускам
    CHUNK_SIZE = int(os.getenv("LLM_RULES_PER_CALL", "6"))   # маленькие чанки => стабильно влезает
    LIMIT_ITEMS = int(os.getenv("LLM_LIMIT_ITEMS", "10"))
    EV_MAX = int(os.getenv("EVIDENCE_MAX_CHARS", "90"))
    NUM_PREDICT = int(os.getenv("NUM_PREDICT", "768"))       # можно поднять до 1024+ при VRAM

    assessed_all: set[str] = set()
    viol_map: Dict[str, Dict[str, Any]] = {}  # rule_id -> item
    total_ms = 0
    total_bytes = 0
    raw_samples: List[str] = []

    use_schema = True   # всегда schema (compact)
    use_grammar = False

    chunks = _chunks(RULE_ID_ENUM, CHUNK_SIZE)
    for rules_this_chunk in chunks:
        q = _compact_question(rules_this_chunk, LIMIT_ITEMS, EV_MAX)
        t0 = time.time()
        raw = chat_ollama(
            system="",
            question=q,
            text=condensed,
            model=STAC_MODEL,
            temperature=0.0,
            num_predict=NUM_PREDICT,
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
            keep_alive=os.getenv("KEEP_ALIVE", "30m"),
            use_json_format=False,
            timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
            connect_timeout=int(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5")),
            retries=int(os.getenv("OLLAMA_RETRIES", "0")),
            grammar=None,
            json_schema=COMPACT_AUDIT_SCHEMA,
        )
        dt = int((time.time() - t0) * 1000)
        total_ms += dt
        total_bytes += len(raw.encode("utf-8"))
        if len(raw_samples) < 3:
            raw_samples.append(raw[:160])

        data = coerce_json(raw)
        # ожидаем {"viol":[...], "assessed":[...]}
        for rid in data.get("assessed", []) or []:
            if rid in rules_this_chunk:
                assessed_all.add(rid)

        for v in data.get("viol", []) or []:
            rid = v.get("r", "")
            if not rid or rid not in rules_this_chunk:
                continue
            # если в этом чанке уже есть нарушение по rid — оставим первое (дальше всё равно дедуп)
            if rid not in viol_map:
                viol_map[rid] = {
                    "rule_id": rid,
                    "title": RULE_TITLES.get(rid, rid),
                    "severity": v.get("s", RULE_SEVERITY.get(rid, "major")),
                    "required": True,
                    "order": v.get("o", "timeline"),
                    "where": v.get("w", "история болезни"),
                    "evidence": v.get("e", ""),
                }

    # 5) Восстанавливаем PASS как assessed - violations
    violated_ids = set(viol_map.keys())
    passes_ids = assessed_all - violated_ids
    for rid in sorted(violated_ids):
        result["violations"].append(viol_map[rid])
    for rid in sorted(passes_ids):
        _append_pass(result, rid, RULE_TITLES.get(rid, rid), RULE_SEVERITY.get(rid, "major"))

    llm_status.update({
        "ok": True,
        "model": STAC_MODEL,
        "duration_ms": total_ms,
        "bytes": total_bytes,
        "chunks": len(chunks),
        "raw_samples": raw_samples,
    })
    llm_status.pop("error", None)
    result["llm_status"] = llm_status

    return _ensure_status(result)
