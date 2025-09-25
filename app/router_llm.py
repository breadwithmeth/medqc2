from __future__ import annotations
import json, os, re
from typing import Dict, List, Tuple
from .ollama_client import chat_ollama

PROFILE_LABELS: Dict[str, str] = {
    "GEN":"Общие", "STAC":"Стационар", "DHS":"Дневной стационар", "ER":"Приёмное",
    "SURG":"Хирургия", "ANES":"Анестезиология", "INF":"Инфекционные", "OBG":"Акушерство/Гинекология",
    "NEO":"Неонатология", "CARD":"Кардиология", "NEPH":"Нефрология", "NEURO":"Неврология",
    "HEM":"Гематология", "ONC":"Онкология", "PONC":"Детская онко-гематология", "RH":"Ревматология",
    "URO":"Урология/Андрология", "GH":"Гастро/Гепато", "PULM":"Пульмонология", "PED":"Педиатрия",
    "PSURG":"Детская хирургия", "ORTHO":"Травма/Ортопедия", "NSURG":"Нейрохирургия",
}

ROUTER_SYSTEM = """Ты — клинический маршрутизатор. По тексту меддокумента выбери до 3 релевантных ПРОФИЛЕЙ.
Всегда включай GEN. Если явный стационар — добавь STAC, если ДС — DHS, если приёмник — ER.
Верни строго JSON: {"profiles":["CARD","STAC","GEN"],"confidence":{"CARD":0.8},"reason":"кратко"}."""

ROUTER_USER = "Определи профили для проверки правил. Если профиль неочевиден — не включай его."

_KEYWORDS = [
    ("OBG", r"\b(роды|кесарев|беремен|акушер|гинеколог)\b"),
    ("NEO", r"\b(новорожд|апгар|антропометр)\b"),
    ("CARD", r"\b(инфаркт|ишемическ|тропонин|экг|эхо[ -]?кг|стент)\b"),
    ("PULM", r"\b(пневмон|хобл|бронхит|s?p[o0]2|сатурац|кислород)\b"),
    ("NEURO", r"\b(инсульт|nihss|очагов|парез|афази)\b"),
    ("SURG", r"\b(лапар|операц|хирург|шов|дренаж)\b"),
    ("ANES", r"\b(анестез|интубац|asa\\s?[iIvVxX])\b"),
    ("INF", r"\b(инфекц|санэпид|изоляц)\b"),
    ("URO", r"\b(цисто|катетер|простата|пса|уролог)\b"),
    ("GH", r"\b(цирроз|гепатит|фгдс|колоноскоп|child|meld)\b"),
    ("NEPH", r"\b(хбп|скф|креатинин|диализ|нефро)\b"),
    ("ORTHO", r"\b(перелом|иммобилизац|остеосинтез|гипс)\b"),
    ("NSURG", r"\b(черепно-мозг|вчд|краниотом|нейрохирург)\b"),
    ("ONC", r"\b(опухол|tnm|стадия\\s?[0-4]|химиотерап|лучев)\b"),
    ("HEM", r"\b(анемия|миел|лейк|тромбоцит|трансфуз)\b"),
    ("PED", r"\b(ребёнок|ребенок|мальчик|девочка|детск)\b"),
    ("PSURG", r"\b(детск[аяие]\\s+хирург|врожд[её]н)\b"),
    ("RH", r"\b(ревмат|биологич|иммуносупрес|acpa|рф)\b"),
    ("DHS", r"\b(дневн(ой|ом)\\s+стационар|\\bДС\\b)\b"),
    ("ER", r"\b(приёмн(ое|ом)|триаж|сортировк|неотлож)\b"),
    ("STAC", r"\b(стационар(е|а)|койко-день|выписн(ой|а)|история болезни)\b"),
]

def heuristic_profiles(text: str, limit: int = 3) -> list[str]:
    t = text.lower()
    hits = {}
    for code, rx in _KEYWORDS:
        if re.search(rx, t):
            hits[code] = hits.get(code, 0) + 1
    base = ["GEN"]
    if re.search(_KEYWORDS[-1][1], t): base.append("STAC")
    if re.search(_KEYWORDS[-2][1], t): base.append("ER")
    if re.search(_KEYWORDS[-3][1], t): base.append("DHS")
    rest = [k for k,_ in sorted(hits.items(), key=lambda kv: kv[1], reverse=True) if k not in base]
    out = []
    for p in base + rest:
        if p not in out:
            out.append(p)
        if len(out) >= limit:
            break
    return out

def classify_profiles_llm(text: str, limit: int = 3) -> tuple[list[str], dict[str,float], str]:
    model = os.getenv("ROUTER_MODEL") or os.getenv("OLLAMA_MODEL") or "llama3.1:8b-instruct-q5_1"
    raw = chat_ollama(ROUTER_SYSTEM, ROUTER_USER, text, model=model, num_predict=128, num_ctx=1024)
    try:
        data = json.loads(raw)
        profs = [p for p in data.get("profiles", []) if p in PROFILE_LABELS]
        if "GEN" not in profs: profs = ["GEN"] + profs
        if len(profs) > limit: profs = profs[:limit]
        conf = {k: float(v) for k,v in (data.get("confidence") or {}).items() if k in PROFILE_LABELS}
        return profs, conf, str(data.get("reason",""))
    except Exception:
        return [], {}, ""

def detect_profiles(text: str, limit: int = 3) -> tuple[list[str], dict[str,float], str, bool]:
    profs, conf, reason = classify_profiles_llm(text, limit=limit)
    if profs: return profs, conf, reason, True
    return heuristic_profiles(text, limit=limit), {}, "heuristic", False
