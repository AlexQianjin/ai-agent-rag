# ai-agent-rag

ai-agent-rag is a monorepo for question answering with retrieval-augmented generation (RAG). Users can upload PDF, TXT, Markdown, and Docs files.

## Tech stack

The list below is the planned stack. The repository currently contains the workspace, a Vite React app, a Hono service that hosts Better Auth, and a FastAPI service that stores accounts, converted documents, and chat threads in PostgreSQL. Converted Markdown is chunked, embedded with BGE-M3 through Ollama, and stored in Qdrant beside a BM25 sparse vector. A LangGraph agent answers from those passages with Grok, through the xAI API. mem0 is not connected yet. The graph has a recall step that returns nothing until it is.

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
- Docling
- Better Auth
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL
- uv

### AI agent

- LangGraph
- mem0 (the recall step is reserved for it)
- Qdrant
- Ollama
- BGE-M3
- Grok, through the xAI API (`https://api.x.ai/v1`)

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

Hono listens on http://127.0.0.1:3001. During local development the Vite server proxies `/api/auth` to that process, and `BETTER_AUTH_URL` stays `http://localhost:5173` so the session cookie matches the page. Vite also proxies `/me`, `/health`, and `/api/documents` to FastAPI, so the browser keeps that cookie on one origin. The documents page itself stays at `/documents`. The cookie is tied to the hostname: open the app as `localhost`, because `127.0.0.1` does not share it.

Sign-up, sign-in, sign-out, and session live at `/api/auth/*`. User administration uses the Better Auth admin plugin on the same service: list, get, create, update, and delete. Those actions require an admin. A signed-in user without that role is rejected. FastAPI does not write the user tables. `GET /me` on the API forwards the session cookie to Better Auth and returns the current user.

Create the first admin after the auth schema exists:

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='a-long-password' pnpm --filter auth create-admin
```

### Run the frontend

```bash
pnpm dev
```

`pnpm dev` and `pnpm dev:frontend` both start the Vite dev server at http://localhost:5173. Sign up at `/signup`, log in at `/login`, and log out at `/logout`. `/users` lists accounts for an admin. `/documents` uploads a file and shows the Markdown preview. `/chat` is the conversation list and the streamed answer.

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

### Convert a document

Signed-in users upload a PDF, DOCX, TXT, or Markdown file to `POST /documents`. The file has to be 20 MB or smaller. Anything else is rejected with a short error. TXT and Markdown are read as UTF-8. PDF and DOCX go through [Docling](https://github.com/docling-project/docling). Conversion runs in the background. `GET /documents` lists the caller's files, and `GET /documents/{id}` returns the status and, when it is `ready`, the Markdown. Status moves from `pending` to `processing`, then `ready` or `failed`.

The row lives in the `document` table (`owner_user_id`, filename, mime type, conversion status, indexing status, Markdown, timestamps). An optional `conversation_id` records which chat uploaded the file, so that chat can show indexing progress. Alembic creates the table. When a document is ready, the API calls `schedule_indexing`. That chunks the Markdown, embeds the chunks, and upserts a dense vector and a BM25 sparse vector into Qdrant. `index_status` moves through `pending`, `indexing`, and then `indexed` or `failed`. `DELETE /documents/{id}` removes the row and that document's vectors.

The first PDF conversion on a machine without cached weights downloads Docling's layout and table models. To do that ahead of time:

```bash
DOCLING_ARTIFACTS_PATH=/path/to/models uv run --directory apps/backend python -m backend.download_models
```

Leave `DOCLING_ARTIFACTS_PATH` set when you start the API. OCR is off, so a scanned PDF will not pick up text; a PDF that already has a text layer will. The Docker image installs the CPU build of PyTorch from the official CPU index, which leaves out the CUDA libraries, and downloads the layout and table models while the image builds.

### Search your documents

`POST /search` takes a JSON body, `{"query": "...", "top_k": 5}`, and returns the nearest chunks for the signed-in user. It embeds the query with BGE-M3, runs a BM25 query over the same chunks, and fuses the two rankings with reciprocal rank fusion. It does not call an answering LLM. Another user's chunks are filtered out of both searches. `top_k` defaults to 5 and cannot be higher than 20.

BM25 lives in Qdrant, not in Postgres and not in an in-process index. The collection has a sparse vector named `bm25` with the IDF modifier, and the Qdrant server turns chunk text into that vector with its `Qdrant/bm25` model. The same model scores the query. The owner filter is part of both searches, so the fusion step never sees another user's passages, and the sparse index scales with the collection instead of loading every chunk into the API process. Postgres full-text ranking is not BM25, and a second copy of the text would drift from the vectors. Qdrant 1.15 cannot add a sparse vector to a collection that was created with only a dense vector, so the first hybrid startup replaces that collection and reindexes from the stored Markdown. Set `HYBRID_BACKFILL=1`, or run:

```bash
uv run --directory apps/backend python -m backend.reindex
```

Compose turns the backfill on. A local API leaves it off unless you set the variable.

Chunking reads the stored Markdown. A heading stays with the text under it. Each chunk aims for about 480 tokens, repeats a short tail from the previous window, and stays under 1024 tokens, inside BGE-M3's 8192-token limit. Docling's HybridChunker wants a Docling document and a Hugging Face tokenizer; the file we keep is Markdown, so the chunker works on that text.

Embeddings go to Ollama's native `POST /api/embed`. That endpoint accepts a list of strings and returns the vectors in the same order. The OpenAI-compatible `/v1/embeddings` route is only a shim, and its batching has lagged behind. The client sends batches, times out, and retries failed requests. Configure it with:

```text
EMBEDDING_BASE_URL=http://127.0.0.1:11434
EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
```

Those are the defaults, along with a 60 second timeout, batches of 16, and 3 attempts. [bge-m3](https://ollama.com/library/bge-m3) produces 1024-dimensional dense vectors. Qdrant stores them with cosine distance in the `documents` collection, which the API creates if it is missing. Each point's payload is the document id, owner user id, chunk index, text, and headings.

```text
QDRANT_URL=http://127.0.0.1:6333
QDRANT_COLLECTION=documents
```

For local development, run Ollama and pull the model once:

```bash
ollama pull bge-m3
```

Qdrant can be the Compose service, or any server at `QDRANT_URL`. The documents page shows the indexing status and a search box for signed-in users.

### Chat

`/chat` lists the signed-in user's conversations. Creating one, opening one, renaming it, and deleting it are all limited to the owner. Deleting a conversation removes its messages. A document uploaded from that chat stays in the library, and the link on the document is cleared.

Search from a chat covers every indexed document the user owns, not only the files attached to that thread. A question often depends on something uploaded earlier, on the documents page or in another chat. The chat still records which files were uploaded there so it can show `pending`, `indexing`, or `indexed` while Docling and the embedding step run.

`POST /conversations/{id}/messages` accepts `{"content": "..."}` and answers with server-sent events. The browser uses `fetch` so the session cookie is sent. The events are:

```text
event: thinking
data: {"status": "Thinking…"}

event: searching
data: {"status": "Searching documents…"}

event: retrieved
data: {"status": "Found 2 passages", "sources": [{"document_name": "notes.txt", "chunk_index": 0, "text": "...", "headings": [], "score": 0.03, "document_id": "..."}]}

event: token
data: {"delta": "The apple "}

event: done
data: {"message_id": "...", "content": "...", "citations": []}

event: error
data: {"message": "..."}
```

The user message is stored before the stream starts. The assistant message, including those citations, is stored when the run finishes. The answer is asked to cite passages as `[1]`, `[2]`, and each source names the document and the chunk. nginx proxies `/api/conversations` with `proxy_buffering off` so those tokens are not held back. The Vite dev proxy leaves the stream open as well.

The model is [Grok](https://docs.x.ai/overview) on the OpenAI-compatible endpoint `https://api.x.ai/v1`. The default model id is `grok-4.7`. Configure it with:

```text
XAI_API_KEY=
LLM_BASE_URL=https://api.x.ai/v1
LLM_MODEL=grok-4.7
```

Leave the key out of git. The placeholder in `.env.example` is commented out. Without a key the stream returns an error event and does not call xAI.

The graph is three steps: recall, retrieve, answer. Recall is where mem0 will plug in. It returns no memories today, and the answer step already reads that list when it is present.

### Other scripts

```bash
pnpm build     # production build of the frontend
pnpm lint      # lint the frontend with oxlint
pnpm preview   # serve the frontend production build
```

`pnpm --filter frontend build` is the same as `pnpm build`.

## Deployment

Docker Compose runs the frontend, the auth service, the API, Qdrant, and, with the `ollama` profile, Ollama. The frontend image builds the Vite app, then nginx serves the static files, falls back to `index.html` for client-side routes, and proxies `/api/auth/` to the auth container. It also proxies `/me` and `/health` to the API, so the browser session stays on port 8080. The auth image installs the workspace package and applies the Better Auth schema on startup. The backend image installs the locked dependencies with uv, including the CPU build of PyTorch, downloads the Docling layout models, and runs FastAPI under uvicorn on `0.0.0.0:8000`. nginx also proxies `/api/documents`, `/api/search`, and `/api/conversations` to the API, accepts uploads up to 20 MB, and turns proxy buffering off for conversation streams.

Compose does not start PostgreSQL. Both services use `DATABASE_URL`, usually the Supabase session pooler. Compose reads that variable, and `BETTER_AUTH_SECRET`, from the shell or from the `.env` file next to `docker-compose.yml`. An exported value overrides the file. Inside Compose, the public auth origin is `http://localhost:8080` and FastAPI calls the auth service at `http://auth:3001`. Qdrant listens on port 6333. The `ollama` profile starts Ollama on port 11434 and a one-shot container pulls `bge-m3` into a persisted volume. The API waits for that pull when the profile is enabled. CPU is the default. GPU support is optional: uncomment the NVIDIA `deploy` block on the `ollama` service if the machine has a GPU.

To use an Ollama that is already running on the host, leave the profile off and point the API at it:

```text
EMBEDDING_BASE_URL=http://host.docker.internal:11434
```

`host.docker.internal` is mapped on the backend service. Pull `bge-m3` on that host Ollama yourself. An exported `EMBEDDING_BASE_URL` or `QDRANT_URL` replaces the Compose default.

The API container receives `XAI_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL` from the shell or from `.env`. The defaults are `https://api.x.ai/v1` and `grok-4.7`. `HYBRID_BACKFILL` defaults to on inside Compose, so the first start rebuilds a dense-only Qdrant collection and reindexes stored Markdown in the background. Later starts leave documents that are already on the hybrid index alone.

| File | Purpose |
| --- | --- |
| `apps/frontend/Dockerfile` | Multi-stage frontend image. The build context is the repository root so the pnpm lockfile is available. |
| `apps/frontend/nginx.conf` | nginx site config copied into the frontend image. |
| `apps/auth/Dockerfile` | Hono and Better Auth image. The build context is the repository root. |
| `apps/backend/Dockerfile` | FastAPI image built with uv 0.13.1. |
| `apps/backend/.dockerignore` | Files left out of the backend build context. |
| `.dockerignore` | Files left out of the frontend build context. |
| `docker-compose.yml` | Builds and runs the frontend, auth service, API, and Qdrant. The `ollama` profile adds Ollama and the `bge-m3` pull. |

### Prerequisites

Docker Engine with the Compose plugin.

### Build and run

From the repository root:

```bash
docker compose --profile ollama build
docker compose --profile ollama run --rm backend alembic upgrade head
docker compose --profile ollama up
```

The first start downloads `bge-m3` before the API container is marked ready. Later starts reuse the `ollama_data` volume. Without the profile, Compose still starts Qdrant and the API uses `EMBEDDING_BASE_URL` if you set it.

The auth container applies its schema when it starts, so you do not run `pnpm migrate:auth` again for Compose.

- Frontend: http://localhost:8080 (container port 80)
- Auth health: http://localhost:3001/health
- Backend: http://localhost:8000/health
- Database check: http://localhost:8000/health/db
- Qdrant: http://localhost:6333
- Ollama, with the profile: http://localhost:11434

The health endpoints return `{"status":"ok"}`. Sign-in from the published frontend uses `/api/auth` on port 8080.

Stop the stack with `docker compose down`.
