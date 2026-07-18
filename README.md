# Agent Memory System

Self-hosted memory layer for AI agents: append-only SQLite storage, hybrid retrieval (vector + BM25 + rerank), conflict detection, temporal rollups, REST + MCP interfaces, and a browser dashboard.

## Status

**MVP / Work in Progress**

Core storage, retrieval, conflict handling, REST/MCP APIs, and tests are present in code. Session docs claim full completion and production readiness; that overstates operational maturity (missing dashboard job endpoints, full multi-key Docker wiring, continuous backup, and the monitoring plan from the build spec). Treat as a usable local/MVP stack, not production-hardened.

**Version:** `0.1.0` in `pyproject.toml` (app metadata also labels API `2.0.0`).

## Tech stack

| Layer | Choice |
|--------|--------|
| Language | Python ≥ 3.10 |
| Package/runtime | `uv` + `pyproject.toml` / `uv.lock` |
| API | FastAPI, Uvicorn, Pydantic v2 |
| Storage | SQLite (WAL, `busy_timeout=5000`, `BEGIN IMMEDIATE` writes) |
| Embeddings / rerank | `sentence-transformers` (`all-MiniLM-L6-v2`), CrossEncoder `BAAI/bge-reranker-v2-m3` |
| LLM client | `httpx` multi-provider OpenAI-compatible chain |
| MCP | FastMCP (`mcp` package) |
| Ops | Docker / docker-compose, `run_jobs.py` CLI |
| Tests | pytest, pytest-asyncio |

## Implemented features

Features with working code (not only documentation):

- **SQLite schema & multi-tenant namespaces** (`database.py`) — `agent_namespaces` (API key SHA-256), append-only `memory_events`, day/month/year rollup tables, TOC, `memory_conflicts`
- **Hybrid retrieval** (`retrieval.py`) — local embeddings, pure-Python BM25, Reciprocal Rank Fusion, BGE cross-encoder rerank, semantic chunk helper, confidence scoring
- **Conflict detection & resolution** (`conflict.py`) — cosine similarity threshold `0.85` on fact/decision/preference/commitment; LLM chooses `supersede` / `retain` / `annotate`
- **Multi-provider LLM client** (`llm.py`) — OpenRouter default chain; optional NVIDIA NIM, Gemini, GitHub Models, Mistral, Cohere, Together, SambaNova when env keys are set; request-level `llm_provider` / `llm_model` lock
- **Temporal cognitive rollups** (`cognitive.py`) — idempotent day / month / year summaries with token-budget chunking
- **Security helpers** (`security.py`) — namespace access checks, injection pattern scan for `external_document` sources, `<retrieved_context>` answer wrapping, TTL flagging of low-confidence memories
- **REST API** (`app.py`) — `POST /remember`, `POST /recall`, `POST /answer`, `GET /health`, `GET /` (serves dashboard)
- **MCP tools** (`mcp_server.py`) — `remember`, `recall` over stdio
- **Browser dashboard** (`index.html`) — store / search / ask UI, auth token field, LLM provider/model lock in `localStorage`
- **Ops CLI** (`run_jobs.py`) — safe SQLite backup, rollups, TTL sweep, metrics printout
- **Docker packaging** — multi-step `Dockerfile` (model pre-cache), `docker-compose.yml` with volume for DB
- **Test suite** (`tests/test_memory_system.py`) — 11 cases covering append-only, isolation, conflicts, rollups, security prompts, API routes, provider selection (LLM calls mocked where needed)

## In-progress / partial features

- **Dashboard Operations (Backup / TTL Sweep)** — UI buttons call `POST /api/backup` and `POST /api/sweep`, but those routes **do not exist** in `app.py`. On failure the UI prints simulated success messages. Real backup/sweep only work via `run_jobs.py`.
- **Docker multi-provider secrets** — `docker-compose.yml` only passes `OPENROUTER_API_KEY`, `MEMORY_SYSTEM_API_KEY`, and `OPENROUTER_MODEL`. Other providers documented in `user-guide.md` / `llm.py` are not wired into compose.
- **No `.env.example`** — setup docs describe env vars; no sample env file is in the repo.
- **Production monitoring (build plan Part 13)** — structured event logging / alerts for rollup health, provider exhaustion, retrieval drift, WAL growth are specified in `agent-memory-system-build-plan.md` but not implemented beyond basic Python logging and CLI `--metrics`.
- **MCP surface** — plan and code expose `remember` + `recall` only; no MCP `answer` tool (REST has `/answer`).
- **Scheduled ops** — handoff recommends cron for rollups/backups; no in-repo scheduler or compose sidecar.

## Planned but not started

From `pending.md` and the build plan:

| Item | Source |
|------|--------|
| Graph-augmented retrieval (entity relations) | `pending.md` — deferred |
| Litestream continuous SQLite → S3 replication | `pending.md` / build plan Part 7.5 |
| OAuth 2.1 PKCE for browser clients | `pending.md` |
| PostgreSQL migration for horizontal scale | `pending.md` — deferred |
| Extra free LLM providers (Groq, Cerebras, SiliconFlow) | `pending.md` |
| Full observability stack (alerts on rollup miss, golden-set regression schedule, etc.) | build plan Part 13 |

## Architecture overview

Summarized from `decisions.md` and `agent-memory-system-build-plan.md` (not a full copy of either):

```
Clients (browser dashboard, REST agents, MCP tools)
        │
        ▼
   FastAPI app  ──  MCP server (stdio)
        │
        ├── conflict check + remember
        ├── hybrid recall + rerank
        └── LLM answer synthesis
        │
        ▼
   SQLite (WAL)  ·  namespaces · events · rollups · conflicts
        │
   Local CPU models (embed + rerank) + external free-tier LLMs
```

Design choices documented in-repo:

1. **SQLite + WAL** for zero hosted DB cost; migrate only if concurrency forces it.
2. **Hybrid Vector + BM25 + RRF + local rerank** for retrieval quality without paid vector DBs.
3. **Free multi-provider LLM fallback** (indexed via freeLLM.net notes in docs) for conflict/rollup/answer paths.
4. **Similarity-gated conflict LLM** to limit cost and default ambiguous cases to `annotate`.
5. **Delimiter-wrapped retrieved context** against stored prompt injection.
6. **Server-side API keys only**; clients may lock provider/model, not credentials.

Two memory classes: **library** (stable knowledge) vs **episodic** (decisions, events, preferences). Cognitive stack: raw segments → day → month → year rollups with TOC.

## Setup / installation

**Prerequisites:** Python 3.10+, [uv](https://github.com/astral-sh/uv).

```bash
# From repo root
uv sync

# Create a .env (not committed; no .env.example in repo). Minimum useful set:
# MEMORY_SYSTEM_API_KEY=...
# OPENROUTER_API_KEY=...
# OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free
# Optional: NVIDIA_API_KEY, GEMINI_API_KEY, GITHUB_TOKEN, MISTRAL_API_KEY,
#           COHERE_API_KEY, TOGETHER_API_KEY, SAMBANOVA_API_KEY, DATABASE_PATH
```

Optional keys and model names are described in `user-guide.md`.

## Usage

### Run API + dashboard

```bash
uv run uvicorn app:app --port 8000 --reload
```

- Dashboard: http://localhost:8000  
- Default local API key (if unset): see default in `app.py` / examples in `user-guide.md`  
- Auth: `Authorization: Bearer <MEMORY_SYSTEM_API_KEY>`

### REST (examples)

See `user-guide.md` for full curl examples of:

- `POST /remember`
- `POST /recall`
- `POST /answer`

### MCP server

```bash
uv run python mcp_server.py
```

Configure your MCP client to run this process; tools take `api_key` plus memory args.

### Ops jobs

```bash
uv run python run_jobs.py --backup-dir backups
uv run python run_jobs.py --agent-id default-agent --date 2026-06-21
uv run python run_jobs.py --agent-id default-agent --sweep
uv run python run_jobs.py --metrics
```

### Docker

```bash
# Ensure OPENROUTER_API_KEY and MEMORY_SYSTEM_API_KEY are in the environment / .env
docker compose up -d --build
```

### Tests

```bash
uv run pytest
```

## Project docs (source of truth for intent)

| File | Role |
|------|------|
| `agent-memory-system-build-plan.md` | Full intended design (v2.0) |
| `implemented.md` | Author checklist of built modules |
| `pending.md` | Deferred roadmap |
| `decisions.md` | ADR-style design choices |
| `handoff.md` / `session.md` | Session state (optimistic on “done”) |
| `user-guide.md` | Setup and API usage |

## Notes: docs vs code

| Claim in docs | Reality in code |
|---------------|-----------------|
| “Completed & Test-Verified” / production containers | Core features + tests exist; ops gaps remain (see Partial above). |
| Dashboard “Safe Backup DB” / “Sweep Expired TTL” | UI only; no matching FastAPI routes; false success on error paths. |
| Eight providers in Docker | Compose exposes OpenRouter + system key only. |
| Monitoring & continuous backup (Litestream) | Planned; not implemented. |
| freeLLM.net as live registry | Used as documentation reference only; providers are hard-coded in `llm.py`. |
| Factual golden corpus Recall@3 ≥ 80% | Evaluation logic exists in tests; not a scheduled production metric job. |
| Path references in older docs | Some docs still point at a previous Windows path under “Judgement Frontend Project”; this repo is `agent-memory-system`. |

**Rule of thumb:** trust the Python modules for what works; trust `agent-memory-system-build-plan.md` + `pending.md` for what was intended next.
