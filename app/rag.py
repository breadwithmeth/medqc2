# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Any
import yaml


_RULES_PATH = os.getenv("RULES_MAIN_FILE", str(Path("rules") / "rules_all.yaml"))

_rules_map: Dict[str, Dict[str, Any]] = {}
_meta: Dict[str, Any] = {}


def _load_rules_once():
    global _rules_map, _meta
    if _rules_map:
        return
    p = Path(_RULES_PATH)
    if not p.exists():
        _rules_map = {}
        _meta = {}
        return
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    _meta = data.get("meta", {}) or {}
    rules = data.get("rules", []) or []
    out: Dict[str, Dict[str, Any]] = {}
    for r in rules:
        rid = str(r.get("id", "")).strip()
        if not rid:
            continue
        out[rid] = r
    _rules_map = out


def _short(s: str, limit: int) -> str:
    s = (s or "").strip()
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)].rstrip() + "…"


def get_global_context(max_items: int = 6, max_chars: int = 600) -> str:
    """Возвращает компактный глобальный контекст из легенды/глоссария правил."""
    _load_rules_once()
    legend = (_meta.get("legend") or {}).get("severity") or {}
    glossary = _meta.get("glossary") or []
    parts: List[str] = []
    if legend:
        parts.append("Легенда по severity: " + "; ".join([f"{k}: {legend[k]}" for k in ("critical","major","minor") if k in legend]))
    if glossary:
        gl = "; ".join(glossary[:max_items])
        parts.append("Глоссарий: " + gl)
    txt = "\n".join(parts)
    return _short(txt, max_chars)


def get_rule_hints(rule_ids: List[str], per_rule_chars: int = 220, max_total_chars: int = 1200) -> str:
    """Возвращает компактные подсказки по правилам (notes/where/order/вопрос)."""
    _load_rules_once()
    lines: List[str] = []
    for rid in rule_ids:
        r = _rules_map.get(rid)
        if not r:
            continue
        title = r.get("title") or rid
        where = r.get("where") or ""
        order = r.get("order") or ""
        notes = r.get("notes") or ""
        question = r.get("llm_question") or ""
        hint = f"{rid} | {title}. Где: {where}. Этап: {order}. Подсказка: {_short(notes, per_rule_chars)}. Вопрос: {_short(question, 140)}"
        lines.append(hint)
        txt = "\n".join(lines)
        if len(txt) >= max_total_chars:
            break
    return "\n".join(lines)
