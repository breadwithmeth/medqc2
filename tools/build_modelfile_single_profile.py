#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, re
from pathlib import Path
from textwrap import dedent
import yaml

def oneline(s: str) -> str:
    s = (s or "").strip()
    return re.sub(r"\s+", " ", s)

def filter_rules(rules: list[dict], include: list[str]) -> list[dict]:
    inc = {p.upper() for p in include}
    out = []
    for r in rules or []:
        rid = str(r.get("id", "")).strip()
        if not rid: continue
        pref = (rid.split("-", 1)[0] if "-" in rid else rid).upper()
        if pref in inc: out.append(r)
    return out

def build_system_instructions(rules: list[dict]) -> str:
    TOTAL = len(rules)
    header = dedent(f"""\
    Ты — строгий аудитор медицинских документов Республики Казахстан.
    Работай по стационарному профилю (GEN+STAC) и правилам ниже.

    ВАЖНО:
    • Если требуемая сущность/дата/время/подпись не найдены — это FAIL (по умолчанию FAIL при отсутствии).
    • Сначала сформируй ТАЙМЛАЙН (timeline) — извлеки ключевые даты/время/факты и дай короткие ДОСЛОВНЫЕ цитаты.
    • 3-и сутки = 72 часа от момента поступления. Рабочее время заведующего (если явно не указано иное): будни 09:00–18:00.
    • Для ограничений по времени (например, «30 минут») сравни реальные метки времени.
    • НЕ придумывай данные; evidence — только короткие цитаты из документа.
    • Оцени КАЖДОЕ правило из списка ниже. Сумма PASS+FAIL ДОЛЖНА быть ровно {TOTAL}.
      Если по правилу нет явной цитаты — помести его в violations с evidence: "не найдено в документе".

    Формат ответа — СТРОГО JSON:
    {{
      "doc_profile_hint": ["STAC","GEN"],
      "timeline": {{
        "admission_dt": "...",
        "er_exam_dt": "...",
        "ward_exam_dt": "...",
        "head_primary": {{ "dt": "...", "is_work_hours": true|false, "quote": "..." }},
        "diag_justify_dt": "...",
        "preop_epicrisis": {{
          "has_indications": true|false, "has_complaints": true|false, "has_anamnesis_vitae": true|false,
          "has_anamnesis_morbi": true|false, "has_somatic_status": true|false, "quote": "..."
        }},
        "anesth_protocol_dt": "...",
        "op_protocol": {{
          "dt": "...", "ab_prophylaxis": true|false, "pre_diag": true|false, "post_diag": true|false,
          "op_name": true|false, "blood_loss_ml": "..."|"", "complications": true|false,
          "biopsy_taken": true|false, "anesthesiologist": true|false, "nurse": true|false, "surgeon": true|false, "quote": "..."
        }},
        "cpr": {{ "present": true|false, "duration_min": 0, "every_5_min_checks": true|false, "quote": "..." }},
        "notes_heavy_every_3h": {{ "required": true|false, "ok": true|false, "quote": "..." }},
        "clinical_diag_day3": true|false,
        "stage_epicrisis_day10": true|false,
        "consilium_day3_ge3docs": true|false,
        "transfusion_pre": {{
          "cbc_dt": true|false, "abg_dt": true|false, "pulse": true|false, "bp": true|false,
          "spo2": true|false, "hb": true|false, "quote": "..."
        }},
        "prescription": {{ "diet": true|false, "regimen": true|false, "quote": "..." }}
      }},
      "passes": [{{ "rule_id":"...", "title":"...", "severity":"...", "required":true, "order":"...", "where":"...", "evidence":"..." }}],
      "violations": [{{ "rule_id":"...", "title":"...", "severity":"...", "required":true, "order":"...", "where":"...", "evidence":"..." }}],
      "assessed_rule_ids": ["..."]  // РОВНО {TOTAL} штук
    }}
    Никаких пояснений вне JSON.
    """).strip()

    lines = []
    for r in rules:
        rid   = oneline(r.get("id", ""))
        title = oneline(r.get("title", ""))
        sev   = oneline(r.get("severity", ""))
        req   = "обяз" if bool(r.get("required")) else "необяз"
        order = oneline(r.get("order", ""))
        where = oneline(r.get("where", ""))
        q     = oneline(r.get("llm_question", "") or r.get("question", ""))
        lines.append(f"- {rid} | {title} | {sev} | {req} | {order} | {where} | check: {q}")

    tail = dedent(f"""\
    Алгоритм:
    1) Сформируй timeline (с дословными цитатами).
    2) Пройди по всем {TOTAL} правилам: каждое правило положи либо в passes, либо в violations (нельзя пропускать).
    3) Если чего-то нет в документе — правило в violations с evidence "не найдено в документе" или короткой цитатой.
    4) Заполни assessed_rule_ids всеми {TOTAL} идентификаторами правил в порядке оценки.
    5) Верни ТОЛЬКО JSON по схеме.
    """).strip()

    return f"{header}\n\nПРАВИЛА:\n" + "\n".join(lines) + "\n\n" + tail

def build_modelfile(base: str, num_ctx: int, system: str) -> str:
    system_escaped = system.replace('"""', '\\"""')
    return dedent(f"""\
    FROM {base}
    PARAMETER num_ctx {num_ctx}
    SYSTEM \"\"\"{system_escaped}\"\"\"
    """).lstrip()

def main():
    ap = argparse.ArgumentParser(description="Собрать Modelfile (prefix include).")
    ap.add_argument("out_modelfile")
    ap.add_argument("rules_yaml")
    ap.add_argument("--base", default="llama3.1:8b-instruct-q5_1")
    ap.add_argument("--name", default="medaudit:stac-strict")
    ap.add_argument("--num_ctx", type=int, default=3072)
    ap.add_argument("--include", nargs="+", default=["GEN","STAC"])
    args = ap.parse_args()

    data = yaml.safe_load(Path(args.rules_yaml).read_text(encoding="utf-8"))
    rules_all = data.get("rules", [])
    chosen = filter_rules(rules_all, args.include)
    if not chosen:
        raise SystemExit(f"Нет правил по префиксам {args.include}")

    system = build_system_instructions(chosen)
    out_path = Path(args.out_modelfile)
    out_path.write_text(build_modelfile(args.base, args.num_ctx, system), encoding="utf-8")
    print(f"OK: Modelfile -> {out_path}")
    print(f"Создать модель:\n  ollama create {args.name} -f {out_path}")

if __name__ == "__main__":
    main()
