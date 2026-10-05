#!/usr/bin/env python3
"""
Self-Discovery: reads target locations to build semantic map and configures.
Nothing more, nothing less.
"""

import os, json, csv, re
from pathlib import Path
from typing import List, Dict, Optional

TARGET_PATHS = [
    "../../../../singularity/erp",
    "../../../workspace/enterprise",
    "../../../workspace/enterprise/divisions",
]

class SemanticMapper:
    def __init__(self, targets=TARGET_PATHS):
        self.targets = targets
        self.map = {}

    def scan(self) -> Dict:
        self.map = {"targets_scanned": 0, "entities": {}, "data_points": []}
        for p in self.targets:
            self._scan_path(Path(p))
        self.map["targets_scanned"] = len(self.targets)
        return self.map

    def _scan_path(self, path: Path):
        if not path.exists():
            return
        for file in path.rglob("*"):
            if file.is_file() and file.suffix in (".json", ".md", ".csv", ".yaml", ".yml"):
                self.map["data_points"].append({
                    "path": str(file),
                    "type": file.suffix,
                    "size": file.stat().st_size,
                })
                # Extract entity names from filenames/dirs
                entity = file.parent.name if file.parent.name else file.name
                if entity not in self.map["entities"]:
                    self.map["entities"][entity] = {"files": [], "semantic_tags": []}
                self.map["entities"][entity]["files"].append(str(file))
                # Tag based on content keywords
                tags = self._tag_file(file)
                self.map["entities"][entity]["semantic_tags"].extend(tags)

    def _tag_file(self, file: Path) -> List[str]:
        tags = []
        try:
            text = file.read_text(errors="ignore")[:2000]
            if "ERP" in text or "erp" in text: tags.append("erp")
            if "department" in text.lower(): tags.append("department")
            if "financial" in text.lower() or "ledger" in text.lower(): tags.append("financial")
            if "simulation" in text.lower() or "twin" in text.lower(): tags.append("simulation")
            if "vector" in text.lower() or "embed" in text.lower(): tags.append("vector")
            if "competitive" in text.lower() or "intelligence" in text.lower(): tags.append("competitive")
        except Exception:
            pass
        return list(set(tags))

    def build_twin_points(self) -> List[Dict]:
        """Generate data points needed to build the digital twin."""
        points = []
        # From artifact-project.json
        try:
            proj = json.load(open("../../../workspace/enterprise/artifact-project.json"))
            org = proj.get("organization", {})
            points.append({"source": "artifact-project", "entity": "company", "type": "org", "data": org})
            for dept, info in proj.get("departments", {}).items():
                points.append({"source": "artifact-project", "entity": dept, "type": "department", "data": info})
        except Exception as e:
            points.append({"source": "discovery", "error": str(e)})
        # From enterprise divisions
        csv_files = list(Path("../../../workspace/enterprise/divisions").rglob("*.csv"))
        for div_path in csv_files[:10]:
            try:
                with open(div_path) as f:
                    reader = csv.reader(f)
                    headers = next(reader, None)
                    points.append({"source": str(div_path), "entity": div_path.parent.name, "type": "division_data", "headers": headers})
            except Exception:
                pass
        self.map["twin_points"] = points
        return points
