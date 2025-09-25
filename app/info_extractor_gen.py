# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional
from .datetime_utils import parse_dt, fmt

RX = {
    # ФИО: варианты "Ф.И.О.", "Фамилия Имя Отчество", "Пациент:"
    "fio": re.compile(r"(?:Ф\.?\s*И\.?\s*О\.?|ФИО|Пациент|Фамилия\s*Имя(?:\s*Отчество)?)\s*[:\-]\s*([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})", re.I),

    "iin": re.compile(r"\b\d{12}\b"),

    # ДР/возраст: "Дата рождения:", "Год рождения:", "Возраст: 56 лет"
    "dob": re.compile(r"(дата|год)\s*рожд[её]н[ия]\s*[:\-]?\s*(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}|\d{4})", re.I),
    "age": re.compile(r"возраст\s*[:\-]?\s*(\d{1,3})\s*лет", re.I),

    # Пол: "Пол: муж/жен", "М/Ж" в отдельных местах
    "sex": re.compile(r"\bпол\s*[:\-]?\s*(муж(?:ской)?|жен(?:ский)?)\b", re.I),
    "sex_short": re.compile(r"\b(м|ж)\b", re.I),

    # № истории: "История болезни №", "ИБ №", "№ ИБ", "ист.бол. №"
    "histno": re.compile(r"(истор(?:ия|и)\s*(?:болезни|родов)|ИБ|ист\.?\s*бол\.)\s*№\s*([A-Za-zА-Яа-я0-9\-\/]+)", re.I),

    # МО/отделение
    "org": re.compile(r"(ГКП|КГП|больниц[аы]|поликлиник[аы]|центр|клиник[аы]|наименовани[ея]\s*мед)", re.I),
    "dept": re.compile(r"(отделени[ея]\s*[:\-]?\s*[А-ЯЁA-Za-zа-яё0-9 \-]+)", re.I),

    # Поступление/выписка + даты
    "admission": re.compile(r"(поступил[аи]?|дата\s+поступ|время\s+поступ)", re.I),
    "discharge": re.compile(r"(выписан[ао]?|дата\s+выписк|выписной\s+эпикриз)", re.I),
    "date": re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b"),

    # Диагнозы + МКБ-10
    "diagnosis_block": re.compile(r"(диагноз(ы)?(\s*[:\-])?.{0,400})", re.I | re.S),
    "icd10": re.compile(r"\b([A-TV-ZА-ЯЁ][0-9][0-9][A-ZА-ЯЁ0-9](?:\.[0-9]{1,2})?)\b"),

    # Согласия, подписи, исследования
    "consent": re.compile(r"(информированн\w*\s+согласие|добровольн\w*\s+информированн\w*\s+согласие)", re.I),
    "consent_sig": re.compile(r"(подпис[ь|ан]|ФИО|паспорт|пациент|законн\w*\s+представител\w*)", re.I),
    "lab": re.compile(r"(оак|оам|кщс|абг|биохими|э\W?к\W?г|узи|рентген|кт|мрт)", re.I),
    "signature": re.compile(r"(врач|лечащий\s+врач|заведующ|ответственн\w*).{0,50}([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ]\.){1,2}|[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+)", re.I),

    # Выписной эпикриз — структура
    "discharge_title": re.compile(r"(выписн\w*\s+эпикриз)", re.I),
    "block_diag": re.compile(r"(диагноз)", re.I),
    "block_just": re.compile(r"(обосновани[ея])", re.I),
    "block_treat": re.compile(r"(провед[её]нн\w*\s+лечени\w*|терап\w*)", re.I),
    "block_outcome": re.compile(r"(исход|состояние\s+при\s+выписке)", re.I),
    "block_recom": re.compile(r"(рекомендац)", re.I),
    "block_regimen": re.compile(r"(режим\s*:\s*[^\n\r]+)", re.I),
    "block_diet": re.compile(r"(диет[аы]\s*:\s*[^\n\r]+)", re.I),
    "block_follow": re.compile(r"(явка|контрол[ья])", re.I),

    "med_line": re.compile(r"^[ \t\-\•\*]?\s*[A-ЯЁA-Za-z].{0,120}(\d+\s*(мг|мл|ед))", re.I | re.M),
    "freq": re.compile(r"(раза?\s+в\s+день|кажд[а-я]+\s*\d+\s*(час|ч))", re.I),
    "duration": re.compile(r"(дн(ей|я)|недел[яи]?|сут(ок|ки))", re.I),
}


def extract_general(text: str) -> Dict[str, Any]:
    t = text or ""

    def _find(pat, default=""):
        m = pat.search(t)
        return m.group(0) if m else default

    out: Dict[str, Any] = {
        "fio_line": "",
        "iin": "",
        "dob_or_age": "",
        "sex": "",
        "hist_no": "",
        "org_present": False,
        "dept_line": "",
        "admission_dt_str": "",
        "discharge_dt_str": "",

        "icd10_codes": [],
        "consents": {"count": 0, "with_sign": 0, "with_date": 0},
        "labs_with_dates": 0,
        "signatures_count": 0,

        "discharge_struct": {
            "has_title": False,
            "has_diag": False,
            "has_just": False,
            "has_treat": False,
            "has_outcome": False,
            "has_recom": False,
            "has_regimen": False,
            "has_diet": False,
            "has_follow": False,
        },
        "meds_at_discharge": {
            "has_any": False,
            "has_dose": False,
            "has_freq": False,
            "has_duration": False
        }
    }

    # Шапка
    m = RX["fio"].search(t); out["fio_line"] = m.group(0) if m else ""
    m = RX["iin"].search(t); out["iin"] = m.group(0) if m else ""
    m = RX["dob"].search(t); out["dob_or_age"] = m.group(0) if m else ""
    m = RX["sex"].search(t); out["sex"] = m.group(0) if m else ""
    m = RX["histno"].search(t); out["hist_no"] = m.group(0) if m else ""
    out["org_present"] = bool(RX["org"].search(t))
    m = RX["dept"].search(t); out["dept_line"] = m.group(0) if m else ""
    # Даты
    adm = RX["admission"].search(t); out["admission_dt_str"] = (adm and RX["date"].search(t[adm.start():adm.end()+80])) and RX["date"].search(t[adm.start():adm.end()+80]).group(0) or ""
    dis = RX["discharge"].search(t); out["discharge_dt_str"] = (dis and RX["date"].search(t[dis.start():dis.end()+180])) and RX["date"].search(t[dis.start():dis.end()+180]).group(0) or ""

    # Диагноз + МКБ-10
    diag_blocks = RX["diagnosis_block"].finditer(t)
    icds = set()
    for m in diag_blocks:
        block = m.group(1)[:400]
        for c in RX["icd10"].finditer(block):
            icds.add(c.group(1))
    out["icd10_codes"] = sorted(icds)

    # Согласия
    consents = RX["consent"].finditer(t)
    cnt = with_sign = with_date = 0
    for m in consents:
        cnt += 1
        blk = t[max(0, m.start()-80): m.end()+260]
        if RX["consent_sig"].search(blk): with_sign += 1
        if RX["date"].search(blk): with_date += 1
    out["consents"] = {"count": cnt, "with_sign": with_sign, "with_date": with_date}

    # Анализы с датами
    lc = 0
    for m in RX["lab"].finditer(t):
        blk = t[max(0, m.start()-40): m.end()+60]
        if RX["date"].search(blk):
            lc += 1
    out["labs_with_dates"] = lc

    # Подписи исполнителей
    out["signatures_count"] = len(list(RX["signature"].finditer(t)))

    # Выписной эпикриз — структура
    ds = out["discharge_struct"]
    ds["has_title"]   = bool(RX["discharge_title"].search(t))
    ds["has_diag"]    = bool(RX["block_diag"].search(t))
    ds["has_just"]    = bool(RX["block_just"].search(t))
    ds["has_treat"]   = bool(RX["block_treat"].search(t))
    ds["has_outcome"] = bool(RX["block_outcome"].search(t))
    ds["has_recom"]   = bool(RX["block_recom"].search(t))
    ds["has_regimen"] = bool(RX["block_regimen"].search(t))
    ds["has_diet"]    = bool(RX["block_diet"].search(t))
    ds["has_follow"]  = bool(RX["block_follow"].search(t))

    # Рекомендации (препараты)
    meds_lines = RX["med_line"].finditer(t)
    has_any = False; has_dose = False; has_freq = False; has_duration = False
    for m in meds_lines:
        has_any = True
        line = m.group(0)
        if RX["freq"].search(line): has_freq = True
        if RX["duration"].search(line): has_duration = True
        if re.search(r"\d+\s*(мг|мл|ед)", line, re.I): has_dose = True
    out["meds_at_discharge"] = {
        "has_any": has_any, "has_dose": has_dose, "has_freq": has_freq, "has_duration": has_duration
    }

    return out
