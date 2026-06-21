# Context Handoff

This document details the current state of the Agent Memory System v2.0 to pass context to the next developer session.

---

## 🚀 Current State
- **FastAPI Backend & MCP Server**: Exposes REST endpoints (`/remember`, `/recall`, `/answer`) and MCP tools (`remember`, `recall`) protected by namespace bearer tokens.
- **Local CPU Scoring**: Automatically generates `all-MiniLM-L6-v2` embeddings and ranks query results using a custom BM25 retriever and `BAAI/bge-reranker-v2-m3` cross-encoder.
- **Operations & Rollups**: Supported by `run_jobs.py` which computes Day/Month/Year summaries, runs TTL sweeps, and safely backs up SQLite databases.
- **Docker Containers**: Setup via `Dockerfile` and `docker-compose.yml` for automated cloud deployments.
- **Automated Verification**: Complete 9-case test suite passing successfully under `pytest`.

---

## 📂 Project Structure
```
c:\Users\Lalli_KK74\Videos\Judgement Frontend Project\Software developer files\KK Multi Agent - Multi API\
├── app.py              # FastAPI endpoints and lifespans
├── database.py         # SQLite connection settings & schemas
├── retrieval.py        # Embeddings, BM25, and CrossEncoder rerank
├── llm.py              # Provider fallback logic
├── conflict.py         # Contradiction triggers & supersedes
├── cognitive.py        # Daily / Monthly summaries
├── security.py         # Isolation verification, delimiters & TTL sweep
├── mcp_server.py       # FastMCP tools
├── run_jobs.py         # Backup, rollup and metrics runner
├── index.html          # Visual browser control dashboard
├── Dockerfile          # Alpine build pre-caching weights
├── docker-compose.yml  # Volume persistence compose
├── pyproject.toml      # Dependency manifests
├── .gitignore          # Exclusion definitions
├── README.md           # Quickstart instructions
└── tests/
    └── test_memory_system.py  # 9 Pytest cases
```

---

## ➡️ Next Steps
1. **Docker Deployment**: Run `docker compose up -d --build` to deploy in production.
2. **Operations Cron**: Set up a nightly cron runner executing `python run_jobs.py --agent-id default-agent --date YYYY-MM-DD --sweep --backup-dir backups` to compile temporal rollups and backup the active database.
3. **Litestream backup**: Integrate continuous replication to S3-compatible cloud storage if needed.
