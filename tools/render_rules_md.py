#!/usr/bin/env python3
"""
Mini-render: convert YAML rules to a concise Markdown cheat sheet for auditors.
- Input: rules/*.yaml (file path arg)
- Output: prints Markdown to stdout, or write to file via --out
"""
import argparse
import sys
from pathlib import Path
import yaml

SEVERITY_EMOJI = {
    "critical": "🛑",
    "major": "⚠️",
    "minor": "ℹ️",
}


def load_yaml(path: Path):
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def section_meta(meta: dict) -> str:
    if not meta:
        return ""
    out = []
    out.append("## Легенда")
    sev = meta.get("legend", {}).get("severity", {})
    if sev:
        items = [f"- {SEVERITY_EMOJI.get(k, '')} {k}: {v}" for k, v in sev.items()]
        out.extend(items)
    gl = meta.get("glossary")
    if gl:
        out.append("\n## Глоссарий")
        for item in gl:
            out.append(f"- {item}")
    return "\n".join(out) + ("\n\n" if out else "")


def render_rule(r: dict) -> str:
    sev = r.get("severity", "").lower()
    badge = SEVERITY_EMOJI.get(sev, "")
    rid = r.get("id", "")
    title = r.get("title", "")
    where = r.get("where", "")
    order = r.get("order", "")
    required = r.get("required", False)
    req = "Обязательное" if required else "Опционально"
    notes = r.get("notes")
    llm_q = r.get("llm_question")
    lines = []
    lines.append(f"### {badge} {rid} — {title}")
    meta_line = ", ".join(x for x in [req, order, where] if x)
    if meta_line:
        lines.append(meta_line)
    if notes:
        lines.append(f"- Примечание: {notes}")
    if llm_q:
        lines.append(f"- Проверка: {llm_q}")
    return "\n".join(lines)


def render(md_data: dict) -> str:
    parts = []
    parts.append(f"# Памятка аудитору: правила ({md_data.get('name','llm_core')})\n")
    parts.append(section_meta(md_data.get("meta")))
    rules = md_data.get("rules", [])
    for r in rules:
        parts.append(render_rule(r))
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("yaml", type=str, help="Путь к rules YAML")
    p.add_argument("--out", type=str, help="Путь для записи Markdown (опционально)")
    args = p.parse_args()

    path = Path(args.yaml)
    if not path.exists():
        print(f"Файл не найден: {path}", file=sys.stderr)
        sys.exit(1)

    data = load_yaml(path)
    md = render(data)

    if args.out:
        out_path = Path(args.out)
        out_path.write_text(md, encoding='utf-8')
        print(f"Готово: {out_path}")
    else:
        sys.stdout.write(md)


if __name__ == "__main__":
    main()
