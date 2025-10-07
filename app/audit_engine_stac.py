# -*- coding: utf-8 -*-
from __future__ import annotations
import os, time
from typing import Any, Dict, List, Tuple

from .ollama_client import chat_ollama, schema_smoke_test, grammar_smoke_test
from .gbnf import COMPACT_AUDIT_GBNF
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
    mapping = "\n".join([f"- {rid}: {RULE_TITLES.get(rid, rid)}" for rid in rules_this_chunk])
    return (
        "Ты аудитор меддокументов РК. Проверь ТОЛЬКО перечисленные rule_id и верни ТОЛЬКО валидный JSON по схеме:\n"
        '{"viol":[{"r":"<rule_id>","s":"critical|major|minor","o":"<order>","w":"<where>","e":"<краткое доказательство>"}],'
        '"assessed":["<rule_id>", "..."]}\n'
        "Справка: rule_id → краткое название (только для понимания, не добавляй в ответ):\n"
        f"{mapping}\n"
        f"Оцени и ВКЛЮЧИ В assessed ВСЕ эти id (в этом же порядке, без повторов): {ids}. "
        "Поле assessed НЕ ДОЛЖНО быть пустым. Если по правилу нет нарушения — оно всё равно обязано быть в assessed. "
        f"Если по правилу нет нарушения — не добавляй его в viol, но оно всё равно должно быть в assessed. "
        f"Поле order выбери из: {order_opts}. Поле where из: {where_opts}. "
        f"Суммарно не более {limit_items} нарушений; evidence ≤ {ev_max} символов. "
        "Evidence делай конкретным: цитата/фраза/дата/номер, без общих слов. "
        "Пример ответа без нарушений для 2 правил: {\"viol\":[], \"assessed\":[\"RULE1\",\"RULE2\"]}. "
        "Не добавляй никаких комментариев и текста вне JSON. Отвечай на русском языке."
    )


def _chunk_schema(rules_this_chunk: List[str], ev_max: int, limit_items: int) -> dict:
    """
    Динамическая JSON-схема для конкретного чанка правил: assessed обязан содержать
    все id из чанка ровно по одному, а r в viol ограничен этим же набором.
    """
    return {
        "type": "object",
        "properties": {
            "viol": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "r": {"type": "string", "enum": rules_this_chunk},
                        "s": {"type": "string", "enum": ["critical", "major", "minor"]},
                        "o": {"type": "string", "enum": ORDER_ENUM},
                        "w": {"type": "string", "enum": WHERE_ENUM},
                        "e": {"type": "string", "minLength": 1, "maxLength": ev_max},
                    },
                    "required": ["r", "s", "o", "w", "e"],
                    "additionalProperties": False,
                },
                "maxItems": limit_items,
                "uniqueItems": True,
            },
            "assessed": {
                "type": "array",
                "items": {"type": "string", "enum": rules_this_chunk},
                "uniqueItems": True,
                "minItems": len(rules_this_chunk),
                "maxItems": len(rules_this_chunk),
            },
        },
        "required": ["viol", "assessed"],
        "additionalProperties": False,
    }

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
    assessed_empty_chunks = 0
    total_ms = 0
    total_bytes = 0
    raw_samples: List[str] = []
    raw_full: List[str] = [] if os.getenv("LLM_INCLUDE_RAW", "0") == "1" else None

    SAMPLES_MAX = int(os.getenv("LLM_SAMPLES_MAX", "3"))
    SAMPLE_CHARS = int(os.getenv("LLM_SAMPLE_CHARS", "160"))

    # Выбор формата вывода ЛЛМ: JSON-Schema (если поддерживается), Grammar (GBNF) или простой JSON
    use_schema_env = os.getenv("OLLAMA_USE_SCHEMA", "auto").lower()
    if use_schema_env in ("1", "true", "yes", "on"):
        schema_supported = True
    elif use_schema_env in ("0", "false", "no", "off"):
        schema_supported = False
    else:
        # auto-детект через пробный вызов
        try:
            schema_supported = bool(schema_smoke_test())
        except Exception:
            schema_supported = False

    grammar_env = os.getenv("OLLAMA_USE_GRAMMAR", "auto").lower()
    if schema_supported:
        # если поддерживается JSON-Schema, используем его (предпочтительнее всего)
        chosen_mode = "schema"
    else:
        # по умолчанию (auto) предпочитаем grammar, т.к. он лучше сдерживает свободный текст;
        # если сервер/модель не поддерживают grammar — откатимся на простой JSON.
        if grammar_env in ("0", "false", "no", "off"):
            chosen_mode = "json"
        else:
            chosen_mode = "grammar"
            try:
                if not grammar_smoke_test():
                    chosen_mode = "json"
            except Exception:
                chosen_mode = "json"

    chunks = _chunks(RULE_ID_ENUM, CHUNK_SIZE)
    rules_per_chunk: List[List[str]] = []
    parse_errors = 0
    assessed_weak_chunks = 0
    for rules_this_chunk in chunks:
        rules_per_chunk.append(list(rules_this_chunk))
        q = _compact_question(rules_this_chunk, LIMIT_ITEMS, EV_MAX)
        t0 = time.time()
        # динамическая схема под чанк (если выбран режим schema)
        per_chunk_schema = _chunk_schema(rules_this_chunk, EV_MAX, LIMIT_ITEMS) if chosen_mode == "schema" else None
        raw = chat_ollama(
            system="Ты строгий аудитор медицинских документов РК. Возвращай только валидный JSON по заданной схеме, без какого-либо текста вне JSON.",
            question=q,
            text=condensed,
            model=STAC_MODEL,
            temperature=0.0,
            num_predict=NUM_PREDICT,
            num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "3072")),
            keep_alive=os.getenv("KEEP_ALIVE", "30m"),
            use_json_format=(chosen_mode == "json"),
            timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "180")),
            connect_timeout=int(os.getenv("OLLAMA_TIMEOUT_CONNECT", "5")),
            retries=int(os.getenv("OLLAMA_RETRIES", "0")),
            grammar=(COMPACT_AUDIT_GBNF if chosen_mode == "grammar" else None),
            json_schema=(per_chunk_schema if chosen_mode == "schema" else None),
        )
        dt = int((time.time() - t0) * 1000)
        total_ms += dt
        total_bytes += len(raw.encode("utf-8"))
        if len(raw_samples) < SAMPLES_MAX:
            raw_samples.append(raw[:SAMPLE_CHARS])
        if raw_full is not None:
            # опционально сохраняем полный сырой ответ (осторожно с размерами)
            raw_full.append(raw)

        try:
            data = coerce_json(raw)
        except Exception:
            # если распарсить не удалось — считаем, что нарушений нет, assessed заполним фолбэком
            parse_errors += 1
            data = {"viol": [], "assessed": []}
        # ожидаем {"viol":[...], "assessed":[...]}
        assessed_list = data.get("assessed", []) or []
        # если пусто — заполним всем чанком
        if not assessed_list:
            assessed_empty_chunks += 1
            assessed_list = list(rules_this_chunk)
        # если покрытие слабое (меньше половины валидных id) — фолбэк на полный чанк
        valid_in_chunk = [rid for rid in assessed_list if rid in rules_this_chunk]
        if len(set(valid_in_chunk)) < max(1, len(rules_this_chunk) // 2):
            assessed_weak_chunks += 1
            assessed_list = list(rules_this_chunk)
        for rid in assessed_list:
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
    llm_status["mode"] = chosen_mode
    llm_status["supports"] = {
        "json_schema": bool(schema_supported),
        "grammar": True if chosen_mode == "grammar" else False,
    }
    if parse_errors:
        llm_status["parse_errors"] = parse_errors
    if assessed_empty_chunks:
        llm_status["assessed_empty_chunks"] = assessed_empty_chunks
    if assessed_weak_chunks:
        llm_status["assessed_weak_chunks"] = assessed_weak_chunks

    # Список оцененных правил в итоговом порядке (по RULE_ID_ENUM)
    assessed_ordered = [rid for rid in RULE_ID_ENUM if rid in assessed_all]
    result["assessed_rule_ids"] = assessed_ordered
    llm_status["rules_per_chunk"] = rules_per_chunk
    if raw_full is not None:
        llm_status["raw_full"] = raw_full
    llm_status.pop("error", None)
    result["llm_status"] = llm_status

    return _ensure_status(result)
