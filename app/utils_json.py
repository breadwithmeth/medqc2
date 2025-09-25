from __future__ import annotations
import json, re
from typing import Optional

def _extract_from_fence(s: str) -> Optional[str]:
    m = re.search(r"```json\s*(\{.*?\})\s*```", s, re.S|re.I)
    if m: return m.group(1).strip()
    m = re.search(r"```\s*(\{.*?\})\s*```", s, re.S)
    if m: return m.group(1).strip()
    return None

def _extract_balanced_object(s: str) -> Optional[str]:
    start = s.find("{")
    if start == -1: return None
    depth = 0; in_str = False; esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc: esc = False
            elif ch == "\\": esc = True
            elif ch == '"': in_str = False
        else:
            if ch == '"': in_str = True
            elif ch == "{": depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0: return s[start:i+1]
    return None

def _sanitize(s: str) -> str:
    return s.replace("\x00"," ").replace("\x0b"," ").replace("\x0c"," ").strip()

def coerce_json(s: str) -> dict:
    if not s: raise ValueError("empty response")
    try: return json.loads(s)
    except Exception: pass
    fenced = _extract_from_fence(s)
    if fenced:
        try: return json.loads(fenced)
        except Exception:
            inner = _extract_balanced_object(fenced)
            if inner: return json.loads(inner)
    balanced = _extract_balanced_object(s)
    if balanced:
        try: return json.loads(balanced)
        except Exception:
            return json.loads(_sanitize(balanced))
    return json.loads(_sanitize(s))
