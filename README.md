# ai-agent-rag

ai-agent-rag is a monorepo for question answering with retrieval-augmented generation (RAG). Users can upload PDF, TXT, Markdown, and Docs files.

## Tech stack

The list below is the planned stack. The repository currently contains the workspace, a Vite React app, a Hono service that hosts Better Auth, and a FastAPI service connected to the same PostgreSQL database. The AI agent is not implemented yet, and there are no document tables yet.

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
│   ├── auth/              # Hono + Better Auth (email, session, user admin)
│   │   └── Dockerfile
│   └── backend/           # FastAPI app managed with uv
│       ├── Dockerfile
│       ├── .dockerignore
│       ├── alembic.ini
│       └── alembic/       # Application migrations; does not own auth tables
├── docker-compose.yml
├── .env.example
├── .dockerignore          # Used by the frontend image build
├── package.json           # Root pnpm scripts
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
├── LICENSE
└── README.md
```

`apps/backend` is a Python project (`pyproject.toml`, `uv.lock`, `.python-version`). Its `package.json` only defines a `dev` script so the root workspace can start it. `apps/auth` is a pnpm workspace package. It is a separate Node process because Better Auth is TypeScript. User accounts stay in that service. FastAPI checks the same session before it serves protected routes.

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

Apply both database steps. They share `DATABASE_URL` and touch different tables, so either one can run first.

From `apps/backend`:

```bash
uv run alembic upgrade head
```

Alembic creates its version table and, later, application tables. It does not create or drop Better Auth tables. Autogenerate ignores `user`, `session`, `account`, and `verification`.

From the repository root:

```bash
pnpm migrate:auth
```

That applies the Better Auth schema with the library's migrator: the `user`, `session`, `account`, and `verification` tables, including the admin role columns. Run it again after a Better Auth upgrade. It does not write Alembic revisions.

`GET /health` does not touch the database. `GET /health/db` runs `SELECT 1` and returns:

```json
{"status": "ok"}
```

### Run the auth service

```bash
pnpm dev:auth
```

Hono listens on http://127.0.0.1:3001. During local development the Vite server proxies `/api/auth` to that process, and `BETTER_AUTH_URL` stays `http://localhost:5173` so the session cookie matches the page. Vite also proxies `/me` and `/health` to FastAPI, so the browser keeps that cookie on one origin. The cookie is tied to the hostname: open the app as `localhost`, because `127.0.0.1` does not share it.

Sign-up, sign-in, sign-out, and session live at `/api/auth/*`. User administration uses the Better Auth admin plugin on the same service: list, get, create, update, and delete. Those actions require an admin. A signed-in user without that role is rejected. FastAPI does not write the user tables. `GET /me` on the API forwards the session cookie to Better Auth and returns the current user.

Create the first admin after the auth schema exists:

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-long-password' pnpm --filter auth create-admin
```

### Run the frontend

```bash
pnpm dev
```

`pnpm dev` and `pnpm dev:frontend` both start the Vite dev server at http://localhost:5173. Sign up at `/signup`, log in at `/login`, and log out at `/logout`. `/users` lists accounts for an admin.

### Run the backend

From the repository root:

```bash
pnpm dev:backend
```

That starts uvicorn with reload on http://localhost:8000. From `apps/backend`:

```bash
uv run uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

`uv run backend` starts the same reload server through the project script.

`GET /health` returns:

```json
{"status": "ok"}
```

`GET /me` returns the signed-in user, or `401` when the session cookie is missing. The dev server and the published frontend both expose that path on the page origin. `http://localhost:8000/me` is the same route on the API itself.

### Other scripts

```bash
pnpm build     # production build of the frontend
pnpm lint      # lint the frontend with oxlint
pnpm preview   # serve the frontend production build
```

`pnpm --filter frontend build` is the same as `pnpm build`.

## Deployment

Docker Compose runs the frontend, the auth service, and the API. The frontend image builds the Vite app, then nginx serves the static files, falls back to `index.html` for client-side routes, and proxies `/api/auth/` to the auth container. It also proxies `/me` and `/health` to the API, so the browser session stays on port 8080. The auth image installs the workspace package and applies the Better Auth schema on startup. The backend image installs the locked dependencies with uv and runs FastAPI under uvicorn on `0.0.0.0:8000`.

Compose does not start PostgreSQL. Both services use `DATABASE_URL`, usually the Supabase session pooler. Compose reads that variable, and `BETTER_AUTH_SECRET`, from the shell or from the `.env` file next to `docker-compose.yml`. An exported value overrides the file. Inside Compose, the public auth origin is `http://localhost:8080` and FastAPI calls the auth service at `http://auth:3001`. Qdrant is still not included.

| File | Purpose |
| --- | --- |
| `apps/frontend/Dockerfile` | Multi-stage frontend image. The build context is the repository root so the pnpm lockfile is available. |
| `apps/frontend/nginx.conf` | nginx site config copied into the frontend image. |
| `apps/auth/Dockerfile` | Hono and Better Auth image. The build context is the repository root. |
| `apps/backend/Dockerfile` | FastAPI image built with uv 0.13.1. |
| `apps/backend/.dockerignore` | Files left out of the backend build context. |
| `.dockerignore` | Files left out of the frontend build context. |
| `docker-compose.yml` | Builds and runs the frontend, auth service, and API. |

### Prerequisites

Docker Engine with the Compose plugin.

### Build and run

From the repository root:

```bash
docker compose build
docker compose run --rm backend alembic upgrade head
docker compose up
```

The auth container applies its schema when it starts, so you do not run `pnpm migrate:auth` again for Compose.

- Frontend: http://localhost:8080 (container port 80)
- Auth health: http://localhost:3001/health
- Backend: http://localhost:8000/health
- Database check: http://localhost:8000/health/db

The health endpoints return `{"status":"ok"}`. Sign-in from the published frontend uses `/api/auth` on port 8080.

Stop the stack with `docker compose down`.
