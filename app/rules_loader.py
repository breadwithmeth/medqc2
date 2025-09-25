# app/rules_loader.py
import os
import yaml
from typing import List, Any
from .models import LLMRule

def _to_list(obj: Any) -> List[dict]:
    """
    Приводим результат safe_load к списку правил.
    Допускаем форматы:
      - [ {...}, {...} ]
      - { "rules": [ {...}, {...} ] }
      - { ... }  # одиночное правило
      - None
    """
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        if "rules" in obj and isinstance(obj["rules"], list):
            return obj["rules"]
        # считаем, что это одно правило в виде словаря
        return [obj]
    raise TypeError(f"Unsupported YAML top-level type: {type(obj)}")

def load_llm_rules(rules_dir: str) -> List[LLMRule]:
    rules: List[LLMRule] = []
    if not os.path.isdir(rules_dir):
        # нет каталога — вернём пустой список, чтобы приложение стартовало
        return rules

    for name in sorted(os.listdir(rules_dir)):
        if not name.lower().endswith((".yml", ".yaml")):
            continue
        path = os.path.join(rules_dir, name)
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)  # <-- ключевая правка: без |
        for item in _to_list(raw):
            rules.append(LLMRule(**item))
    return rules
