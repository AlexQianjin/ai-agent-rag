# ai-agent-rag
## Description
This is a mono repo project for the Q&A with RAG. It supports the user to upload PDFs, TXT, Markdown, and Docs files.

## Technical Stack

### Frontend
- React
- React hooks
- React Router
- Tailwind CSS
- Shadcn/ui
- React hook form
- Zod
- Zustand
- React Query
- Tanstack Table React
- Better Auth
- vitejs
- pnpm

### Backend
- Python
- FastAPI
- Better Auth
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- uv

### AI Agent
- LangGraph
- mem0
- Qdrant
- Local LLM with Openai API standard

The sections above describe the planned stack. This scaffold sets up the workspace, a Vite React app with Tailwind CSS, and a FastAPI service with a health check. Routing, auth, database, and AI agent code are not included yet.

## Project structure

```
.
├── apps/
│   ├── frontend/          # Vite + React + TypeScript + Tailwind CSS
│   └── backend/           # FastAPI app managed with uv
├── package.json           # Root pnpm scripts
├── pnpm-workspace.yaml    # pnpm workspace definition
├── pnpm-lock.yaml
├── LICENSE
└── README.md
```

`apps/backend` is a Python project (`pyproject.toml`, `uv.lock`, `.python-version`). A small `package.json` there only exposes a `dev` script so the root workspace can start it.

## Prerequisites

- Node.js 22 or newer
- pnpm 10 (`packageManager` is pinned in the root `package.json`)
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Setup

From the repository root:

```bash
pnpm install
pnpm --filter backend exec uv sync
```

`uv sync` creates `apps/backend/.venv` and installs FastAPI and uvicorn. You can also run it from the backend directory:

```bash
cd apps/backend
uv sync
```

## Run

### Frontend

```bash
pnpm dev
```

`pnpm dev` and `pnpm dev:frontend` both start the Vite dev server (http://localhost:5173).

### Backend

From the repository root:

```bash
pnpm dev:backend
```

That runs uvicorn with reload on http://127.0.0.1:8000. The same command from `apps/backend`:

```bash
uv run uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

`uv run backend` starts the same reload server through the project script.

`GET /health` returns:

```json
{"status": "ok"}
```

### Other scripts

```bash
pnpm build    # production build of the frontend
pnpm lint     # oxlint in the frontend
pnpm preview  # preview the frontend production build
```

`pnpm --filter frontend build` is equivalent to `pnpm build`.
