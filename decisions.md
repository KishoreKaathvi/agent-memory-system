# Architectural Decisions Log

This document records the major design choices and engineering rationale for the Agent Memory System v2.0.

---

## 💾 1. SQLite Storage &WAL Concurrency Configuration
- **Decision**: Use a local SQLite database file in WAL (Write-Ahead Logging) mode, rather than PostgreSQL or a cloud database.
- **Rationale**:
  - Achieves $0 hosting cost and avoids setting up heavy database server dependencies.
  - WAL mode allows concurrent reads to proceed without being blocked by writes.
  - Setting `busy_timeout=5000` tells SQLite to wait up to 5 seconds for write locks to clear instead of throwing errors immediately.
  - Utilizing `BEGIN IMMEDIATE` transactions forces write locks to be obtained at the start of transactions, preventing upgrades from read locks that cause deadlocks.

---

## 🔍 2. Hybrid Search (RRF) & Local CPU Model Scoring
- **Decision**: Implement Vector Similarity and a pure-Python BM25 ranker, merged via Reciprocal Rank Fusion (RRF), with local CPU Cross-Encoder reranking.
- **Rationale**:
  - Local CPU embeddings and rerankers maintain $0 cost constraints.
  - RRF is mathematically robust and merges semantic scores and keyword exact matches without requiring manual parameter weight tuning.
  - Initial retrieval retrieves `40` candidates (optimized for recall), which are then reranked using `BAAI/bge-reranker-v2-m3` down to a final count (e.g., `8`) optimized for precision.

---

## 🤖 3. OpenRouter Fallback Chain
- **Decision**: Structure an async provider client that iterates through a list of free-tier model endpoints (e.g. Llama 3.3 70B, Gemini 2.5 Flash, Llama 3 8B).
- **Rationale**:
  - Free-tier API keys can hit rate limits (HTTP 429) or timeouts. A fallback chain prevents API failures from blocking core rollup and conflict resolution operations.

---

## ⚖️ 4. Cosine Similarity & LLM Contradiction Triggers
- **Decision**: Use a high semantic similarity threshold ($0.85$) to check incoming memories. Overlapping items trigger an LLM query that chooses one of: `supersede`, `retain`, or `annotate`.
- **Rationale**:
  - Restricts expensive LLM verification to entries that are highly similar semantically.
  - Defensively defaults unrecognized LLM responses to `annotate`, routing conflicting decisions to human review rather than silently overwriting data.

---

## 🛡️ 5. Stored Injection Prevention Delimiters
- **Decision**: Wrap retrieved memories inside strict HTML-style tags (`<retrieved_context>`) with instructions telling the LLM to treat retrieved entries as raw reference data, not system instructions.
- **Rationale**:
  - Defends against stored prompt injection vulnerabilities (OWASP ASI06 / SpAIware) where malicious payloads are stored in memory and execute during query recall.
