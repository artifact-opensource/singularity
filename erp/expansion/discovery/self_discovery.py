#!/usr/bin/env python3
"""
Self Discovery System — Main Orchestrator
Reads target locations, builds semantic map, creates digital twin data points,
saves company dataset, creates autonomous DB and ledgers.
"""

import sys, json
sys.path.insert(0, "/home/adam/workspace/singularity/erp/expansion/discovery")

from semantic_mapper import SemanticMapper
from dataset_builder import DatasetBuilder
from autonomous_ledger import AutonomousLedger

TARGETS = [
    "/home/adam/workspace/singularity/erp",
    "/home/adam/workspace/enterprise",
    "/home/adam/workspace/enterprise/divisions",
]

def main():
    print("=== SELF DISCOVERY START ===")
    mapper = SemanticMapper(TARGETS)
    semantic_map = mapper.scan()
    print(f"Scanned targets: {semantic_map['targets_scanned']}")
    print(f"Entities discovered: {len(semantic_map['entities'])}")
    print(f"Data points: {len(semantic_map['data_points'])}")

    # Build digital twin data points
    twin_points = mapper.build_twin_points()
    print(f"Twin data points: {len(twin_points)}")

    # Dataset builder
    dataset = DatasetBuilder()
    dataset.save_company_data(twin_points)
    dataset.save_semantic_map(semantic_map)
    # Load departments from artifact-project
    try:
        proj = __import__("json").load(open("/home/adam/workspace/enterprise/artifact-project.json"))
        dataset.save_departments(proj.get("departments", {}))
        dataset.build_ledger_from_project()
    except Exception:
        pass
    print(f"Dataset saved: {dataset.db_path}")
    print(f"Semantic map saved: {dataset.map_path}")

    # Autonomous ledger
    ledger = AutonomousLedger()
    ledger_id = ledger.create_ledger("singularity_erp", source_path="/home/adam/workspace/singularity/erp")
    ledger.save_company_state("digital_twin_version", "v0.7.1")
    ledger.save_company_state("twin_points_count", str(len(twin_points)))
    ledger.record(ledger_id, "init", 0.0, "Autonomous ledger created for Singularity ERP", {"points": len(twin_points)})
    consolidated_path = ledger.consolidate()
    print(f"Autonomous ledger DB: {ledger.db_path}")
    print(f"Consolidated dataset: {consolidated_path}")

    # Final output: complete map and dataset
    final_output = {
        "semantic_map": semantic_map,
        "twin_points": twin_points,
        "dataset_path": dataset.db_path,
        "map_path": dataset.map_path,
        "ledger_path": ledger.db_path,
        "consolidated_path": consolidated_path,
        "status": "discovered_configured_autonomous"
    }
    with open("/home/adam/workspace/singularity/erp/expansion/discovery/self_discovery_result.json", "w") as f:
        json.dump(final_output, f, indent=2)
    print("=== SELF DISCOVERY COMPLETE ===")
    return final_output

if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, default=str))
