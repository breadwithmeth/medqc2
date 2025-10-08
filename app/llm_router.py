# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from typing import Optional, Dict, Any

from .ollama_client import chat_ollama
from .openai_compat_client import chat_openai_compat


def chat_llm(
    system: str,
    question: str,
    text: str,
    model: Optional[str] = None,
    force_provider: Optional[str] = None,
    # общие параметры
    temperature: float = 0.0,
    num_predict: int = 512,
    num_ctx: int = 3072,
    keep_alive: str = "30m",
    use_json_format: bool = True,
    timeout: int = 180,
    connect_timeout: int = 8,
    retries: int = 1,
    # ollama-only
    grammar: Optional[str] = None,
    json_schema: Optional[dict] = None,
) -> str:
    """
    Единый вход для LLM. Провайдер выбирается по env LLM_PROVIDER=ollama|openai (или force_provider),
    по умолчанию: если есть OPENAI_API_KEY — используем openai-совместимый; иначе ollama.
    """
    provider = (force_provider or os.getenv("LLM_PROVIDER", "")).strip().lower()
    if not provider:
        # По умолчанию используем локальный/удалённый Ollama с запечённой моделью
        provider = "ollama"

    if provider == "openai":
        # OpenAI-совместимый путь: строгий json через response_format
        return chat_openai_compat(
            system=system,
            question=question,
            text=text,
            model=model or os.getenv("OPENAI_MODEL"),
            temperature=temperature,
            max_tokens=num_predict,
            top_p=float(os.getenv("OPENAI_TOP_P", "1.0")) if os.getenv("OPENAI_TOP_P") else None,
            use_json_format=use_json_format,
            timeout=timeout,
            connect_timeout=connect_timeout,
            retries=retries,
        )
    # Ollama по умолчанию (локальный/удалённый)
    return chat_ollama(
        system=system,
        question=question,
        text=text,
        model=model or os.getenv("STAC_MODEL"),
        temperature=temperature,
        num_predict=num_predict,
        num_ctx=num_ctx,
        keep_alive=keep_alive,
        use_json_format=use_json_format,
        timeout=timeout,
        connect_timeout=connect_timeout,
        retries=retries,
        grammar=grammar,
        json_schema=json_schema,
    )
