# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Any, List
import re
from .datetime_utils import within_minutes, days_between, is_work_hours, fmt, parse_dt

def _v(rule_id: str, title: str, where: str, ok: bool, evidence: str,
       severity="major", required=True, order="Приказ 27"):
    item = {
        "rule_id": rule_id,
        "title": title,
        "severity": severity,
        "required": required,
        "order": order,
        "where": where,
        "evidence": evidence
    }
    return ("pass" if ok else "fail", item)

def validate_stac_det(tl: Dict[str, Any], full_text: str | None = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Детерминированные проверки по стационару (Приказ №27).
    ВНИМАНИЕ: никаких локальных import внутри функции (чтобы не ловить UnboundLocalError).
    """
    passes: List[Dict[str,Any]] = []
    violations: List[Dict[str,Any]] = []

    def add(res):
        kind, item = res
        (passes if kind=="pass" else violations).append(item)

    # 1) ≤30 мин ER→Ward
    if tl.get("er_exam_dt") or tl.get("ward_exam_dt"):
        ok = within_minutes(tl.get("er_exam_dt"), tl.get("ward_exam_dt"), 30)
        ev = f"ER:{fmt(tl.get('er_exam_dt'))} → Ward:{fmt(tl.get('ward_exam_dt'))}"
        add(_v("STAC-27-ER-WARD-EXAM-30MIN", "Осмотр отделения ≤30 мин при экстренной",
               "приёмное/отделение", bool(ok), ev))

    # 2) Первичный осмотр заведующим в рабочее время (+ наличие «заведующ» рядом)
    head_time_ok = bool(is_work_hours(tl.get("head_primary_dt")))
    head_role_ok = False
    if full_text:
        m = re.search(r"(первичн\w*\s+осмотр.{0,200})", full_text, re.I | re.S)
        if m:
            blk = full_text[max(0, m.start()-80): m.end()+160]
            head_role_ok = bool(re.search(r"заведующ", blk, re.I))
    ok_head = head_time_ok and head_role_ok
    add(_v("STAC-27-HEAD-PRIMARY-D0", "Первичный осмотр Заведующим в рабочее время",
           "первичный осмотр", ok_head, f"time_ok:{head_time_ok} role_ok:{head_role_ok} dt:{fmt(tl.get('head_primary_dt'))}"))

    # 3) Обоснование диагноза ≤3 суток
    if tl.get("admission_dt") and tl.get("diag_justify_dt"):
        d = days_between(tl["admission_dt"], tl["diag_justify_dt"])
        ok = (d is not None and d <= 3.0)
        ev = f"Поступл:{fmt(tl['admission_dt'])} → Обоснование:{fmt(tl['diag_justify_dt'])} ~ {d:.2f} сут" if d is not None else "нет данных"
        add(_v("STAC-27-DIAG-JUSTIFY-D3", "Обоснование диагноза ≤ 3 суток",
               "обоснование диагноза", ok, ev))

    # 4) Предоперационный эпикриз — полнота (если есть)
    pre = tl.get("preop_epicrisis") or {}
    if pre.get("exists"):
        ok = all([pre.get("has_indications"),
                  pre.get("has_complaints"),
                  pre.get("has_anamnesis_vitae"),
                  pre.get("has_anamnesis_morbi"),
                  pre.get("has_somatic_status")])
        ev = (f"Индик:{pre.get('has_indications')} Жал:{pre.get('has_complaints')} "
              f"АЖ:{pre.get('has_anamnesis_vitae')} АЗ:{pre.get('has_anamnesis_morbi')} "
              f"Статус:{pre.get('has_somatic_status')}")
        add(_v("STAC-27-PREOP-EPICRISIS-CONTENT", "Предоперационный эпикриз — полнота",
               "предоперационный эпикриз", ok, ev))

    # 5) Протокол операции — поля (если есть)
    op = tl.get("op_protocol") or {}
    if op.get("exists"):
        ok = all([
            op.get("ab_prophylaxis"),
            op.get("pre_diag"),
            op.get("post_diag"),
            op.get("op_name"),
            bool(op.get("blood_loss_ml")),
            op.get("anesthesiologist"),
            op.get("nurse"),
            op.get("surgeon")
        ])
        ev = (f"AB:{op.get('ab_prophylaxis')} pre/post:{op.get('pre_diag')}/{op.get('post_diag')} "
              f"op:{op.get('op_name')} blood:{op.get('blood_loss_ml')} "
              f"A/N/S:{op.get('anesthesiologist')}/{op.get('nurse')}/{op.get('surgeon')}")
        add(_v("STAC-27-OP-PROTOCOL-FIELDS", "Протокол операции — обязательные поля",
               "операционный протокол", ok, ev, severity="critical"))

    # 6) Анестезия → Операция ≤30 минут
    if tl.get("anes_protocol_dt") and tl.get("op_protocol_dt"):
        ok = within_minutes(tl["anes_protocol_dt"], tl["op_protocol_dt"], 30)
        ev = f"Анестезия:{fmt(tl['anes_protocol_dt'])} → Операция:{fmt(tl['op_protocol_dt'])}"
        add(_v("STAC-27-ANES-OP-TIME-DELTA", "Анестезия перед операцией (≤30 минут)",
               "анестезия/операция", bool(ok), ev))

    # 7) Послеоперационный дневник — наличие (если была операция)
    if op.get("exists"):
        has_post = False
        if full_text:
            has_post = bool(re.search(r"(послеоперационн\w*\s+дневник)", full_text, re.I))
        add(_v("STAC-27-POSTOP-NOTE", "Послеоперационный дневник — наличие",
               "послеоперационный дневник", has_post, f"операция есть → дневник:{has_post}"))

    # 8) Предтрансфузионный эпикриз — параметры
    tr = tl.get("transfusion_pre") or {}
    if tr.get("exists"):
        ok = all([tr.get("cbc_dt"), tr.get("abg_dt"), tr.get("pulse"),
                  tr.get("bp"), tr.get("spo2"), tr.get("hb")])
        ev = (f"OAK:{tr.get('cbc_dt')} KЩC:{tr.get('abg_dt')} "
              f"P/BP/SpO2/Hb:{tr.get('pulse')}/{tr.get('bp')}/{tr.get('spo2')}/{tr.get('hb')}")
        add(_v("STAC-27-TRANSFUSION-PRE-EPICRISIS", "Предтрансфузионный эпикриз — параметры",
               "предтрансфузионный эпикриз", ok, ev, severity="critical"))

    # 9) СЛР — ≥30 мин, контроль каждые 5 мин
    cpr = tl.get("cpr") or {}
    if cpr.get("present"):
        ok = (cpr.get("duration_min", 0) >= 30) and bool(cpr.get("every_5_min_checks"))
        ev = f"Длительность:{cpr.get('duration_min')}; каждые 5 мин:{cpr.get('every_5_min_checks')}"
        add(_v("STAC-27-CPR-LOG-30MIN", "СЛР — ≥30 мин, контроль каждые 5 мин",
               "реанимация/дневники", ok, ev, severity="critical"))

    # 10) Тяжёлое состояние — дневники каждые 3 часа
    if tl.get("severe_present") and tl.get("note_times"):
        ok = True
        prev = None
        for s in tl["note_times"]:
            dt = parse_dt(s)
            if prev and dt:
                from .datetime_utils import hours_between  # импорт ЛОКАЛЬНОГО НЕТ (это другой символ), но лучше наверху
                if hours_between(prev, dt) and hours_between(prev, dt) > 3.0:
                    ok = False
                    break
            prev = dt or prev
        add(_v("STAC-27-SEVERE-3H-NOTES", "Тяжёлое состояние — дневники каждые 3 часа",
               "дневники", ok, f"всего записей: {len(tl['note_times'])}"))

    # 11) Клинический диагноз — к 3-м суткам
    if tl.get("admission_dt") and tl.get("clinical_diag_dt"):
        ok = (days_between(tl["admission_dt"], tl["clinical_diag_dt"]) or 999) <= 3.0
        ev = f"Поступл:{fmt(tl['admission_dt'])} → Клин.диагноз:{fmt(tl['clinical_diag_dt'])}"
        add(_v("STAC-27-CLINICAL-DIAG-D3", "Клинический диагноз — к 3-м суткам",
               "диагноз/эпикриз", ok, ev))

    # 12) Этапный эпикриз — на 10-е сутки
    if tl.get("admission_dt") and tl.get("stage_epicrisis_dt"):
        ok = (days_between(tl["admission_dt"], tl["stage_epicrisis_dt"]) or 999) <= 10.5
        ev = f"Поступл:{fmt(tl['admission_dt'])} → Этапный:{fmt(tl['stage_epicrisis_dt'])}"
        add(_v("STAC-27-STAGE-EPICRISIS-D10", "Этапный эпикриз — на 10-е сутки",
               "этапный эпикриз", ok, ev, severity="minor"))

    # 13) Консилиум ≥3 врачей к 3-м суткам при тяжёлом состоянии
    if tl.get("severe_present"):
        ok = False
        ev = "не найден"
        if full_text and tl.get("admission_dt"):
            for m in re.finditer(r"(консилиум.{0,500})", full_text, re.I | re.S):
                blk = m.group(1)
                cnt = len(re.findall(r"(врач|хирург|анестезиолог|реаниматолог|терапевт|невролог|кардиолог)", blk, re.I))
                dt = None
                mdt = re.search(r"\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}", blk)
                if mdt:
                    dt = parse_dt(mdt.group(0))
                in3d = (dt is not None and days_between(tl["admission_dt"], dt) is not None
                        and days_between(tl["admission_dt"], dt) <= 3.0)
                if cnt >= 3 and in3d:
                    ok = True
                    ev = f"врачей:{cnt} дата:{fmt(dt)}"
                    break
        add(_v("STAC-27-CONSILIUM-D3-SEVERE", "Консилиум ≥3 врачей к 3-м суткам (тяжёлое)",
               "консилиум", ok, ev))

    return {"passes": passes, "violations": violations}
