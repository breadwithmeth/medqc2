# -*- coding: utf-8 -*-
from __future__ import annotations
from typing import Dict, Any, List
from .datetime_utils import parse_dt, fmt

def _v(rule_id, title, where, ok, evidence, severity="major", required=True, order="Оформление/Общие"):
    return ("pass" if ok else "fail", {
        "rule_id": rule_id, "title": title, "severity": severity, "required": required,
        "order": order, "where": where, "evidence": evidence
    })

def validate_gen_det(g: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    passes: List[Dict[str,Any]] = []
    violations: List[Dict[str,Any]] = []

    def add(res):
        kind, item = res
        (passes if kind=="pass" else violations).append(item)

    # GEN-IDENT-HEADER
    ok = all([
        bool(g.get("fio_line")),
        bool(g.get("dob_or_age")),
        bool(g.get("sex")),
        bool(g.get("iin")),
        bool(g.get("hist_no")),
        bool(g.get("org_present")),
        bool(g.get("admission_dt_str")),
    ])
    ev = f"FIO:{bool(g.get('fio_line'))} DOB/AGE:{bool(g.get('dob_or_age'))} SEX:{bool(g.get('sex'))} IIN:{bool(g.get('iin'))} №ист:{bool(g.get('hist_no'))} МО:{g.get('org_present')} Поступл:{bool(g.get('admission_dt_str'))} Выписка:{bool(g.get('discharge_dt_str'))}"
    add(_v("GEN-IDENT-HEADER","Шапка — идентификация пациента и МО","шапка/первая страница", ok, ev))

    # GEN-DATES-CONSISTENT (простая проверка: выписка после поступления)
    adm = parse_dt(g.get("admission_dt_str") or "")
    dis = parse_dt(g.get("discharge_dt_str") or "")
    ok2 = True
    if adm and dis:
        ok2 = dis >= adm
    add(_v("GEN-DATES-CONSISTENT","Хронология без противоречий","весь документ", ok2, f"Поступл:{fmt(adm)} → Вып:{fmt(dis)}"))

    # GEN-ICD10-CODING
    icds = g.get("icd10_codes") or []
    add(_v("GEN-ICD10-CODING","МКБ-10 у диагноза(ов)","диагнозы", bool(icds), f"МКБ-10: {', '.join(icds)[:120]}", severity="minor"))

    # GEN-CONSENTS
    c = g.get("consents") or {}
    ok3 = (c.get("count",0) > 0 and c.get("with_sign",0) >= 1 and c.get("with_date",0) >= 1)
    ev3 = f"всего:{c.get('count',0)} подпись:{c.get('with_sign',0)} дата:{c.get('with_date',0)}"
    add(_v("GEN-CONSENTS","Информированные согласия — есть подписи и даты","согласия/приложения", ok3, ev3))

    # GEN-LABS-DATED
    add(_v("GEN-LABS-DATED","Анализы/исследования — с датами","диагностика", g.get("labs_with_dates",0) > 0, f"с датами: {g.get('labs_with_dates',0)}", severity="minor"))

    # GEN-SIGNATURES
    add(_v("GEN-SIGNATURES","Подписи и ФИО исполнителей","концы записей/протоколов/эпикризов", g.get("signatures_count",0) >= 1, f"найдено подписей: {g.get('signatures_count',0)}"))

    # GEN-DISCHARGE-SUMMARY
    ds = g.get("discharge_struct") or {}
    ok4 = all([ds.get("has_title"), ds.get("has_diag"), ds.get("has_treat"), ds.get("has_recom")])
    ev4 = f"title:{ds.get('has_title')} diag:{ds.get('has_diag')} just:{ds.get('has_just')} treat:{ds.get('has_treat')} outcome:{ds.get('has_outcome')} recom:{ds.get('has_recom')} regimen:{ds.get('has_regimen')} diet:{ds.get('has_diet')} follow:{ds.get('has_follow')}"
    add(_v("GEN-DISCHARGE-SUMMARY","Выписной эпикриз — структура","выписной эпикриз", ok4, ev4))

    # GEN-MEDS-AT-DISCHARGE
    md = g.get("meds_at_discharge") or {}
    ok5 = (md.get("has_any") and md.get("has_dose") and md.get("has_freq") and md.get("has_duration"))
    ev5 = f"any:{md.get('has_any')} dose:{md.get('has_dose')} freq:{md.get('has_freq')} dur:{md.get('has_duration')}"
    add(_v("GEN-MEDS-AT-DISCHARGE","Препараты при выписке — доза/кратность/срок","рекомендации", ok5, ev5, severity="minor"))

    return {"passes": passes, "violations": violations}
