#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_modelfile_single_profile.py
---------------------------------
Собирает ОДИН Modelfile для Ollama с зашитыми в SYSTEM правилами,
отфильтрованными по префиксам (например, GEN, STAC).

Пример использования:
  python3 tools/build_modelfile_single_profile.py Modelfile.stac.strict rules_all.yaml \
    --base llama3.1:8b-instruct-q5_1 \
    --name medaudit:stac-strict \
    --num_ctx 3072 \
    --include GEN STAC

После генерации Modelfile создайте модель:
  ollama create medaudit:stac-strict -f Modelfile.stac.strict
"""

from __future__ import annotations
import argparse
import re
from pathlib import Path
from textwrap import dedent

try:
    import yaml  # pip install pyyaml
except Exception as e:
    raise SystemExit("Требуется PyYAML: pip install pyyaml") from e


def oneline(s: str) -> str:
    """Сжать многострочный текст в одну строку с одиночными пробелами."""
    s = (s or "").strip()
    return re.sub(r"\s+", " ", s)


def filter_rules(rules: list[dict], include: list[str]) -> list[dict]:
    """
    Оставить только правила, чей префикс (часть до первого '-') входит в include.
    Пример: id="STAC-27-..." -> префикс "STAC".
    """
    inc = {p.upper() for p in include}
    out: list[dict] = []
    for r in rules or []:
        rid = str(r.get("id", "")).strip()
        if not rid:
            continue
        pref = (rid.split("-", 1)[0] if "-" in rid else rid).upper()
        if pref in inc:
            out.append(r)
    return out


def build_system_instructions(rules: list[dict]) -> str:
    """
    Строгий SYSTEM:
    - Сначала TАЙМЛАЙН (ключевые даты/время/факты с цитатами),
    - 100% покрытие правил (каждое правило попадает либо в passes, либо в violations),
    - FAIL по умолчанию при отсутствии данных,
    - assessed_rule_ids для контроля количества.
    """
    TOTAL = len(rules)

    header = dedent(f"""\
    Ты — строгий аудитор медицинских документов Республики Казахстан.
    Работай по стационарному профилю (GEN+STAC) и правилам ниже.

    ВАЖНО:
    • Если требуемая сущность/дата/время/подпись не найдены — это FAIL (по умолчанию FAIL при отсутствии).
    • Сначала сформируй ТАЙМЛАЙН (timeline) — извлеки ключевые даты/время/факты и дай короткие ДОСЛОВНЫЕ цитаты.
    • 3-и сутки = 72 часа от момента поступления. Рабочее время заведующего (если явно не указано иное): будни 09:00–18:00.
    • Для ограничений во времени (например, «30 минут») сравни реальные метки времени.
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

    # Компактный список правил одной строкой — часть SYSTEM
    lines: list[str] = []
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
    3) Если чего-то нет в документе — правило идёт в violations с evidence "не найдено в документе" или короткой цитатой.
    4) Заполни assessed_rule_ids всеми {TOTAL} идентификаторами правил в порядке оценки.
    5) Верни ТОЛЬКО JSON по схеме.
    """).strip()

    return f"{header}\n\nПРАВИЛА:\n" + "\n".join(lines) + "\n\n" + tail


def build_modelfile(base: str, num_ctx: int, system: str) -> str:
    """
    Формирует текст Modelfile: FROM + PARAMETER num_ctx + SYSTEM \"\"\"...\"\"\".
    Экранируем тройные кавычки, чтобы не сломать Modelfile.
    """
    system_escaped = system.replace('"""', '\\"""')
    return dedent(f"""\
    FROM {base}
    PARAMETER num_ctx {num_ctx}
    SYSTEM \"\"\"{system_escaped}\"\"\"
    """).lstrip()


def main():
    ap = argparse.ArgumentParser(description="Собрать ОДИН Modelfile для выбранного профиля (prefix include).")
    ap.add_argument("out_modelfile", help="Путь для Modelfile (например, Modelfile.stac.strict)")
    ap.add_argument("rules_yaml", help="YAML с полным набором правил (корневой ключ 'rules')")
    ap.add_argument("--base", default="llama3.1:8b-instruct-q5_1", help="Базовая квантованная модель Ollama")
    ap.add_argument("--name", default="medaudit:stac-strict", help="Имя модели для 'ollama create'")
    ap.add_argument("--num_ctx", type=int, default=3072, help="Контекст модели (num_ctx)")
    ap.add_argument("--include", nargs="+", default=["GEN", "STAC"], help="Список префиксов правил для включения")
    args = ap.parse_args()

    rules_path = Path(args.rules_yaml)
    if not rules_path.exists():
        raise SystemExit(f"Не найден файл правил: {rules_path}")

    try:
        data = yaml.safe_load(rules_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"Не удалось прочитать YAML {rules_path}: {e}") from e

    if not isinstance(data, dict) or "rules" not in data:
        raise SystemExit("В YAML ожидается корневой ключ 'rules' со списком правил.")

    rules_all = data["rules"]
    if not isinstance(rules_all, list) or not rules_all:
        raise SystemExit("Список 'rules' пуст или имеет неверный формат.")

    chosen = filter_rules(rules_all, args.include)
    if not chosen:
        raise SystemExit(f"По префиксам {args.include} правил не найдено.")

    system = build_system_instructions(chosen)
    modelfile_text = build_modelfile(args.base, args.num_ctx, system)

    out_path = Path(args.out_modelfile)
    out_path.write_text(modelfile_text, encoding="utf-8")
    print(f"OK: Modelfile записан -> {out_path}")
    print(f"Создать модель:\n  ollama create {args.name} -f {out_path}")


if __name__ == "__main__":
    main()
