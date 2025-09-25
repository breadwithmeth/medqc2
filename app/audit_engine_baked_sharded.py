from __future__ import annotations
import json, os, re, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

from .ollama_client import chat_ollama
from .router_llm import detect_profiles
from .focus_text import focus_text

# Маппинг код профиля -> имя модели в Ollama
MODEL_PREFIX = os.getenv("MODEL_PREFIX", "medaudit")
# ВНИМАНИЕ: мы создали модели вида medaudit:<lowercase(profile)>
def model_for_profile(profile_code: str) -> str:
    return f"{MODEL_PREFIX}:{profile_code.lower()}"

# включать ли параллелизм по шардам
SHARD_CONCURRENCY = int(os.getenv("SHARD_CONCURRENCY", "2"))
NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "3072"))
NUM_PRED = int(os.getenv("NUM_PREDICT", "100"))
STRICT_ROUTER = os.getenv("STRICT_ROUTER", "1") == "1"
ROUTER_LIMIT = int(os.getenv("ROUTER_LIMIT", "3"))
def _pluck_json(s: str) -> str:
    m = re.search(r"\{.*\}\s*$", s, re.S)
    return m.group(0) if m else s

def _call_model(model: str, text: str) -> dict:
    raw = chat_ollama(
        system="",  # правила зашиты в модель
        question="Проверь документ по зашитым правилам и верни СТРОГО JSON.",
        text=text,
        model=model,
        temperature=0.0,
        num_predict=NUM_PRED,
        num_ctx=NUM_CTX,
        keep_alive=os.getenv("KEEP_ALIVE", "30m"),
        use_json_format=True,
        timeout=int(os.getenv("OLLAMA_TIMEOUT_READ", "300")),
    )
    raw = _pluck_json(raw)
    data = json.loads(raw)
    data.setdefault("passes", [])
    data.setdefault("violations", [])
    return data

def _merge(a: dict, b: dict) -> dict:
    # key = rule_id; при конфликте FAIL сильнее PASS
    out = {"passes": [], "violations": []}
    ix: Dict[str, Tuple[str, dict]] = {}  # rule_id -> ("PASS"/"FAIL", item)

    def feed(arr: List[dict], status: str):
        for it in arr:
            rid = str(it.get("rule_id") or "")
            if not rid: continue
            if rid in ix:
                prev_status, prev_item = ix[rid]
                if prev_status == "PASS" and status == "FAIL":
                    ix[rid] = ("FAIL", it)
            else:
                ix[rid] = (status, it)

    feed(a.get("passes", []), "PASS")
    feed(a.get("violations", []), "FAIL")
    feed(b.get("passes", []), "PASS")
    feed(b.get("violations", []), "FAIL")

    for status, item in ix.values():
        if status == "FAIL":
            out["violations"].append(item)
        else:
            out["passes"].append(item)
    return out

def audit_baked_sharded(text: str) -> dict:
    # 1) авто-детект профилей
    profs, conf, reason, from_llm = detect_profiles(text, limit=ROUTER_LIMIT)
    if not profs:
        profs = ["GEN"]
    if STRICT_ROUTER and profs:
        # берем только главный профиль (первый)
        profs = [profs[0]]

    # 2) фокус входа (сжатие) — см. новый focus_text ниже
    condensed = focus_text(text)

    # 3) вызываем строго один шард (или несколько, если вы отключите STRICT_ROUTER)
    models = [model_for_profile(p) for p in profs]
    # Жестко выключаем конкуррентность при одном вызове
    results = []
    for m in models:
        data, ms = _call_model(m, condensed)
        calls_info = [{"model": m, "ms": round(ms,1)}]
        results.append((data, calls_info))

    # 4) merge и сбор таймингов (оставьте вашу версию с debug, если добавляли)
    agg = {"passes": [], "violations": []}
    calls = []
    for data, info in results:
        agg = _merge(agg, data)
        calls += info

    return {
        "profiles_detected": profs,
        "profiles_confidence": conf,
        "profiles_reason": reason,
        "profiles_source": "llm" if from_llm else "heuristic",
        "models_called": [c["model"] for c in calls],
        "rules_total": len(agg["passes"]) + len(agg["violations"]),
        "passes": agg["passes"],
        "violations": agg["violations"],
        "debug": {"shard_calls": calls}
    }