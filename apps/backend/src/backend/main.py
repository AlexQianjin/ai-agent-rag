"""FastAPI application entrypoint."""

from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.db import get_db

app = FastAPI(title="ai-agent-rag", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for local development and deployment probes."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Check that the configured PostgreSQL database accepts a query."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


def main() -> None:
    """Run the API with uvicorn in reload mode for local development."""
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
