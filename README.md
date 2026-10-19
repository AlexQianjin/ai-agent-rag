# ai-agent-rag

ai-agent-rag is a monorepo for question answering with retrieval-augmented generation (RAG). Users can upload PDF, TXT, Markdown, and Docs files.

## Tech stack

The list below is the planned stack. The repository currently contains the workspace, a Vite React app styled with Tailwind CSS, and a FastAPI service connected to PostgreSQL through SQLAlchemy and Alembic. Routing, authentication, and the AI agent are not implemented yet. There are no application tables yet.

### Frontend

- React
- React hooks
- React Router
- Tailwind CSS
- shadcn/ui
- React Hook Form
- Zod
- Zustand
- React Query
- TanStack Table
- Better Auth
- Vite
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

### AI agent

- LangGraph
- mem0
- Qdrant
- A local LLM that follows the OpenAI API

## Project structure

```
.
├── apps/
│   ├── frontend/          # Vite + React + TypeScript + Tailwind CSS
│   │   ├── Dockerfile     # Multi-stage build; nginx serves the static app
│   │   └── nginx.conf
│   └── backend/           # FastAPI app managed with uv
│       ├── Dockerfile
│       ├── .dockerignore
│       ├── alembic.ini
│       └── alembic/       # Baseline migration only; no app tables yet
├── docker-compose.yml
├── .env.example
├── .dockerignore          # Used by the frontend image build
├── package.json           # Root pnpm scripts
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
├── LICENSE
└── README.md
```

`apps/backend` is a Python project (`pyproject.toml`, `uv.lock`, `.python-version`). Its `package.json` only defines a `dev` script so the root workspace can start it.

## Getting started

### Prerequisites

- Node.js 22 or newer
- pnpm 10 (the version is pinned in the root `package.json`)
- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Install

From the repository root:

```bash
pnpm install
pnpm --filter backend exec uv sync
```

`uv sync` creates `apps/backend/.venv` and installs the backend dependencies. From `apps/backend`, the same step is `uv sync`.

### Configure the database

The API reads `DATABASE_URL` from the environment, then from a `.env` file at the repository root. Copy the example and set it to the Supabase session pooler URI. That URI uses port 5432 and must require SSL:

```bash
cp .env.example .env
```

```text
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/postgres?sslmode=require
```

A `postgresql://` URL is rewritten to `postgresql+psycopg://` so SQLAlchemy uses the psycopg 3 driver. `.env` stays on your machine. Commit `.env.example` only.

Apply the baseline migration from `apps/backend`:

```bash
uv run alembic upgrade head
```

The migration creates Alembic's version table and no application tables.

`GET /health` does not touch the database. `GET /health/db` runs `SELECT 1` and returns:

```json
{"status": "ok"}
```

### Run the frontend

```bash
pnpm dev
```

`pnpm dev` and `pnpm dev:frontend` both start the Vite dev server at http://localhost:5173.

### Run the backend

From the repository root:

```bash
pnpm dev:backend
```

That starts uvicorn with reload on http://127.0.0.1:8000. From `apps/backend`:

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
pnpm build     # production build of the frontend
pnpm lint      # lint the frontend with oxlint
pnpm preview   # serve the frontend production build
```

`pnpm --filter frontend build` is the same as `pnpm build`.

## Deployment

Docker Compose runs the frontend and the API. The frontend image builds the Vite app, then nginx serves the static files and falls back to `index.html` for client-side routes. The backend image installs the locked dependencies with uv and runs FastAPI under uvicorn on `0.0.0.0:8000`.

Compose does not start PostgreSQL. The API connects to the database in `DATABASE_URL`, usually the Supabase session pooler. Compose reads that variable from the shell, or from the `.env` file next to `docker-compose.yml` when the shell does not set it. An exported value overrides the file. Qdrant is still not included.

| File | Purpose |
| --- | --- |
| `apps/frontend/Dockerfile` | Multi-stage frontend image. The build context is the repository root so the pnpm lockfile is available. |
| `apps/frontend/nginx.conf` | nginx site config copied into the frontend image. |
| `apps/backend/Dockerfile` | FastAPI image built with uv 0.13.1. |
| `apps/backend/.dockerignore` | Files left out of the backend build context. |
| `.dockerignore` | Files left out of the frontend build context. |
| `docker-compose.yml` | Builds and runs both services. |

### Prerequisites

Docker Engine with the Compose plugin.

### Build and run

From the repository root:

```bash
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up
```

- Frontend: http://localhost:8080 (container port 80)
- Backend: http://localhost:8000/health
- Database check: http://localhost:8000/health/db

Both health endpoints return `{"status":"ok"}`.

Stop the stack with `docker compose down`.
