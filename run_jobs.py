import os
import argparse
import asyncio
import sqlite3
from datetime import datetime, timedelta
from dotenv import load_dotenv

from database import get_db, initialize_db
from cognitive import roll_up_day, roll_up_month, roll_up_year
from security import sweep_expired_unverified_memories

load_dotenv()

def safe_backup(db_path: str, backup_dir: str):
    """
    Safely backup the active SQLite database using Python's native backup API.
    Avoids corrupting the database file mid-write.
    """
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")
    
    print(f"Starting safe database backup from '{db_path}' to '{backup_path}'...")
    
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    try:
        with dst:
            src.backup(dst)
        print(f"Backup completed successfully: '{backup_path}'")
    except Exception as e:
        print(f"Error during database backup: {e}")
    finally:
        dst.close()
        src.close()

def print_metrics(db_path: str):
    """Print key database size, record counts, and conflict stats."""
    if not os.path.exists(db_path):
        print(f"Database does not exist at '{db_path}'")
        return
        
    conn = get_db(db_path)
    try:
        db_size_bytes = os.path.getsize(db_path)
        db_size_mb = db_size_bytes / (1024 * 1024)
        
        # Check WAL size if it exists
        wal_path = f"{db_path}-wal"
        wal_size_mb = 0.0
        if os.path.exists(wal_path):
            wal_size_mb = os.path.getsize(wal_path) / (1024 * 1024)
            
        print("=== DATABASE METRICS ===")
        print(f"Main DB File Size:  {db_size_mb:.4f} MB")
        print(f"WAL File Size:      {wal_size_mb:.4f} MB")
        
        # Event count
        events_total = conn.execute("SELECT COUNT(*) FROM memory_events").fetchone()[0]
        events_active = conn.execute("SELECT COUNT(*) FROM memory_events WHERE superseded_by IS NULL").fetchone()[0]
        events_superseded = conn.execute("SELECT COUNT(*) FROM memory_events WHERE superseded_by IS NOT NULL").fetchone()[0]
        
        print(f"Total Raw Events:   {events_total} (Active: {events_active}, Superseded: {events_superseded})")
        
        # Rollups
        days_count = conn.execute("SELECT COUNT(*) FROM memory_days").fetchone()[0]
        months_count = conn.execute("SELECT COUNT(*) FROM memory_months").fetchone()[0]
        years_count = conn.execute("SELECT COUNT(*) FROM memory_years").fetchone()[0]
        
        print(f"Rollups:            Days: {days_count}, Months: {months_count}, Years: {years_count}")
        
        # Conflicts
        pending_conflicts = conn.execute("SELECT COUNT(*) FROM memory_conflicts WHERE status = 'pending'").fetchone()[0]
        resolved_conflicts = conn.execute("SELECT COUNT(*) FROM memory_conflicts WHERE status = 'resolved'").fetchone()[0]
        
        print(f"Conflicts:          Pending: {pending_conflicts}, Resolved: {resolved_conflicts}")
        
        # Namespace details
        namespaces = conn.execute("SELECT agent_id, owner_id FROM agent_namespaces").fetchall()
        print("Namespaces registered:")
        for ns in namespaces:
            print(f"  - Agent ID: '{ns['agent_id']}' (Owner: '{ns['owner_id']}')")
            
        print("========================")
    finally:
        conn.close()

async def main():
    parser = argparse.ArgumentParser(description="Agent Memory System - Operations & Rollup Runner")
    parser.add_argument("--agent-id", help="Target agent ID for rollups and sweeps")
    parser.add_argument("--date", help="Target date for Day rollup (YYYY-MM-DD), defaults to yesterday")
    parser.add_argument("--month", help="Target month for Month rollup (YYYY-MM), e.g. 2026-06")
    parser.add_argument("--year", type=int, help="Target year for Year rollup (YYYY)")
    parser.add_argument("--sweep", action="store_true", help="Run TTL sweep on low-confidence unverified memories")
    parser.add_argument("--backup-dir", help="Safely backup SQLite DB to the specified directory")
    parser.add_argument("--metrics", action="store_true", help="Display db metrics and record counts")
    
    args = parser.parse_args()
    
    db_path = os.getenv("DATABASE_PATH", "memory.db")
    
    # Initialize DB if it doesn't exist
    conn = get_db(db_path)
    initialize_db(conn)
    conn.close()
    
    if args.backup_dir:
        safe_backup(db_path, args.backup_dir)
        
    if args.metrics:
        print_metrics(db_path)
        
    if args.sweep:
        if not args.agent_id:
            print("Error: --agent-id is required for TTL sweep.")
            return
        print(f"Running unverified memory TTL sweep for agent '{args.agent_id}'...")
        conn = get_db(db_path)
        try:
            sweep_expired_unverified_memories(conn)
            print("TTL sweep complete.")
        finally:
            conn.close()
            
    # Temporal rollups
    if args.date or args.month or args.year:
        if not args.agent_id:
            print("Error: --agent-id is required for rollups.")
            return
            
        conn = get_db(db_path)
        try:
            if args.date:
                target_date = args.date
            else:
                # default to yesterday's date if date is passed as empty but month/year was not requested
                target_date = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
                
            if args.date:
                print(f"Running Day rollup for agent '{args.agent_id}' on {target_date}...")
                await roll_up_day(conn, args.agent_id, target_date)
                
            if args.month:
                print(f"Running Month rollup for agent '{args.agent_id}' on {args.month}...")
                await roll_up_month(conn, args.agent_id, args.month)
                
            if args.year:
                print(f"Running Year rollup for agent '{args.agent_id}' on {args.year}...")
                await roll_up_year(conn, args.agent_id, args.year)
                
            print("Rollups complete.")
        finally:
            conn.close()

if __name__ == "__main__":
    asyncio.run(main())
