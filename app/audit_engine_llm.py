from typing import List, Tuple
from .models import LLMRule, RuleResult
from .ollama_client import chat_ollama, chat_ollama_batch, parse_json, parse_batch_json

def run_llm_rules(text: str, rules: List[LLMRule]) -> Tuple[List[RuleResult], List[RuleResult]]:
    """Одноправильный режим (фолбэк)."""
    passes: List[RuleResult] = []
    violations: List[RuleResult] = []
    for r in rules:
        raw = chat_ollama(r.llm_system or "", r.llm_question, text)
        status, evidence = parse_json(raw)
        res = RuleResult(
            rule_id=r.id, title=r.title, severity=r.severity, order=r.order,
            where=r.where, required=r.required, status=status, evidence=evidence, notes=r.notes
        )
        (passes if status == "PASS" else violations).append(res)
    return passes, violations

def run_llm_rules_batched(text: str, rules: List[LLMRule]) -> Tuple[List[RuleResult], List[RuleResult]]:
    """Батч: все правила одним запросом. Если парсинг не удался — фолбэк на run_llm_rules()."""
    # соберём вход для батча
    items = [{"id": r.id, "title": r.title, "question": r.llm_question} for r in rules]
    raw = chat_ollama_batch("", items, text)
    mapping = parse_batch_json(raw)

    # если модель дала мусор — отступаем к одиночным запросам (редко, но бывает)
    if not mapping or len(mapping) < max(1, int(0.6 * len(rules))):
        return run_llm_rules(text, rules)

    passes: List[RuleResult] = []
    violations: List[RuleResult] = []
    for r in rules:
        status, evidence = mapping.get(r.id, ("FAIL", ""))  # если нет ответа — FAIL
        res = RuleResult(
            rule_id=r.id, title=r.title, severity=r.severity, order=r.order,
            where=r.where, required=r.required, status=status, evidence=evidence, notes=r.notes
        )
        (passes if status == "PASS" else violations).append(res)
    return passes, violations
