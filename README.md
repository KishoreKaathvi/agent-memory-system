# Agent Memory System v2.0
### Production-Grade, Self-Hosted, Multi-Provider, Zero-Cost Memory Infrastructure

A private, self-hosted memory layer designed to sit underneath AI agents (Claude, OpenRouter, NVIDIA NIM, etc.) that persists context across sessions and interfaces.

Features local vector embeddings and cross-encoder reranking ($0 hosted cost), database-enforced multi-tenant isolation, append-only immutable logs, semantic contradiction checks, and progressive temporal rollups.

---

## 🛠️ Technology Stack
- **Language**: Python 3.13
- **Web API**: FastAPI & Uvicorn
- **Protocol**: Model Context Protocol (MCP) via Python FastMCP
- **Database**: SQLite (configured for high concurrency: WAL mode, `PRAGMA synchronous=NORMAL`, `busy_timeout=5000`, `BEGIN IMMEDIATE` transactions)
- **Local Models**: 
  - Embeddings: `all-MiniLM-L6-v2` via `sentence-transformers` (runs on CPU)
  - Reranking: `BAAI/bge-reranker-v2-m3` via `sentence-transformers` (runs on CPU)
- **Rollups & Contradiction LLM**: OpenRouter free-tier Fallback Chain (defaulting to Llama-3.3-70b-instruct)

---

## 📂 Project Architecture

The system consists of the following core modules:
- [database.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/database.py): SQLite storage schemas, WAL setup, transaction locks, and namespace verification.
- [retrieval.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/retrieval.py): Lazy loading of local models, BM25 ranker, Reciprocal Rank Fusion (RRF) search, semantic chunker.
- [llm.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/llm.py): Robust OpenRouter fallback logic, parsing LLM decision tags.
- [conflict.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/conflict.py): Cosine similarity scans and automated supersede linkages on memory overrides.
- [cognitive.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/cognitive.py): Progressive temporal rollup compressor jobs (Day, Month, Year summaries) with database level unique constraints.
- [security.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/security.py): Tenant namespace isolation assertions, prompt wrappers for stored memory injections, instruction filters, and unverified data TTL sweeper.
- [mcp_server.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/mcp_server.py): FastMCP wrapper exposing standard tools `remember` and `recall`.
- [app.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/app.py): REST API exposing FastAPI routes.
- [run_jobs.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/run_jobs.py): Background job runner (backup database, TTL sweep, temporal rollups, metrics reporting).
- [tests/test_memory_system.py](file:///c:/Users/Lalli_KK74/Videos/Judgement%20Frontend%20Project/Software%20developer%20files/KK%20Multi%20Agent%20-%20Multi%20API/tests/test_memory_system.py): Automated test suite verifying the complete memory stack.

---

## ⚡ Setup & Quickstart

### 1. Requirements
Ensure Python 3.10+ is installed. We recommend the `uv` tool for package execution.

### 2. Configure Environment
Create a `.env` file at the root:
```ini
OPENROUTER_API_KEY=your_key_here
MEMORY_SYSTEM_API_KEY=mcp_localdev0123456789abcdef...
DATABASE_PATH=memory.db
```

### 3. Run Automated Tests
```bash
uv run pytest -v
```

### 4. Start the FastAPI REST Server
```bash
uv run uvicorn app:app --port 8000 --reload
```

---

## 📡 API Endpoints & MCP Tools

### REST Endpoints
All REST endpoints require the header `Authorization: Bearer <MEMORY_SYSTEM_API_KEY>`.

- **`POST /remember`**: Record a new factual event or static knowledge document.
  - Body: `{ "agent_id": "default-agent", "memory_class": "episodic", "memory_type": "decision", "content": "We decide to write tests." }`
- **`POST /recall`**: Perform hybrid search & reranking.
  - Body: `{ "agent_id": "default-agent", "query": "Which database are we using?", "top_k": 5 }`
- **`POST /answer`**: Retrieve facts and synthesize an answer protected by delimiter prompt delimiters.
  - Body: `{ "agent_id": "default-agent", "query": "What is our database choice?" }`
- **`GET /health`**: Retrieve database check status.

### MCP Server Integration
Run the MCP server locally over stdin/stdout:
```bash
uv run python mcp_server.py
```
This registers tools:
- `remember(agent_id, memory_class, memory_type, content, api_key, source)`
- `recall(agent_id, query, api_key, top_k)`

---

## ⚙️ Operations & CLI Management (`run_jobs.py`)

Run background jobs on schedules (e.g., cron or Windows Scheduler):

1. **Safely Backup Database** (uses SQLite native backup API):
   ```bash
   uv run python run_jobs.py --backup-dir backups
   ```
2. **Execute Temporal Rollups** (compressing day events for an agent):
   ```bash
   uv run python run_jobs.py --agent-id default-agent --date 2026-06-20
   ```
3. **Execute TTL Security Sweeps** (marking expired unverified logs):
   ```bash
   uv run python run_jobs.py --agent-id default-agent --sweep
   ```
4. **Display Database Metrics**:
   ```bash
   uv run python run_jobs.py --metrics
   ```

---

## 🐳 Production Deployment with Docker

To deploy the Agent Memory System for production users using Docker:

### 1. Build and Start Container
Ensure your environment variables are configured in a `.env` file, then run:
```bash
docker compose up -d --build
```
This builds a lightweight container utilizing `ghcr.io/astral-sh/uv` to fast-install packages, pre-caches Hugging Face model weights (`all-MiniLM-L6-v2` and `BAAI/bge-reranker-v2-m3`) to prevent startup latency, and exposes the REST API on port `8000`.

### 2. Data Persistence
The SQLite database file is stored in a persistent volume mount (`memory-data:/app/data/memory.db`) to ensure restarts do not delete your memories.

