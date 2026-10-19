"""Importing the agent must not open Postgres."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND = Path(__file__).resolve().parents[1]


def test_imports_do_not_require_a_database_url() -> None:
    env = os.environ.copy()
    env["DATABASE_URL"] = ""
    env["PYTHONPATH"] = os.pathsep.join([str(BACKEND / "src"), str(BACKEND), env.get("PYTHONPATH", "")])
    script = (
        "import backend.agent, backend.db, backend.vector_store, backend.embeddings, "
        "evals.answer, evals.run"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_opening_a_session_still_requires_a_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    import backend.db as db
    from backend.config import get_settings

    previous_engine = db._engine
    previous_factory = db._session_factory
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    db._engine = None
    db._session_factory = None
    try:
        with pytest.raises(ValidationError):
            db.SessionLocal()
    finally:
        db._engine = previous_engine
        db._session_factory = previous_factory
        get_settings.cache_clear()
