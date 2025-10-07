#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

from collections import Counter
from typing import Dict, Any

from .localize import localize_result


def _mk_pretty_text(data: dict) -> str:
    doc_hint = ", ".join(data.get("doc_profile_hint") or [])
    passes = data.get("passes") or []
    viols = data.get("violations") or []

    sev_counter = Counter([str(v.get("severity") or "").lower() for v in viols])
    parts = []
    parts.append("Итог проверки")
    if doc_hint:
        parts.append(f"Профиль документа: {doc_hint}")
    parts.append(f"Пройдено правил: {len(passes)}")
    parts.append(f"Нарушений: {len(viols)}")
    if viols:
        parts.append(
            "По тяжести: "
            + ", ".join(
                f"{k}: {sev_counter.get(k, 0)}" for k in ("критично", "существенно", "незначительно")
            )
        )
        parts.append("")
        parts.append("Список нарушений:")
        for v in viols:
            rid = v.get("rule_id", "")
            title = v.get("title", "")
            sev = v.get("severity", "")
            ev = (v.get("evidence") or "").strip()
            if len(ev) > 220:
                ev = ev[:217] + "..."
            parts.append(f"- [{sev}] {rid} — {title}")
            if ev:
                parts.append(f"  • Доказательство: {ev}")
    return "\n".join(parts).strip() + "\n"


def build_human_report(raw_result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Возвращает локализованный компактный отчёт + Markdown/plain текст.
    Структура:
    {
      summary: {passes, violations, by_severity},
      violations_compact: [{id,title,severity,evidence}],
      pretty_text: "..."
    }
    """
    data = localize_result(dict(raw_result))  # легкая копия словаря

    passes = data.get("passes") or []
    viols = data.get("violations") or []
    sev_counter = Counter([str(v.get("severity") or "").lower() for v in viols])
    assessed_ids = list(raw_result.get("assessed_rule_ids") or [])

    comp = [
        {
            "id": v.get("rule_id"),
            "title": v.get("title"),
            "severity": v.get("severity"),
            "evidence": v.get("evidence"),
        }
        for v in viols
    ]

    pretty = _mk_pretty_text(data)

    # соберём краткую мета-информацию о работе ЛЛМ (если есть)
    llm = raw_result.get("llm_status") or {}
    llm_meta = None
    if llm:
        llm_meta = {
            "ok": bool(llm.get("ok")),
            "model": llm.get("model"),
            "duration_ms": llm.get("duration_ms"),
            "bytes": llm.get("bytes"),
            "chunks": llm.get("chunks"),
            # дополнительные диагностические поля
            "mode": llm.get("mode"),
        }
        if llm.get("error"):
            llm_meta["error"] = llm.get("error")
        if llm.get("parse_errors"):
            llm_meta["parse_errors"] = llm.get("parse_errors")
        if llm.get("assessed_empty_chunks"):
            llm_meta["assessed_empty_chunks"] = llm.get("assessed_empty_chunks")
        if llm.get("assessed_weak_chunks"):
            llm_meta["assessed_weak_chunks"] = llm.get("assessed_weak_chunks")
        if llm.get("supports"):
            llm_meta["supports"] = llm.get("supports")
        if llm.get("rules_per_chunk"):
            llm_meta["rules_per_chunk"] = llm.get("rules_per_chunk")
        samples = llm.get("raw_samples") or []
        if samples:
            llm_meta["samples"] = samples
            # добавим в текст фрагменты «ответа LLM»
            pretty += "\nОтвет LLM (фрагменты):\n"
            for s in samples:
                if not s:
                    continue
                s_clean = s.strip()
                if not s_clean:
                    continue
                if len(s_clean) > 400:
                    s_clean = s_clean[:397] + "..."
                pretty += f"  {s_clean}\n"

        # если видим явные признаки не-JSON, подскажем что включить грамматику
        try:
            first = (samples[0] if samples else "").lstrip()
            if first and not first.startswith("{") and not llm.get("error"):
                hint = "Модель вернула текст, а не JSON. Рекомендуется запустить сервис с OLLAMA_USE_GRAMMAR=1 (или выбрать режим grammar) и NUM_PREDICT умеренным (например, 384–512)."
                llm_meta["hint"] = hint
                pretty += "\nПодсказка: " + hint + "\n"
        except Exception:
            pass

    return {
        "summary": {
            "passes": len(passes),
            "violations": len(viols),
            "by_severity": {
                "критично": sev_counter.get("критично", 0),
                "существенно": sev_counter.get("существенно", 0),
                "незначительно": sev_counter.get("незначительно", 0),
            },
        },
        "violations_compact": comp,
        "pretty_text": pretty,
        "assessed_rule_ids": assessed_ids,
        "meta": {"llm": llm_meta} if llm_meta is not None else {"llm": None},
    }
