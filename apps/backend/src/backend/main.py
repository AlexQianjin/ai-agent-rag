"""FastAPI application entrypoint."""

from typing import Annotated

import uvicorn
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.auth import AuthenticatedUser, CurrentUser
from backend.config import get_settings
from backend.db import get_db

settings = get_settings()
app = FastAPI(title="ai-agent-rag", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for local development and deployment probes."""
    return {"status": "ok"}


@app.get("/health/db")
def health_db(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
    """Check that the configured PostgreSQL database accepts a query."""
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.get("/me")
def me(user: CurrentUser) -> AuthenticatedUser:
    """Return the Better Auth user for the current session."""
    return user


def main() -> None:
    """Run the API with uvicorn in reload mode for local development."""
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
