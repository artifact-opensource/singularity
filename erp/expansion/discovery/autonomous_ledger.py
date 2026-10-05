#!/usr/bin/env python3
"""
Autonomous Ledger: Singularity creates and saves DBs/ledgers as required.
Nothing more, nothing less.
"""

import sqlite3, json, os
from pathlib import Path
from datetime import datetime

LEDGER_DB = "/home/adam/workspace/singularity/erp/expansion/discovery/autonomous_ledger.db"

class AutonomousLedger:
    def __init__(self, db_path=LEDGER_DB):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        c = self.conn.cursor()
        c.execute("CREATE TABLE IF NOT EXISTS ledgers (ledger_id TEXT PRIMARY KEY, name TEXT, created_at TEXT, source_path TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS entries (entry_id INTEGER PRIMARY KEY AUTOINCREMENT, ledger_id TEXT, entry_type TEXT, amount REAL, description TEXT, meta_json TEXT, timestamp DEFAULT CURRENT_TIMESTAMP)")
        c.execute("CREATE TABLE IF NOT EXISTS company_state (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
        self.conn.commit()

    def create_ledger(self, name: str, source_path=""):
        lid = f"ledger_{name.lower().replace(' ','_')}_{datetime.now().strftime('%Y%m%d') }"
        c = self.conn.cursor()
        c.execute("INSERT OR IGNORE INTO ledgers (ledger_id, name, created_at, source_path) VALUES (?, ?, ?, ?)",
            (lid, name, datetime.now().isoformat(), source_path))
        self.conn.commit()
        return lid

    def record(self, ledger_id: str, entry_type: str, amount: float, description: str, meta: dict = None):
        c = self.conn.cursor()
        c.execute("INSERT INTO entries (ledger_id, entry_type, amount, description, meta_json) VALUES (?, ?, ?, ?, ?)",
            (ledger_id, entry_type, amount, description, json.dumps(meta or {})))
        self.conn.commit()

    def save_company_state(self, key: str, value: str):
        c = self.conn.cursor()
        c.execute("INSERT OR REPLACE INTO company_state (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, datetime.now().isoformat()))
        self.conn.commit()

    def consolidate(self):
        """Consolidate all ledgers into a unified dataset file."""
        output_path = "/home/adam/workspace/singularity/erp/expansion/discovery/consolidated_dataset.json"
        c = self.conn.cursor()
        c.execute("SELECT * FROM ledgers")
        ledgers = [{"lid": r[0], "name": r[1], "created": r[2], "source": r[3]} for r in c.fetchall()]
        c.execute("SELECT e.*, l.name FROM entries e JOIN ledgers l ON e.ledger_id=l.ledger_id")
        entries = [{"ledger": r[5], "type": r[3], "amount": r[4], "desc": r[5], "time": r[6]} for r in c.fetchall()]
        consolidated = {"ledgers": ledgers, "entries": entries, "generated_at": datetime.now().isoformat()}
        with open(output_path, "w") as f:
            json.dump(consolidated, f, indent=2)
        return output_path
