# -*- coding: utf-8 -*-
from __future__ import annotations
import re
from datetime import datetime, timedelta
from typing import Optional

# Поддерживаем самые частые форматы дат/времени
DATE_RX = re.compile(
    r"\b(?P<d>\d{1,2})[.\-/](?P<m>\d{1,2})[.\-/](?P<y>\d{2,4})(?:[T\s]+(?P<h>\d{1,2}):(?P<min>\d{2})(?::(?P<s>\d{2}))?)?\b"
)

def parse_dt(s: str) -> Optional[datetime]:
    """
    Парсим строку в datetime (локальное «наивное» время).
    Поддержка DD.MM.YYYY HH:MM[:SS] и DD.MM.YY ...
    """
    if not s:
        return None
    m = DATE_RX.search(s)
    if not m:
        return None
    d = int(m.group("d")); mth = int(m.group("m")); y = int(m.group("y"))
    if y < 100:
        y += 2000 if y < 70 else 1900
    hh = int(m.group("h") or 0)
    mm = int(m.group("min") or 0)
    ss = int(m.group("s") or 0)
    try:
        return datetime(y, mth, d, hh, mm, ss)
    except ValueError:
        return None

def fmt(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else ""

def hours_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    if not a or not b:
        return None
    return abs((b - a).total_seconds()) / 3600.0

def days_between(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    h = hours_between(a, b)
    return None if h is None else (h / 24.0)

def within_minutes(a: Optional[datetime], b: Optional[datetime], minutes: int) -> Optional[bool]:
    h = hours_between(a, b)
    return None if h is None else (h * 60.0 <= minutes)

WORK_START = 9
WORK_END = 18

def is_work_hours(dt: Optional[datetime]) -> Optional[bool]:
    if not dt:
        return None
    wd = dt.weekday()  # 0=Mon..6=Sun
    return (wd < 5) and (WORK_START <= dt.hour < WORK_END)
