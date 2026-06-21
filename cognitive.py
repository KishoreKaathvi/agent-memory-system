import json
import sqlite3
import logging
from datetime import datetime
from database import get_db
from retrieval import get_embedder
from llm import generate_answer

cognitive_logger = logging.getLogger("memory.cognitive")

MAX_SUMMARY_INPUT_TOKENS = 6000  # fits comfortably in free-tier windows

def format_for_summary(rows: list, max_tokens: int = MAX_SUMMARY_INPUT_TOKENS) -> list[str]:
    """
    Format rows into string blocks. Splits rows if they exceed the character limit (tokens * 4).
    Returns a list of string blocks, each safe to summarize in a single LLM call.
    """
    max_chars = max_tokens * 4
    blocks = []
    current_block = []
    current_length = 0
    
    for r in rows:
        line = f"- [{r['memory_type']}] {r['content']} (confidence: {r['confidence']})"
        if current_length + len(line) > max_chars and current_block:
            blocks.append("\n".join(current_block))
            current_block = [line]
            current_length = len(line)
        else:
            current_block.append(line)
            current_length += len(line)
            
    if current_block:
        blocks.append("\n".join(current_block))
        
    return blocks

async def roll_up_day(conn: sqlite3.Connection, agent_id: str, target_date: str):
    """
    Rolls up a single day's raw memory events into a Day summary.
    Enforces idempotency and tracks source ID lineages.
    """
    # 1. Idempotency Check
    existing = conn.execute(
        "SELECT id FROM memory_days WHERE agent_id = ? AND day_date = ?",
        (agent_id, target_date)
    ).fetchone()
    if existing:
        cognitive_logger.info(f"Day rollup already exists for agent {agent_id} on {target_date}. Skipping.")
        return existing["id"]

    # 2. Fetch raw events for this date
    rows = conn.execute(
        """SELECT id, memory_type, content, confidence FROM memory_events 
           WHERE agent_id = ? AND date(created_at) = ? AND superseded_by IS NULL""",
        (agent_id, target_date)
    ).fetchall()
    
    if not rows:
        cognitive_logger.info(f"No events to rollup for agent {agent_id} on {target_date}.")
        return None

    # 3. Format and chunk if necessary
    blocks = format_for_summary(rows)
    block_summaries = []
    
    # 4. Generate LLM summaries for each block
    for idx, block in enumerate(blocks):
        prompt = f"Summarize these events from {target_date} concisely, preserving decisions, commitments, and key facts. Keep it factual."
        summary = await generate_answer(query=prompt, context_str=block)
        block_summaries.append(summary)
        
    # If we had multiple blocks, merge them into a single final summary
    if len(block_summaries) > 1:
        merged_context = "\n\n".join(block_summaries)
        prompt = f"Consolidate these daily summaries for {target_date} into a single unified summary. Retain key facts, decisions, and commitments."
        final_summary = await generate_answer(query=prompt, context_str=merged_context)
    else:
        final_summary = block_summaries[0]

    # 5. Generate embedding for the final rollup summary
    embedder = get_embedder()
    emb = embedder.encode(final_summary)
    emb_bytes = emb.tobytes()
    source_ids = json.dumps([r["id"] for r in rows])

    # 6. Database transaction (atomic write)
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO memory_days (agent_id, day_date, summary, source_ids, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_id, target_date, final_summary, source_ids, emb_bytes)
        )
        record_id = cursor.lastrowid
        
        # Update Table of Contents
        conn.execute(
            """INSERT OR REPLACE INTO memory_toc (agent_id, period_type, period_key, record_id)
               VALUES (?, 'day', ?, ?)""",
            (agent_id, target_date, record_id)
        )
        conn.commit()
        cognitive_logger.info(f"Successfully rolled up day {target_date} for agent {agent_id} (ID: {record_id})")
        return record_id
    except Exception:
        conn.rollback()
        raise

async def roll_up_month(conn: sqlite3.Connection, agent_id: str, target_month: str):
    """
    Rolls up a single month's Day summaries into a Month summary (target_month format: 'YYYY-MM').
    """
    # 1. Idempotency Check
    existing = conn.execute(
        "SELECT id FROM memory_months WHERE agent_id = ? AND month_date = ?",
        (agent_id, target_month)
    ).fetchone()
    if existing:
        cognitive_logger.info(f"Month rollup already exists for agent {agent_id} on {target_month}. Skipping.")
        return existing["id"]

    # 2. Fetch Day rollups for this month
    rows = conn.execute(
        """SELECT id, summary FROM memory_days 
           WHERE agent_id = ? AND strftime('%Y-%m', day_date) = ?""",
        (agent_id, target_month)
    ).fetchall()
    
    if not rows:
        cognitive_logger.info(f"No daily summaries to rollup for agent {agent_id} on month {target_month}.")
        return None

    # 3. Format context
    formatted_context = "\n".join(f"- Day Summary (ID {r['id']}): {r['summary']}" for r in rows)
    prompt = f"Summarize these daily logs from {target_month} into a single, concise monthly summary. Highlight recurring patterns, key milestones, and decisions."
    
    final_summary = await generate_answer(query=prompt, context_str=formatted_context)
    
    # 4. Generate embedding
    embedder = get_embedder()
    emb = embedder.encode(final_summary)
    emb_bytes = emb.tobytes()
    source_ids = json.dumps([r["id"] for r in rows])

    # 5. Database transaction
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO memory_months (agent_id, month_date, summary, source_ids, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_id, target_month, final_summary, source_ids, emb_bytes)
        )
        record_id = cursor.lastrowid
        
        conn.execute(
            """INSERT OR REPLACE INTO memory_toc (agent_id, period_type, period_key, record_id)
               VALUES (?, 'month', ?, ?)""",
            (agent_id, target_month, record_id)
        )
        conn.commit()
        cognitive_logger.info(f"Successfully rolled up month {target_month} for agent {agent_id} (ID: {record_id})")
        return record_id
    except Exception:
        conn.rollback()
        raise

async def roll_up_year(conn: sqlite3.Connection, agent_id: str, target_year: int):
    """
    Rolls up a single year's Month summaries into a Year summary.
    """
    # 1. Idempotency Check
    existing = conn.execute(
        "SELECT id FROM memory_years WHERE agent_id = ? AND year = ?",
        (agent_id, target_year)
    ).fetchone()
    if existing:
        cognitive_logger.info(f"Year rollup already exists for agent {agent_id} on year {target_year}. Skipping.")
        return existing["id"]

    # 2. Fetch Month rollups for this year
    rows = conn.execute(
        """SELECT id, summary FROM memory_months 
           WHERE agent_id = ? AND CAST(substr(month_date, 1, 4) AS INTEGER) = ?""",
        (agent_id, target_year)
    ).fetchall()
    
    if not rows:
        cognitive_logger.info(f"No monthly summaries to rollup for agent {agent_id} on year {target_year}.")
        return None

    # 3. Format context
    formatted_context = "\n".join(f"- Month Summary (ID {r['id']}): {r['summary']}" for r in rows)
    prompt = f"Summarize these monthly logs from the year {target_year} into a high-level concise annual summary. Retain core achievements, decisions, and strategies."
    
    final_summary = await generate_answer(query=prompt, context_str=formatted_context)
    
    # 4. Generate embedding
    embedder = get_embedder()
    emb = embedder.encode(final_summary)
    emb_bytes = emb.tobytes()
    source_ids = json.dumps([r["id"] for r in rows])

    # 5. Database transaction
    conn.execute("BEGIN IMMEDIATE")
    try:
        cursor = conn.execute(
            """INSERT INTO memory_years (agent_id, year, summary, source_ids, embedding)
               VALUES (?, ?, ?, ?, ?)""",
            (agent_id, target_year, final_summary, source_ids, emb_bytes)
        )
        record_id = cursor.lastrowid
        
        conn.execute(
            """INSERT OR REPLACE INTO memory_toc (agent_id, period_type, period_key, record_id)
               VALUES (?, 'year', ?, ?)""",
            (agent_id, str(target_year), record_id)
        )
        conn.commit()
        cognitive_logger.info(f"Successfully rolled up year {target_year} for agent {agent_id} (ID: {record_id})")
        return record_id
    except Exception:
        conn.rollback()
        raise
