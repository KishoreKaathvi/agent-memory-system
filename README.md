# Agent Memory System

Self-hosted memory layer for AI agents: append-only SQLite storage, hybrid retrieval (vector + BM25 + rerank), conflict detection, temporal rollups, REST + MCP interfaces, and a browser dashboard.

## Status

**MVP / Work in Progress**

Core storage, retrieval, conflict handling, REST/MCP APIs, Docker packaging, and an 11-case pytest suite are present in code (`app.py`, `database.py`, `retrieval.py`, `conflict.py`, `llm.py`, `mcp_server.py`, `tests/test_memory_system.py`). Session docs claim full completion and production readiness (`session.md`); that overstates operational maturity (dashboard job endpoints missing, Docker multi-key wiring incomplete, continuous backup and monitoring from the build plan not implemented). Treat as a usable local/MVP stack, not production-hardened.

**Versions:** package `0.1.0` in `pyproject.toml`; FastAPI app metadata may label API `2.0.0` separately in `app.py`.

**Remote:** `https://github.com/KishoreKaathvi/agent-memory-system.git`

## Tech Stack

Pulled from manifests and imports (not assumed):

| Layer | Choice | Source |
|---|---|---|
| Language | Python >= 3.10 | `pyproject.toml` |
| Package / lock | `uv` + `pyproject.toml` / `uv.lock` | repo root |
| API | FastAPI, Uvicorn, Pydantic v2 | `pyproject.toml`, `app.py` |
| Storage | SQLite (WAL, busy timeout, `BEGIN IMMEDIATE`) | `database.py` |
| Embeddings / rerank | `sentence-transformers` (`all-MiniLM-L6-v2`), CrossEncoder `BAAI/bge-reranker-v2-m3` | `retrieval.py`, `implemented.md` |
| LLM HTTP client | `httpx` multi-provider OpenAI-compatible chain | `llm.py` |
| MCP | FastMCP via `mcp` package | `mcp_server.py`, `pyproject.toml` |
| Frontend | Single-page `index.html` dashboard | `index.html`, served by `GET /` |
| Ops | Docker multi-stage build, `docker-compose.yml`, `run_jobs.py` | Dockerfile, compose, CLI |
| Tests | pytest, pytest-asyncio | `pyproject.toml` dev group, `tests/` |

## Implemented Features (✅)

| Feature | Evidence |
|---|---|
| SQLite schema, WAL, multi-tenant namespaces (API key SHA-256) | `database.py` |
| Append-only memory events, rollups, TOC, conflict tables | `database.py`, `implemented.md` |
| Hybrid retrieval: embeddings + pure-Python BM25 + RRF + BGE rerank | `retrieval.py` |
| Semantic chunk helper + confidence scoring | `retrieval.py` |
| Conflict detection (cosine ~0.85) + LLM resolve supersede/retain/annotate | `conflict.py` |
| Multi-provider LLM client with fallback chain | `llm.py` (OpenRouter default; optional NVIDIA, Gemini, GitHub, Mistral, Cohere, Together, SambaNova when env keys set) |
| Request-level `llm_provider` / `llm_model` lock | `llm.py`, `app.py` `/answer` |
| Day / month / year cognitive rollups with token budget chunking | `cognitive.py` |
| Namespace checks, injection scan, `<retrieved_context>` wrap, TTL sweep helpers | `security.py` |
| REST: `POST /remember`, `POST /recall`, `POST /answer`, `GET /health`, `GET /` | `app.py` |
| MCP tools `remember` + `recall` over stdio | `mcp_server.py` |
| Browser dashboard: store / search / ask + LLM lock in `localStorage` | `index.html` |
| Ops CLI: backup, rollups, TTL sweep, metrics | `run_jobs.py` |
| Docker image + compose with DB volume | `Dockerfile`, `docker-compose.yml` |
| Automated tests (11 cases) | `tests/test_memory_system.py` |

## In-Progress / Partial Features ()

| Feature | What exists | What is missing |
|---|---|---|
| Dashboard Operations (Backup / TTL Sweep) | UI calls `POST /api/backup` and `POST /api/sweep` (`index.html`) | Those routes do **not** exist in `app.py` (only `/remember`, `/recall`, `/answer`, `/health`, `/`). On failure the UI can still print simulated success. Real ops: `run_jobs.py` |
| Docker multi-provider secrets | Compose passes `OPENROUTER_API_KEY`, `MEMORY_SYSTEM_API_KEY`, `OPENROUTER_MODEL` | Other providers documented in `user-guide.md` / `llm.py` are not wired into `docker-compose.yml` |
| Env sample file | Docs describe env vars | No `.env.example` in repo |
| Production monitoring (build plan Part 13) | Basic Python logging + `run_jobs.py --metrics` | Structured alerts for rollup health, provider exhaustion, retrieval drift, WAL growth not implemented |
| MCP surface | `remember`, `recall` | No MCP `answer` tool (REST has `/answer`) |
| Scheduled ops | Handoff recommends cron | No in-repo scheduler or compose sidecar |
| freeLLM.net | Referenced heavily in docs as discovery index | Not a live registry in code; providers hard-coded in `llm.py` |

## Planned but Not Started (❌)

From `pending.md` and `agent-memory-system-build-plan.md` where matching production code was not found:

| Item | Source |
|---|---|
| Graph-augmented retrieval (entity relations) | `pending.md` - deferred |
| Litestream continuous SQLite -> S3 replication | `pending.md` / build plan |
| OAuth 2.1 PKCE for browser clients | `pending.md` |
| PostgreSQL migration for horizontal scale | `pending.md` - deferred |
| Extra free LLM providers (Groq, Cerebras, SiliconFlow) | `pending.md` |
| Full observability stack (alerts, golden-set regression schedule) | build plan Part 13 |

## Architecture Overview

Summarized from `decisions.md` and `agent-memory-system-build-plan.md` (not copied verbatim):

```
Clients (browser dashboard, REST agents, MCP tools)
        |
        v
   FastAPI app  --  MCP server (stdio)
        |
        +-- conflict check + remember
        +-- hybrid recall + rerank
        +-- LLM answer synthesis
        |
        v
   SQLite (WAL)  -  namespaces, events, rollups, conflicts
        |
   Local CPU models (embed + rerank) + external free-tier LLMs
```

Design choices documented in-repo:

1. **SQLite + WAL** for zero hosted DB cost; migrate only if concurrency forces it (`decisions.md`).
2. **Hybrid Vector + BM25 + RRF + local rerank** without paid vector DBs (`decisions.md`).
3. **Free multi-provider LLM fallback** for conflict/rollup/answer paths (`llm.py`, `decisions.md`).
4. **Similarity-gated conflict LLM**; ambiguous cases default toward `annotate` (`conflict.py`, `decisions.md`).
5. **Delimiter-wrapped retrieved context** against stored prompt injection (`security.py`).
6. **Server-side API keys only**; clients may lock provider/model, not credentials (`decisions.md`, `index.html`).

Two memory classes: **library** (stable knowledge) vs **episodic** (decisions, events, preferences). Cognitive stack: raw segments -> day -> month -> year rollups with TOC.

## Setup / Installation

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

Optional keys and model names are described in `user-guide.md`. Dependencies come only from `pyproject.toml` / `uv.lock`.

## Usage

### Run API + dashboard

```bash
uv run uvicorn app:app --port 8000 --reload
```

- Dashboard: http://localhost:8000
- Auth: `Authorization: Bearer <MEMORY_SYSTEM_API_KEY>`

### REST

See `user-guide.md` for curl examples of:

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

## Notes / Discrepancies

| Claim in docs | Reality in code | Prefer |
|---|---|---|
| "Completed & Test-Verified" / production ready (`session.md`) | Core features + tests exist; ops gaps remain (see Partial) | Code over optimistic session notes |
| Dashboard "Safe Backup DB" / "Sweep Expired TTL" (`user-guide.md`) | UI only; no matching FastAPI routes; false success paths possible | `run_jobs.py` for real backup/sweep |
| Eight providers in Docker | Compose exposes OpenRouter + system key only | `docker-compose.yml` |
| Monitoring & continuous backup (Litestream) | Planned in `pending.md` / build plan | Not implemented |
| freeLLM.net as live registry | Documentation reference only | Hard-coded providers in `llm.py` |
| Factual golden corpus Recall@3 >= 80% | Evaluation logic exists in tests | Not a scheduled production metric job |
| Path references in older docs | Some docs still point at a previous Windows path under "Judgement Frontend Project" (`handoff.md`, `user-guide.md`) | This repo root is `agent-memory-system` |
| `implemented.md` vs partial dashboard ops | Lists dashboard as full visual controller | Dashboard exists; ops buttons incomplete |

**Project intent docs:**

| File | Role |
|---|---|
| `agent-memory-system-build-plan.md` | Full intended design (v2.0) |
| `implemented.md` | Author checklist of built modules |
| `pending.md` | Deferred roadmap |
| `decisions.md` | ADR-style design choices |
| `handoff.md` / `session.md` | Session state (optimistic on "done") |
| `user-guide.md` | Setup and API usage |

**Rule of thumb:** trust the Python modules for what works; trust `agent-memory-system-build-plan.md` + `pending.md` for what was intended next.
