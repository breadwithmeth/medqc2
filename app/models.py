from pydantic import BaseModel, Field
from typing import List, Optional

class LLMRule(BaseModel):
    id: str
    title: str
    required: bool = True
    severity: str = "major"   # minor | major | critical
    order: str = ""           # ссылка/название стандарта
    where: str = ""           # где это ожидается
    notes: str = ""           # комментарий для отчёта
    llm_system: Optional[str] = None
    llm_question: str         # что именно спросить у модели
    expect_json: bool = True  # ожидаем JSON {"status": "...", "evidence": "..."}

class RuleResult(BaseModel):
    rule_id: str
    title: str
    severity: str
    order: str
    where: str
    required: bool
    status: str               # PASS | FAIL
    evidence: str = ""
    notes: str = ""

class AuditResponse(BaseModel):
    ok: bool
    doc_name: Optional[str] = None
    rules_total: int
    violations: List[RuleResult] = Field(default_factory=list)
    passes: List[RuleResult] = Field(default_factory=list)

class TextReq(BaseModel):
    text: str
