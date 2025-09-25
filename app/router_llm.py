# app/router_llm.py
from __future__ import annotations
import json
import os
import re
from typing import Dict, List, Tuple

from .ollama_client import chat_ollama

# Префиксы должны совпадать с rule_id: "SURG-...", "CARD-..." и т.д.
PROFILE_LABELS: Dict[str, str] = {
    "GEN": "Общие",
    "STAC": "Стационар",
    "DHS": "Дневной стационар",
    "ER": "Приёмное отделение",
    "SURG": "Хирургия",
    "ANES": "Анестезиология",
    "INF": "Инфекционные",
    "OBG": "Акушерство/Гинекология",
    "NEO": "Неонатология",
    "CARD": "Кардиология",
    "NEPH": "Нефрология",
    "NEURO": "Неврология",
    "HEM": "Гематология (взрослые)",
    "ONC": "Онкология",
    "PONC": "Детская онко-гематология",
    "RH": "Ревматология",
    "URO": "Урология/Андрология",
    "GH": "Гастро/Гепато",
    "PULM": "Пульмонология",
    "PED": "Педиатрия",
    "PSURG": "Детская хирургия",
    "ORTHO": "Травма/Ортопедия",
    "NSURG": "Нейрохирургия",
}

ROUTER_SYSTEM = """Ты — клинический маршрутизатор. По тексту меддокумента определи, какие ПРОФИЛИ правил релевантны.
Профили (коды): GEN, STAC, DHS, ER, SURG, ANES, INF, OBG, NEO, CARD, NEPH, NEURO, HEM, ONC, PONC, RH, URO, GH, PULM, PED, PSURG, ORTHO, NSURG.
Выбери до 6 штук. Всегда включай GEN. Если явный стационар — добавь STAC; если дневной — DHS; приём — ER.
Верни строго JSON без пояснений: {"profiles":["CARD","STAC","GEN"],"confidence":{"CARD":0.82,"STAC":0.7,"GEN":1.0},"reason":"кратко почему"}.
"""

ROUTER_USER = """Определи релевантные профили для проверки правил. Если профиль неочевиден — не включай его."""

_KEYWORDS = [
    ("OBG", r"\b(роды|кесарев|беремен|акушер|гинеколог)\b"),
    ("NEO", r"\b(новорожд|апгар|апґар|вес при рожд|родильн)\b"),
    ("CARD", r"\b(инфаркт|ишемическ|элевац|тропонин|экг|эхо[ -]?кг|стент)\b"),
    ("PULM", r"\b(пневмон|хобл|бронхит|спирометр|s?p[o0]2|оксиген|сатурац)\b"),
    ("NEURO", r"\b(инсульт|ниhss|очагов[ые]|парез|парезы|афази)\b"),
    ("SURG", r"\b(лапар|операц|хирург|удалени[ея]|шов|дренаж)\b"),
    ("ANES", r"\b(анестез|интубац|аса\s?[IIVX])\b"),
    ("INF", r"\b(инфекц|санэпид|изоляц|контакт|очаг)\b"),
    ("URO", r"\b(цисто|катетер|простата|пса|уролог)\b"),
    ("GH", r"\b(цирроз|гепатит|фгдс|колоноскоп|эластограф)\b"),
    ("NEPH", r"\b(хбп|скф|диализ|нефро)\b"),
    ("ORTHO", r"\b(перелом|иммобилизац|остеосинтез|гипс)\b"),
    ("NSURG", r"\b(черепно-мозг|вчд|краниотом|нейрохирург)\b"),
    ("ONC", r"\b(опухол|tnm|стадия\s?([0-4])|химиотерап|лучев)\b"),
    ("HEM", r"\b(анемия|миел|лейк|тромбоцит|трансфуз)\b"),
    ("PED", r"\b(ребёнок|ребенок|мальчик|девочка|детск)\b"),
    ("PSURG", r"\b(детск[аяие]\s+хирург|врождённ|врожденн)\b"),
    ("RH", r"\b(ревмат|биологич|иммуносупрес|acpa|рф\s?полож)\b"),
    ("DHS", r"\b(дневн(ой|ом) стационар|ДС\\b)\b"),
    ("ER", r"\b(приёмн(ое|ом)|триаж|сортировк|неотлож)\b"),
    ("STAC", r"\b(стационар(е|а)|койко-день|выписн(ой|а)|история болезни)\b"),
]

def heuristic_profiles(text: str, limit: int = 6) -> List[str]:
    t = text.lower()
    hits: Dict[str, int] = {}
    for code, rx in _KEYWORDS:
        if re.search(rx, t):
            hits[code] = hits.get(code, 0) + 1
    # Базовые
    base = ["GEN"]
    if re.search(_KEYWORDS[-1][1], t):  # STAC
        base.append("STAC")
    if re.search(_KEYWORDS[-2][1], t):  # ER
        base.append("ER")
    if re.search(_KEYWORDS[-3][1], t):  # DHS
        base.append("DHS")
    # Топ-N по совпадениям
    ordered = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)
    rest = [k for k, _ in ordered if k not in base]
    profs = base + rest
    # убрать дубликаты, ограничить
    seen = set()
    out = []
    for p in profs:
        if p not in seen:
            out.append(p)
            seen.add(p)
        if len(out) >= limit:
            break
    return out or ["GEN"]

def classify_profiles_llm(text: str, limit: int = 6) -> Tuple[List[str], Dict[str, float], str]:
    model = os.getenv("ROUTER_MODEL") or os.getenv("OLLAMA_MODEL") or "llama3.1"
    raw = chat_ollama(
        system=ROUTER_SYSTEM,
        question=ROUTER_USER,
        text=text,
        model=model,
        temperature=0.0,
        num_predict=128,
        num_ctx=min(int(os.getenv("OLLAMA_NUM_CTX", "2048")), 2048)
    )
    try:
        data = json.loads(raw)
        profiles = [p for p in data.get("profiles", []) if p in PROFILE_LABELS]
        if "GEN" not in profiles:
            profiles = ["GEN"] + profiles
        if limit and len(profiles) > limit:
            profiles = profiles[:limit]
        conf = {k: float(v) for k, v in (data.get("confidence") or {}).items() if k in PROFILE_LABELS}
        reason = str(data.get("reason") or "")
        return profiles, conf, reason
    except Exception:
        return [], {}, ""

def detect_profiles(text: str, limit: int = 6) -> Tuple[List[str], Dict[str, float], str, bool]:
    """Возвращает (profiles, confidences, reason, from_llm)."""
    profs, conf, reason = classify_profiles_llm(text, limit=limit)
    if profs:
        return profs, conf, reason, True
    # фолбэк — ключевые слова
    profs2 = heuristic_profiles(text, limit=limit)
    return profs2, {}, "heuristic", False
