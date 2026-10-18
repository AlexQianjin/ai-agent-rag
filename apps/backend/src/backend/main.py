"""FastAPI application entrypoint."""

import uvicorn
from fastapi import FastAPI

app = FastAPI(title="ai-agent-rag", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check for local development and deployment probes."""
    return {"status": "ok"}


def main() -> None:
    """Run the API with uvicorn in reload mode for local development."""
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
