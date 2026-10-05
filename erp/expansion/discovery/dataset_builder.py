#!/usr/bin/env python3
"""
Dataset Builder: properly saves company data in a dataset.
Nothing more, nothing less.
"""

import json, sqlite3, os
from pathlib import Path
from typing import List, Dict

DB_PATH = "company_dataset.db"
MAP_PATH = "semantic_map.json"

class DatasetBuilder:
    def __init__(self, db_path=DB_PATH, map_path=MAP_PATH):
        self.db_path = db_path
        self.map_path = map_path
        self.conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self):
        cursor = self.conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS departments (id TEXT PRIMARY KEY, name TEXT, head TEXT, status TEXT, path TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS people (id TEXT PRIMARY KEY, name TEXT, role TEXT, dept_id TEXT, skills TEXT, hours_per_week REAL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS data_points (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT, entity TEXT, type TEXT, data TEXT, created_at DEFAULT CURRENT_TIMESTAMP)")
        cursor.execute("CREATE TABLE IF NOT EXISTS financial_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, entry_type TEXT, amount REAL, description TEXT, source_text TEXT, recorded_at DEFAULT CURRENT_TIMESTAMP)")
        self.conn.commit()

    def save_company_data(self, data_points: List[Dict]):
        cursor = self.conn.cursor()
        for pt in data_points:
            cursor.execute("INSERT INTO data_points (source, entity, type, data) VALUES (?, ?, ?, ?)",
                (pt.get("source"), pt.get("entity"), pt.get("type"), json.dumps(pt.get("data", {}))))
        self.conn.commit()

    def save_departments(self, departments: Dict):
        cursor = self.conn.cursor()
        for dept_id, info in departments.items():
            cursor.execute("INSERT OR REPLACE INTO departments (id, name, head, status, path) VALUES (?, ?, ?, ?, ?)",
                (dept_id, info.get("name") or dept_id, info.get("head", ""), info.get("status", "Active"), info.get("path", "")))
        self.conn.commit()

    def save_semantic_map(self, semantic_map: Dict):
        with open(self.map_path, "w") as f:
            json.dump(semantic_map, f, indent=2)

    def build_ledger_from_project(self, project_path="../../../workspace/enterprise/artifact-project.json"):
        try:
            proj = json.load(open(project_path))
            org = proj.get("organization", {})
            # Create initial ledger entries from project health/status
            health = proj.get("project", {}).get("health", {})
            for k, v in health.items():
                self.conn.execute("INSERT INTO financial_ledger (entry_type, amount, description, source_text) VALUES (?, ?, ?, ?)",
                    (k, 0.0, f"Project health: {k}={v}", "artifact-project.json"))
            self.conn.commit()
        except Exception:
            pass
