# Context Handoff

This document details the current state of the Agent Memory System v2.0 to pass context to the next developer session.

---

## 🚀 Current State
- **FastAPI Backend & MCP Server**: Exposes REST endpoints (`/remember`, `/recall`, `/answer`) and MCP tools (`remember`, `recall`) protected by namespace bearer tokens. Now includes dynamic request-level routing parameters (`llm_provider` and `llm_model`).
- **Multi-Provider LLM Integration**: Directly routes API calls to 8 providers (OpenRouter, NVIDIA NIM, Google Gemini AI Studio, GitHub Models, Mistral AI, Cohere, Together AI, SambaNova) depending on request-level parameters or dashboard locks, using their respective environment variables.
- **Visual Control Dashboard**: Premium single-page dashboard featuring the "LLM Model Control" sidebar component that dynamically queries and locks provider/model targets on all subsequent question-answering and conflict-checking triggers.
- **Local CPU Scoring**: Automatically generates `all-MiniLM-L6-v2` embeddings and ranks query results using a custom BM25 retriever and `BAAI/bge-reranker-v2-m3` cross-encoder.
- **Operations & Rollups**: Supported by `run_jobs.py` which computes Day/Month/Year summaries, runs TTL sweeps, and safely backs up SQLite databases.
- **Docker Containers**: Setup via `Dockerfile` and `docker-compose.yml` for automated cloud deployments.
- **Automated Verification**: Complete 11-case test suite passing successfully under `pytest` verifying multi-provider selector parameter resolution.

---

## 📂 Project Structure
```
c:\Users\Lalli_KK74\Videos\Judgement Frontend Project\Software developer files\KK Multi Agent - Multi API\
├── app.py              # FastAPI endpoints, lifespans, and custom route handlers
├── database.py         # SQLite connection settings & schemas
├── retrieval.py        # Embeddings, BM25, and CrossEncoder rerank
├── llm.py              # Dynamic multi-provider dynamic fallback client routing
├── conflict.py         # Contradiction triggers & supersedes
├── cognitive.py        # Daily / Monthly summaries
├── security.py         # Isolation verification, delimiters & TTL sweep
├── mcp_server.py       # FastMCP tools
├── run_jobs.py         # Backup, rollup and metrics runner
├── index.html          # Visual browser control dashboard with LLM selection lock widget
├── Dockerfile          # Alpine build pre-caching weights
├── docker-compose.yml  # Volume persistence compose
├── pyproject.toml      # Dependency manifests
├── .gitignore          # Exclusion definitions
├── README.md           # Quickstart instructions
└── tests/
    └── test_memory_system.py  # 11 Pytest cases
```

---

## ➡️ Next Steps
1. **Multi-Provider Secrets Management**: Confirm that all environment keys (`NVIDIA_API_KEY`, `GEMINI_API_KEY`, etc.) are securely bound inside production container configurations or environment variables.
2. **Operations Cron**: Set up a nightly cron runner executing `python run_jobs.py --agent-id default-agent --date YYYY-MM-DD --sweep --backup-dir backups` to compile temporal rollups and backup the active database.
3. **Litestream backup**: Integrate continuous replication to S3-compatible cloud storage if needed.
