import numpy as np
import math
import re
from sentence_transformers import SentenceTransformer, CrossEncoder
from database import get_db

# Lazy loaded embedding and reranker models to prevent slowing down application imports
_embedder = None
_reranker = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedder

def get_reranker():
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder('BAAI/bge-reranker-v2-m3')
    return _reranker

def compute_confidence(memory_type: str, source: str, explicit: bool) -> float:
    """
    Compute a confidence score between 0.0 and 1.0 for a memory.
    explicit = True  -> user/agent directly stated this as fact
    explicit = False -> this was inferred/summarized by an LLM
    """
    base = 1.0 if explicit else 0.7
    if memory_type in ("fact", "decision", "commitment"):
        return base
    if memory_type in ("learning", "observation"):
        return base * 0.9
    return base

def tokenize(text: str) -> list[str]:
    """Helper to tokenize text for BM25 search."""
    return re.findall(r'\w+', text.lower())

class SimpleBM25:
    """A lightweight BM25 ranking model for keyword retrieval."""
    def __init__(self, corpus: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avg_doc_len = sum(len(tokenize(doc)) for doc in corpus) / (self.corpus_size or 1)
        self.doc_lengths = [len(tokenize(doc)) for doc in corpus]
        self.doc_freqs = {}
        self.term_freqs = []
        
        for doc in corpus:
            tokens = tokenize(doc)
            tfs = {}
            for token in tokens:
                tfs[token] = tfs.get(token, 0) + 1
            self.term_freqs.append(tfs)
            for token in set(tokens):
                self.doc_freqs[token] = self.doc_freqs.get(token, 0) + 1
                
    def score(self, query: str, doc_idx: int) -> float:
        query_tokens = tokenize(query)
        score = 0.0
        tfs = self.term_freqs[doc_idx]
        doc_len = self.doc_lengths[doc_idx]
        
        for token in query_tokens:
            if token not in self.doc_freqs:
                continue
            df = self.doc_freqs[token]
            idf = math.log((self.corpus_size - df + 0.5) / (df + 0.5) + 1.0)
            tf = tfs.get(token, 0)
            num = tf * (self.k1 + 1)
            den = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avg_doc_len)
            score += idf * num / den
        return score

def semantic_chunk(text: str, target_chunk_size: int = 500) -> list[str]:
    """Split long documents at paragraph boundaries preserving semantic coherence."""
    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) > target_chunk_size and current:
            chunks.append(current.strip())
            current = para
        else:
            current = (current + "\n\n" + para).strip()
    if current.strip():
        chunks.append(current.strip())
    return chunks

async def hybrid_recall(query: str, agent_id: str, db_path: str = None, top_k: int = 40) -> list[dict]:
    """
    Perform hybrid search (Vector + BM25) on active memory events.
    Utilizes Reciprocal Rank Fusion (RRF) to merge rankings.
    """
    conn = get_db(db_path)
    try:
        # Retrieve active (non-superseded) memory events for the agent
        rows = conn.execute(
            """SELECT id, memory_class, memory_type, content, source, confidence, embedding, created_at 
               FROM memory_events 
               WHERE agent_id = ? AND superseded_by IS NULL""",
            (agent_id,)
        ).fetchall()
        
        if not rows:
            return []
        
        corpus = [row["content"] for row in rows]
        
        # 1. Vector Search
        embedder = get_embedder()
        query_vec = embedder.encode(query)
        
        vector_scores = []
        for i, row in enumerate(rows):
            if row["embedding"] is None:
                # Fallback if no embedding stored yet
                vector_scores.append((i, 0.0))
                continue
            emb = np.frombuffer(row["embedding"], dtype=np.float32)
            similarity = np.dot(query_vec, emb) / (np.linalg.norm(query_vec) * np.linalg.norm(emb) + 1e-10)
            vector_scores.append((i, float(similarity)))
        
        # Sort indices by vector similarity descending
        vector_ranked = sorted(vector_scores, key=lambda x: x[1], reverse=True)
        
        # 2. BM25 Keyword Search
        bm25 = SimpleBM25(corpus)
        bm25_scores = []
        for i in range(len(rows)):
            bm25_scores.append((i, bm25.score(query, i)))
            
        bm25_ranked = sorted(bm25_scores, key=lambda x: x[1], reverse=True)
        
        # 3. Reciprocal Rank Fusion (RRF)
        # RRF Score = sum( 1 / (60 + rank) )
        rrf_scores = {}
        for rank, (idx, _) in enumerate(vector_ranked):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (60.0 + (rank + 1))
            
        for rank, (idx, _) in enumerate(bm25_ranked):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + 1.0 / (60.0 + (rank + 1))
            
        # Rank by RRF score descending
        rrf_ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
        
        # Build candidates list
        candidates = []
        for idx, rrf_score in rrf_ranked[:top_k]:
            row = rows[idx]
            candidates.append({
                "id": row["id"],
                "memory_class": row["memory_class"],
                "memory_type": row["memory_type"],
                "content": row["content"],
                "source": row["source"],
                "confidence": row["confidence"],
                "created_at": row["created_at"],
                "rrf_score": rrf_score
            })
            
        return candidates
    finally:
        conn.close()

async def hybrid_recall_with_rerank(query: str, agent_id: str, db_path: str = None, 
                                     retrieve_k: int = 40, final_k: int = 8) -> list[dict]:
    """
    Retrieves candidates via hybrid recall, then applies local CrossEncoder reranking.
    """
    candidates = await hybrid_recall(query, agent_id, db_path, top_k=retrieve_k)
    if not candidates:
        return []
        
    reranker = get_reranker()
    pairs = [(query, c["content"]) for c in candidates]
    
    # Predict relevance scores
    scores = reranker.predict(pairs)
    
    # Associate scores with candidates
    for i, score in enumerate(scores):
        candidates[i]["rerank_score"] = float(score)
        
    # Sort by rerank score descending
    ranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
    return ranked[:final_k]
