# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional, Tuple
from .datetime_utils import parse_dt, fmt, within_minutes, hours_between, days_between, is_work_hours

# Ключевые маркеры разделов / событий
RX = {
    "admission": re.compile(r"(поступил[аи]?|дата\s+поступ|время\s+поступ)", re.I),
    "er_exam": re.compile(r"(при[её]мн[ао]м\s+отделен|осмотр\s+в\s+при[её]мном)", re.I),
    "ward_exam": re.compile(r"(осмотр\s+врача\s+отделен|осмотр\s+отделенческ)", re.I),
    "head_primary": re.compile(r"(первичн\w+\s+осмотр|первичный\s+осмотр).{0,80}(заведующ|зав\.)", re.I | re.S),
    "diag_justify": re.compile(r"(обосновани[ея]\s+диагноз[ао])", re.I),
    "preop_epicrisis": re.compile(r"(предоперационн\w*\s+эпикриз)", re.I),
    "anes_protocol": re.compile(r"(протокол\s+анестез\w+|анестезиологическ\w+\s+пособи\w+)", re.I),
    "op_protocol": re.compile(r"(протокол\s+операц\w+)", re.I),
    "postop_note": re.compile(r"(послеоперационн\w*\s+дневник)", re.I),
    "cpr": re.compile(r"(сердечно[-\s]*легочн\w*\s+реанимац|СЛР)", re.I),
    "severe": re.compile(r"(тяжел\w*\s+состояни\w*)", re.I),
    "consilium": re.compile(r"(консилиум)", re.I),
    "stage_epicrisis": re.compile(r"(этапн\w*\s+эпикриз)", re.I),
    "clinical_diag": re.compile(r"(клинич\w*\s+диагноз)", re.I),
    "diet": re.compile(r"(диет[аы]\s*:\s*[^\n\r]+)", re.I),
    "regimen": re.compile(r"(режим\s*:\s*[^\n\r]+)", re.I),
    "transfusion_pre": re.compile(r"(предтрансфузионн\w*\s+эпикриз)", re.I),
}

DT_LINE = re.compile(r"(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}(?:[T\s]+\d{1,2}:\d{2}(?::\d{2})?)?)")

def _neighbor_dt(text: str, i: int, left: int = 200, right: int = 200) -> Optional[str]:
    s = max(0, i - left)
    e = min(len(text), i + right)
    m = DT_LINE.search(text[s:e])
    return m.group(1) if m else None

def _find_first(text: str, patt: re.Pattern) -> Tuple[Optional[int], Optional[str]]:
    m = patt.search(text)
    if not m:
        return None, None
    dt_str = _neighbor_dt(text, m.start())
    return m.start(), dt_str

def _find_all_blocks(text: str, patt: re.Pattern, window: int = 800) -> List[str]:
    out = []
    for m in patt.finditer(text):
        s = max(0, m.start() - 100)
        e = min(len(text), m.end() + window)
        out.append(text[s:e])
    return out

def _has_word(block: str, word_rx: re.Pattern) -> bool:
    return bool(word_rx.search(block))

def extract_timeline(text: str) -> Dict[str, Any]:
    t = text or ""
    # Базовые точки
    _, dt_adm = _find_first(t, RX["admission"])
    _, dt_er = _find_first(t, RX["er_exam"])
    _, dt_ward = _find_first(t, RX["ward_exam"])
    head_idx, dt_head = _find_first(t, RX["head_primary"])
    _, dt_diag = _find_first(t, RX["diag_justify"])
    _, dt_anes = _find_first(t, RX["anes_protocol"])
    _, dt_op = _find_first(t, RX["op_protocol"])

    # Предоперационный эпикриз — проверим наполненность
    preop_blocks = _find_all_blocks(t, RX["preop_epicrisis"])
    preop = {
        "exists": bool(preop_blocks),
        "has_indications": False,
        "has_complaints": False,
        "has_anamnesis_vitae": False,
        "has_anamnesis_morbi": False,
        "has_somatic_status": False,
        "quote": ""
    }
    if preop_blocks:
        b = preop_blocks[0]
        preop["quote"] = b[:180].replace("\n", " ")
        preop["has_indications"] = _has_word(b, re.compile(r"показан\w*\s+к\s+операц", re.I))
        preop["has_complaints"] = _has_word(b, re.compile(r"жалоб", re.I))
        preop["has_anamnesis_vitae"] = _has_word(b, re.compile(r"анамнез\s+жизн", re.I))
        preop["has_anamnesis_morbi"] = _has_word(b, re.compile(r"анамнез\s+заболеван", re.I))
        preop["has_somatic_status"] = _has_word(b, re.compile(r"(соматическ\w*\s+статус|объективн\w*\s+статус)", re.I))

    # Операционный протокол — поля
    op_blocks = _find_all_blocks(t, RX["op_protocol"])
    op_proto = {
        "exists": bool(op_blocks),
        "ab_prophylaxis": False,
        "pre_diag": False,
        "post_diag": False,
        "op_name": False,
        "blood_loss_ml": "",
        "complications": False,
        "biopsy_taken": False,
        "anesthesiologist": False,
        "nurse": False,
        "surgeon": False,
        "quote": ""
    }
    if op_blocks:
        b = op_blocks[0]
        op_proto["quote"] = b[:180].replace("\n", " ")
        op_proto["ab_prophylaxis"] = _has_word(b, re.compile(r"антибио\w*\s*профил|АБ-?профил", re.I))
        op_proto["pre_diag"] = _has_word(b, re.compile(r"диагноз\s*до\s*операц", re.I))
        op_proto["post_diag"] = _has_word(b, re.compile(r"диагноз\s*после\s*операц", re.I))
        op_proto["op_name"] = _has_word(b, re.compile(r"(операция|лапаротом|фиксац|резекц|остеосинтез|лапароскоп)", re.I))
        bl = re.search(r"(кровопотер[яи]\s*[:\-]\s*(\d+)\s*м?л?)", b, re.I)
        if bl:
            op_proto["blood_loss_ml"] = bl.group(2)
        op_proto["complications"] = _has_word(b, re.compile(r"осложнен|интраоперационн\w*", re.I))
        op_proto["biopsy_taken"] = _has_word(b, re.compile(r"биопс", re.I))
        op_proto["anesthesiologist"] = _has_word(b, re.compile(r"анестезиолог", re.I))
        op_proto["nurse"] = _has_word(b, re.compile(r"(мед\.?\s*сестра|медсестра)", re.I))
        op_proto["surgeon"] = _has_word(b, re.compile(r"(хирург|оперирующ)", re.I))

    # CPR
    cpr_blocks = _find_all_blocks(t, RX["cpr"])
    cpr = {"present": bool(cpr_blocks), "duration_min": 0, "every_5_min_checks": False, "quote": ""}
    if cpr_blocks:
        b = cpr_blocks[0]
        cpr["quote"] = b[:180].replace("\n", " ")
        # duration
        d1 = re.search(r"(\d{1,2})\s*мин", b, re.I)
        if d1:
            try: cpr["duration_min"] = int(d1.group(1))
            except: pass
        cpr["every_5_min_checks"] = bool(re.search(r"каждые?\s*5\s*мин", b, re.I))

    # Тяжёлое состояние и дневники
    severe_present = bool(RX["severe"].search(t))
    note_lines = []
    for m in re.finditer(r"(дневник[^\n\r]*)(.*)", t, re.I):
        line = (m.group(0) or "")[:160]
        note_lines.append(line)
    # конвертируем возможные часы в набор с датами
    note_times = []
    for line in note_lines:
        dt = parse_dt(line)
        if dt:
            note_times.append(dt)
    note_times_sorted = sorted(note_times)

    # Предтрансфузионный эпикриз
    transf_blocks = _find_all_blocks(t, RX["transfusion_pre"])
    transf = {
        "exists": bool(transf_blocks),
        "cbc_dt": False,
        "abg_dt": False,
        "pulse": False,
        "bp": False,
        "spo2": False,
        "hb": False,
        "quote": ""
    }
    if transf_blocks:
        b = transf_blocks[0]
        transf["quote"] = b[:180].replace("\n", " ")
        # очень простая проверка полей
        transf["cbc_dt"] = bool(re.search(r"(оак|общий\s+анализ\s+крови).{0,40}\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}", b, re.I))
        transf["abg_dt"] = bool(re.search(r"(кщс|абг|кислотно-щелочн).{0,40}\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}", b, re.I))
        transf["pulse"] = bool(re.search(r"(пульс|чсс)\s*[:\-]?\s*\d{2,3}", b, re.I))
        transf["bp"]    = bool(re.search(r"(АД|давлени\w*)\s*[:\-]?\s*\d{2,3}\s*/\s*\d{2,3}", b, re.I))
        transf["spo2"]  = bool(re.search(r"(сатурац|spo2)\s*[:\-]?\s*\d{2,3}", b, re.I))
        transf["hb"]    = bool(re.search(r"(Hb|гемоглобин)\s*[:\-]?\s*\d{2,3}", b, re.I))

    # Этапный эпикриз / клинический диагноз
    stage_idx, stage_dt_str = _find_first(t, RX["stage_epicrisis"])
    clin_idx, clin_dt_str = _find_first(t, RX["clinical_diag"])

    # Диета/режим (для сведения; детермин. проверка в другом месте)
    diet = None
    m_diet = RX["diet"].search(t)
    if m_diet: diet = m_diet.group(0)
    regimen = None
    m_reg = RX["regimen"].search(t)
    if m_reg: regimen = m_reg.group(0)

    out = {
        "admission_dt_str": dt_adm, "er_exam_dt_str": dt_er, "ward_exam_dt_str": dt_ward,
        "head_primary_dt_str": dt_head, "diag_justify_dt_str": dt_diag,
        "anes_protocol_dt_str": dt_anes, "op_protocol_dt_str": dt_op,
        "stage_epicrisis_dt_str": stage_dt_str, "clinical_diag_dt_str": clin_dt_str,
        "admission_dt": parse_dt(dt_adm) if dt_adm else None,
        "er_exam_dt": parse_dt(dt_er) if dt_er else None,
        "ward_exam_dt": parse_dt(dt_ward) if dt_ward else None,
        "head_primary_dt": parse_dt(dt_head) if dt_head else None,
        "diag_justify_dt": parse_dt(dt_diag) if dt_diag else None,
        "anes_protocol_dt": parse_dt(dt_anes) if dt_anes else None,
        "op_protocol_dt": parse_dt(dt_op) if dt_op else None,
        "stage_epicrisis_dt": parse_dt(stage_dt_str) if stage_dt_str else None,
        "clinical_diag_dt": parse_dt(clin_dt_str) if clin_dt_str else None,
        "preop_epicrisis": preop,
        "op_protocol": op_proto,
        "cpr": cpr,
        "severe_present": severe_present,
        "note_times": [fmt(x) for x in note_times_sorted],
        "diet_line": diet or "",
        "regimen_line": regimen or "",
    }
    return out
