"""Eval settings from the environment.

This does not construct the API `Settings` object. That object requires
`DATABASE_URL`, and the retrieval eval does not talk to Postgres.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalSettings:
    embedding_base_url: str
    embedding_model: str
    embedding_dimension: int
    embedding_timeout: float
    qdrant_url: str
    collection: str
    api_key: str
    llm_base_url: str
    llm_model: str
    llm_timeout: float
    judge_base_url: str
    judge_model: str

    @classmethod
    def from_env(cls) -> EvalSettings:
        llm_base_url = os.environ.get("LLM_BASE_URL", "https://api.x.ai/v1")
        llm_model = os.environ.get("LLM_MODEL", "grok-4.7")
        return cls(
            embedding_base_url=os.environ.get("EMBEDDING_BASE_URL", "http://127.0.0.1:11434"),
            embedding_model=os.environ.get("EMBEDDING_MODEL", "bge-m3"),
            embedding_dimension=int(os.environ.get("EMBEDDING_DIMENSION", "1024")),
            embedding_timeout=float(os.environ.get("EMBEDDING_TIMEOUT_SECONDS", "120")),
            qdrant_url=os.environ.get("QDRANT_URL", "http://127.0.0.1:6333"),
            collection=os.environ.get("EVAL_COLLECTION", "eval_golden"),
            api_key=os.environ.get("XAI_API_KEY", ""),
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_timeout=float(os.environ.get("LLM_TIMEOUT_SECONDS", "120")),
            judge_base_url=os.environ.get("JUDGE_BASE_URL", llm_base_url),
            judge_model=os.environ.get("JUDGE_MODEL", llm_model),
        )
