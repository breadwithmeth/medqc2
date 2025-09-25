# -*- coding: utf-8 -*-
from __future__ import annotations
import re

SEV_RU = {"critical": "критично", "major": "существенно", "minor": "незначительно"}
STATUS_RU = {"PASS": "СООТВЕТСТВУЕТ", "FAIL": "НАРУШЕНИЕ"}

# простая локализация тех.флагов в evidence
EV_REPLACERS = [
    (r"\btime_ok:True\b",  "раб. время: да"),
    (r"\btime_ok:False\b", "раб. время: нет"),
    (r"\brole_ok:True\b",  "заведующий: да"),
    (r"\brole_ok:False\b", "заведующий: нет"),
    (r"\bdt:\b",           "время:"),
    (r"\bpre/post:",       "до/после:"),
    (r"\bblood:",          "кровопотеря:"),
    (r"\bOAK:",            "ОАК:"),
    (r"\bKЩC:",            "КЩС:"),
    (r"\bP/BP/SpO2/Hb:",   "Пульс/АД/SpO₂/Hb:"),
]

def _loc_evidence(e: str) -> str:
    if not e: return e
    out = e
    for patt, repl in EV_REPLACERS:
        out = re.sub(patt, repl, out)
    return out

def localize_result(data: dict) -> dict:
    for k in ("passes","violations"):
        for it in data.get(k, []) or []:
            sev = (it.get("severity") or "").lower()
            if sev in SEV_RU:
                it["severity"] = SEV_RU[sev]
            ev = it.get("evidence") or ""
            it["evidence"] = _loc_evidence(ev)
            # статус
            st = it.get("status")
            if st in STATUS_RU:
                it["status"] = STATUS_RU[st]
    return data
