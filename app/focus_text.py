import re, os
AVG_CHARS_PER_TOKEN = float(os.getenv("AVG_CHARS_PER_TOKEN", "3.7"))

HEADINGS = [
    r"приемн\w* отделен", r"экстренн\w* госпитал",
    r"поступил", r"время поступ", r"дата поступ",
    r"осмотр врача отделен", r"первичн\w* осмотр", r"заведующ\w* отделен",
    r"обоснован\w* диагноз", r"клиническ\w* диагноз",
    r"предоперационн\w* эпикриз", r"послеоперационн\w* дневник", r"этапн\w* эпикриз",
    r"протокол операц", r"протокол анестез", r"АБ-?профилакти",
    r"кровопотер", r"осложнен", r"биопс",
    r"предтрансфузионн\w* эпикриз", r"КЩС", r"гемоглоб",
    r"сатурац|spo2", r"пульс", r"АД\b|артериальн\w* давлен",
    r"реанимац|СЛР|сердечно-?\s*легочн\w* реанимац",
    r"дневник", r"тяжел\w* состояни",
    r"консилиум", r"лист назначен", r"режим", r"лечебн\w* стол|диет",
]

def focus_text(text: str) -> str:
    num_ctx = int(os.getenv("OLLAMA_NUM_CTX", "3072"))
    out_budget = int(os.getenv("OUTPUT_BUDGET_TOKENS", "140"))
    system_budget = int(os.getenv("SYSTEM_BUDGET_TOKENS", "650"))
    max_input_tokens = max(512, num_ctx - out_budget - system_budget)
    max_chars = int(max_input_tokens * AVG_CHARS_PER_TOKEN)

    t = text
    blocks = [t[:5000]]  # больше шапки — тут обычно прием, первые осмотры и сроки
    low = t.lower()
    for rx in HEADINGS:
        m = re.search(rx, low)
        if not m: continue
        i = max(0, m.start() - 1400)
        j = min(len(t), m.start() + 3200)
        blocks.append(t[i:j])
    blocks.append(t[-3000:])  # хвост — эпикризы/рекомендации

    seen, out, total = set(), [], 0
    for b in blocks:
        key = (b[:128], len(b))
        if key in seen: continue
        seen.add(key)
        take = min(len(b), max(0, max_chars - total))
        if take <= 0: break
        out.append(b[:take]); total += take
    focused = "\n\n".join(out)
    return focused[:max_chars]
