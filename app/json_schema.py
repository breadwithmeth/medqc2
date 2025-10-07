# -*- coding: utf-8 -*-
from __future__ import annotations
import os

# ----- Перечень правил (фиксируем enum, чтобы не было мусора) -----
RULE_ID_ENUM = [
    # Стационар (Приказ 27)
    "STAC-27-ER-WARD-EXAM-30MIN",
    "STAC-27-HEAD-PRIMARY-D0",
    "STAC-27-DIAG-JUSTIFY-D3",
    "STAC-27-PREOP-EPICRISIS-CONTENT",
    "STAC-27-OP-PROTOCOL-FIELDS",
    "STAC-27-ANES-OP-TIME-DELTA",
    "STAC-27-POSTOP-NOTE",
    "STAC-27-TRANSFUSION-PRE-EPICRISIS",
    "STAC-27-CPR-LOG-30MIN",
    "STAC-27-SEVERE-3H-NOTES",
    "STAC-27-CLINICAL-DIAG-D3",
    "STAC-27-STAGE-EPICRISIS-D10",
    "STAC-27-CONSILIUM-D3-SEVERE",
    # Общие
    "GEN-IDENT-HEADER",
    "GEN-ICD10-CODING",
    "GEN-CONSENT",
    "GEN-SIGNATURES",
    "GEN-DIET-REGIMEN",
]

ORDER_ENUM = ["D0", "D1", "D2", "D3", "D4-9", "D10", "preop", "intraop", "postop", "timeline"]
WHERE_ENUM = [
    "приемное отделение",
    "история болезни",
    "обоснование диагноза",
    "предоперационный эпикриз",
    "протокол операции",
    "протокол анестезиологического пособия",
    "послеоперационный дневник",
    "лист назначений",
    "консилиум",
    "приказ/нормативный пункт",
]

# Человеческие заголовки правил (для вывода)
RULE_TITLES = {
    "STAC-27-ER-WARD-EXAM-30MIN": "Осмотр врача отделения в 30 минут после приёма (экстренно)",
    "STAC-27-HEAD-PRIMARY-D0": "Первичный осмотр заведующим (рабочее время, Д0)",
    "STAC-27-DIAG-JUSTIFY-D3": "Обоснование диагноза к 3-м суткам (с осмотром заведующего)",
    "STAC-27-PREOP-EPICRISIS-CONTENT": "Предоперационный эпикриз — обязательные поля",
    "STAC-27-OP-PROTOCOL-FIELDS": "Протокол операции — обязательные поля",
    "STAC-27-ANES-OP-TIME-DELTA": "Согласованность времени анест. пособия и операции",
    "STAC-27-POSTOP-NOTE": "Послеоперационный дневник",
    "STAC-27-TRANSFUSION-PRE-EPICRISIS": "Предтрансфузионный эпикриз — обязательные поля",
    "STAC-27-CPR-LOG-30MIN": "Реанимационные мероприятия — запись каждые 5 минут (30 мин)",
    "STAC-27-SEVERE-3H-NOTES": "Тяжёлое состояние — записи каждые 3 часа",
    "STAC-27-CLINICAL-DIAG-D3": "Клинический диагноз — к 3-м суткам",
    "STAC-27-STAGE-EPICRISIS-D10": "Этапный эпикриз — к 10-м суткам",
    "STAC-27-CONSILIUM-D3-SEVERE": "Консилиум ≥3 врачей к Д3 при тяжёлом состоянии",
    "GEN-IDENT-HEADER": "Шапка меддокумента — идентификация пациента и МО",
    "GEN-ICD10-CODING": "Кодирование диагнозов по МКБ-10",
    "GEN-CONSENT": "Информированные согласия",
    "GEN-SIGNATURES": "Подписи исполнителей (ФИО/должность/дата/время)",
    "GEN-DIET-REGIMEN": "Лечебный стол и режим в листе назначений",
}

# Базовая «важность» для PASS (чтобы была однородность формата)
RULE_SEVERITY = {
    "STAC-27-ER-WARD-EXAM-30MIN": "major",
    "STAC-27-HEAD-PRIMARY-D0": "major",
    "STAC-27-DIAG-JUSTIFY-D3": "major",
    "STAC-27-PREOP-EPICRISIS-CONTENT": "major",
    "STAC-27-OP-PROTOCOL-FIELDS": "major",
    "STAC-27-ANES-OP-TIME-DELTA": "major",
    "STAC-27-POSTOP-NOTE": "major",
    "STAC-27-TRANSFUSION-PRE-EPICRISIS": "major",
    "STAC-27-CPR-LOG-30MIN": "major",
    "STAC-27-SEVERE-3H-NOTES": "major",
    "STAC-27-CLINICAL-DIAG-D3": "major",
    "STAC-27-STAGE-EPICRISIS-D10": "major",
    "STAC-27-CONSILIUM-D3-SEVERE": "major",
    "GEN-IDENT-HEADER": "minor",
    "GEN-ICD10-CODING": "minor",
    "GEN-CONSENT": "minor",
    "GEN-SIGNATURES": "minor",
    "GEN-DIET-REGIMEN": "minor",
}

# ----- Лимиты (ужимаем текст) -----
LIMIT_ITEMS = int(os.getenv("LLM_LIMIT_ITEMS", "10"))
EVIDENCE_MAX = int(os.getenv("EVIDENCE_MAX_CHARS", "90"))  # короче
TITLE_MAX = int(os.getenv("TITLE_MAX_CHARS", "80"))

# ----- ПОЛНАЯ (человеческая) схема — если нужна где-то еще -----
AUDIT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_id":  {"type": "string", "enum": RULE_ID_ENUM},
        "title":    {"type": "string", "minLength": 1, "maxLength": TITLE_MAX},
        "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
        "required": {"type": "boolean"},
        "order":    {"type": "string", "enum": ORDER_ENUM},
        "where":    {"type": "string", "enum": WHERE_ENUM},
        "evidence": {"type": "string", "minLength": 1, "maxLength": EVIDENCE_MAX},
    },
    "required": ["rule_id", "title", "severity", "required", "order", "where", "evidence"],
    "additionalProperties": False,
}

AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "passes": {"type": "array", "items": AUDIT_ITEM_SCHEMA, "maxItems": LIMIT_ITEMS, "uniqueItems": True},
        "violations": {"type": "array", "items": AUDIT_ITEM_SCHEMA, "maxItems": LIMIT_ITEMS, "uniqueItems": True},
        "assessed_rule_ids": {
            "type": "array", "items": {"type": "string", "enum": RULE_ID_ENUM}, "maxItems": LIMIT_ITEMS * 2, "uniqueItems": True
        },
    },
    "required": ["passes", "violations", "assessed_rule_ids"],
    "additionalProperties": False,
}

# ----- КОМПАКТНАЯ схема для ЛЛМ: только нарушения и перечень оценённых -----
#   {"viol":[{"r":"RULE","s":"major","o":"D3","w":"история болезни","e":"..."}], "assessed":["RULE", ...]}
COMPACT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "r": {"type": "string", "enum": RULE_ID_ENUM},                 # rule_id
        "s": {"type": "string", "enum": ["critical", "major", "minor"]},  # severity
        "o": {"type": "string", "enum": ORDER_ENUM},                    # order
        "w": {"type": "string", "enum": WHERE_ENUM},                    # where
        "e": {"type": "string", "minLength": 1, "maxLength": EVIDENCE_MAX},  # evidence
    },
    "required": ["r", "s", "o", "w", "e"],
    "additionalProperties": False,
}

COMPACT_AUDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "viol": {"type": "array", "items": COMPACT_ITEM_SCHEMA, "maxItems": LIMIT_ITEMS, "uniqueItems": True},
        "assessed": {
            "type": "array",
            "items": {"type": "string", "enum": RULE_ID_ENUM},
            "uniqueItems": True,
            "minItems": 1
        },
    },
    "required": ["viol", "assessed"],
    "additionalProperties": False,
}
