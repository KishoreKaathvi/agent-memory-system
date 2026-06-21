import numpy as np
import sqlite3
import logging
from database import remember, supersede, get_db
from retrieval import get_embedder, compute_confidence
from llm import generate_answer, parse_conflict_decision

conflict_logger = logging.getLogger("memory.conflict")

CONFLICT_SIMILARITY_THRESHOLD = 0.85

def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-10))

def detect_conflict(conn: sqlite3.Connection, new_content: str, agent_id: str, 
                    memory_type: str, new_vec: np.ndarray) -> dict:
    """
    Check if the incoming memory contradicts any existing non-superseded memory.
    Only checks types where contradictions are logically possible (fact, decision, preference, commitment).
    """
    conflict_types = {"fact", "decision", "preference", "commitment"}
    if memory_type not in conflict_types:
        return None

    # Fetch active candidates of the exact same memory type
    rows = conn.execute(
        """SELECT id, content, embedding FROM memory_events 
           WHERE agent_id = ? AND memory_type = ? AND superseded_by IS NULL""",
        (agent_id, memory_type)
    ).fetchall()

    for row in rows:
        if row["embedding"] is None:
            continue
        existing_vec = np.frombuffer(row["embedding"], dtype=np.float32)
        similarity = cosine_similarity(new_vec, existing_vec)
        
        if similarity > CONFLICT_SIMILARITY_THRESHOLD:
            conflict_logger.info(f"Potential conflict detected between existing ID {row['id']} and new memory. Similarity: {similarity:.4f}")
            return {
                "id": row["id"],
                "content": row["content"]
            }
            
    return None

async def remember_with_conflict_check(conn: sqlite3.Connection, agent_id: str, memory_class: str, 
                                       memory_type: str, content: str, source: str = None, 
                                       explicit: bool = True) -> int:
    """
    Store memory after performing semantic conflict checks. Resolves conflicts
    automatically (supersede/retain/annotate) via LLM validation.
    """
    # 1. Generate local vector embedding
    embedder = get_embedder()
    new_vec = embedder.encode(content)
    new_vec_bytes = new_vec.tobytes()

    # 2. Check for semantic conflict/overlap
    conflict = detect_conflict(conn, content, agent_id, memory_type, new_vec)

    if conflict is None:
        # No conflict: write directly
        confidence = compute_confidence(memory_type, source, explicit)
        return remember(conn, agent_id, memory_class, memory_type, content, source, confidence, new_vec_bytes)

    # 3. Found a conflict: call LLM to evaluate contradiction
    prompt = f"""Evaluate the potential contradiction between the EXISTING record and the NEW record.
Determine if the new statement contradicts, updates, or is simply complementary to the existing one.

Choose exactly one of the following words:
- supersede: The new record directly contradicts or updates the existing record, rendering the old one obsolete.
- retain: The new record and the existing record are both valid, complementary, or cover different aspects without contradiction.
- annotate: The statements are related, but it is ambiguous or highly contradictory in a way that requires human review.

Respond with ONLY one of the words: supersede, retain, or annotate. Do not explain your choice.

EXISTING Statement: "{conflict['content']}"
NEW Statement: "{content}"
"""

    try:
        judgment = await generate_answer(query=prompt)
        decision = parse_conflict_decision(judgment)
    except Exception as e:
        conflict_logger.warning(f"LLM call failed during conflict check: {e}. Defaulting to annotate.")
        decision = "annotate"

    conflict_logger.info(f"Conflict decision for existing ID {conflict['id']} vs new memory: {decision}")

    # 4. Insert new memory event
    confidence = compute_confidence(memory_type, source, explicit)
    new_id = remember(conn, agent_id, memory_class, memory_type, content, source, confidence, new_vec_bytes)

    # 5. Handle the decision path
    if decision == "supersede":
        supersede(conn, conflict["id"], new_id)
    elif decision == "annotate":
        flag_for_review(conn, conflict["id"], new_id, reason=f"Contradicting statement check failed. Similarity check found similarity. LLM selected annotate.")
        
    return new_id

def flag_for_review(conn: sqlite3.Connection, old_id: int, new_id: int, reason: str):
    """Flag a potential memory contradiction for manual human review."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """INSERT INTO memory_conflicts (old_memory_id, new_memory_id, reason, status)
               VALUES (?, ?, ?, 'pending')""",
            (old_id, new_id, reason)
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
