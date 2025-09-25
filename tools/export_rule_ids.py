#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations
import argparse, json
from pathlib import Path
import yaml

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rules_yaml")
    ap.add_argument("--include", nargs="+", default=["GEN","STAC"])
    ap.add_argument("--out", default="app/expected_rules_stac.json")
    args = ap.parse_args()

    data = yaml.safe_load(Path(args.rules_yaml).read_text(encoding="utf-8"))
    rules = data.get("rules", [])
    inc = {p.upper() for p in args.include}
    out_ids = []
    for r in rules:
        rid = str(r.get("id","")).strip()
        if not rid: continue
        pref = (rid.split("-",1)[0] if "-" in rid else rid).upper()
        if pref in inc: out_ids.append(rid)

    Path(args.out).write_text(json.dumps({"expected_rule_ids": out_ids}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK: {len(out_ids)} правил -> {args.out}")

if __name__ == "__main__":
    main()
