from __future__ import annotations

import hashlib

from agentic_scd.config import Settings, get_settings


def mock_completion(prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
    return f"[MOCK-LLM:{digest}] offline response for {len(prompt)} characters"


def completion(prompt: str, *, system: str | None = None, settings: Settings | None = None, **kwargs: object) -> str:
    settings = settings or get_settings()
    if settings.llm_is_mock:
        return mock_completion(prompt)
    try:
        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.completions.create(model=settings.groq_model, messages=messages, **kwargs)
        return response.choices[0].message.content or ""
    except Exception:
        return mock_completion(prompt)
