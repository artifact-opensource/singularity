#!/usr/bin/env python3
"""
Singularity CLI — Full command interface for all new features.
Usage: python cli/singularity_cli.py <command>
"""

import argparse, sys, json, os
sys.path.insert(0, "/home/adam/workspace/singularity/erp/expansion/discovery")

# Import modules directly
from semantic_mapper import SemanticMapper
from dataset_builder import DatasetBuilder
from autonomous_ledger import AutonomousLedger
from self_discovery import main as discovery_main

# Relative import for twin
sys.path.insert(0, "/home/adam/workspace/singularity/erp/expansion")


def cmd_discover(args):
    print("=== DISCOVER ===")
    mapper = SemanticMapper(
        targets=[
            "../../singularity/erp",
            "../../../workspace/enterprise",
            "../../../workspace/enterprise/divisions",
        ]
    )
    result = mapper.scan()
    twin_points = mapper.build_twin_points()
    print(f"Targets: {result['targets_scanned']}")
    print(f"Entities: {len(result['entities'])}")
    print(f"Data points: {len(result['data_points'])}")
    print(f"Twin points: {len(twin_points)}")
    print(json.dumps(result, indent=2, default=str)[:2000])
    return result


def cmd_twin(args):
    print("=== TWIN SIMULATION ===")
    try:
        from twin.simulator import DigitalTwinSimulator, SimulationScenario
        sim = DigitalTwinSimulator()
        scenario_data = {
            "scenario_type": args.scenario,
            "description": args.description or f"Simulation: {args.scenario}",
            "budget_usd": args.budget,
            "launch_date": args.launch_date,
            "channels": args.channels.split(",") if args.channels else ["email", "paid"],
            "target_market": args.market,
            "team_deployments": {},
            "duration_weeks": args.duration,
        }
        if args.team:
            for item in args.team.split(","):
                dept, load = item.split(":") if ":" in item else (item, "1")
                scenario_data["team_deployments"][dept] = int(load)
        sc = SimulationScenario(**scenario_data)
        result = sim.simulate(sc)
        output = result.to_dict()
        print(json.dumps(output, indent=2, default=str)[:3000])
        return output
    except Exception as e:
        print(f"Simulation error: {e}")
        import traceback
        traceback.print_exc()
        return None


def cmd_vectorize(args):
    print("=== VECTORIZE ===")
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("vectorizer", "/home/adam/workspace/singularity/erp/expansion/vectorizer/vectorizer.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        worker = mod.VectorizerWorker(worker_id=1)
        result = worker.run_cycle()
        print(f"Scanned: {result['scanned']} | Changed: {result['changed']} | Embedded: {result['embedded']} | Deleted: {result['deleted']} | Errors: {len(result['errors'])}")
        if args.save and result.get("scanned", 0) > 0:
            result_path = "/home/adam/workspace/singularity/erp/expansion/discovery/vector_result.json"
            with open(result_path, "w") as f:
                json.dump({"cycle_result": result, "timestamp": str(__import__("datetime").datetime.now())}, f, default=str)
            print(f"Saved to: {result_path}")
    except Exception as e:
        print(f"Vectorization error: {e}")
        import traceback
        traceback.print_exc()


def cmd_dataset(args):
    print("=== DATASET ===")
    db_path = args.db or "company_dataset.db"
    if args.build:
        dataset = DatasetBuilder(db_path=db_path)
        try:
            proj = json.load(open("../../../workspace/enterprise/artifact-project.json"))
            dataset.save_departments(proj.get("departments", {}))
            dataset.build_ledger_from_project()
            print("Built dataset + ledger from project manifest")
        except Exception as e:
            print(f"Project load error (expected if relative): {e}")
        print(f"DB ready at: {db_path}")
    elif args.show:
        import sqlite3
        if not os.path.exists(db_path):
            print(f"DB not found: {db_path}")
            return
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [r[0] for r in c.fetchall()]
        print(f"DB: {db_path}")
        print(f"Tables: {', '.join(tables)}")
        for t in tables:
            c.execute(f"SELECT COUNT(*) FROM {t}")
            count = c.fetchone()[0]
            print(f"  {t}: {count} rows")
    else:
        dataset = DatasetBuilder(db_path=db_path)
        dataset.save_semantic_map({"dataset_path": db_path, "status": "ready"})
        print(f"Dataset initialized at: {db_path}")


def cmd_ledger(args):
    print("=== LEDGER ===")
    db_path = args.db or "autonomous_ledger.db"
    ledger = AutonomousLedger(db_path=db_path)
    if args.create:
        lid = ledger.create_ledger(args.name, source_path=args.source or ".")
        print(f"Created ledger: {lid}")
        return lid
    elif args.record:
        if not args.ledger:
            print("Error: --ledger required")
            return
        meta = {}
        if args.meta:
            meta = json.loads(args.meta) if "{" in args.meta else {"raw": args.meta}
        ledger.record(args.ledger, args.type or "entry", args.amount or 0.0, args.desc or "", meta)
        print(f"Recorded entry on {args.ledger}: {args.desc or args.type}")
    elif args.consolidate:
        out = ledger.consolidate()
        print(f"Consolidated dataset: {out}")
    else:
        # Default: show ledgers
        import sqlite3
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT ledger_id, name FROM ledgers")
        ledgers = c.fetchall()
        print(f"DB: {db_path}")
        for l in ledgers:
            print(f"  Ledger: {l[0]} ({l[1]})")


def cmd_docs(args):
    print("=== DOCS ===")
    docs_path = "/home/adam/workspace/singularity/erp/expansion/docs/"
    investor_path = docs_path + "INVESTOR/"
    if args.investor:
        files = os.listdir(investor_path) if os.path.exists(investor_path) else []
        print(f"Investor docs ({len(files)} files):")
        for f in sorted(files):
            print(f"  - {f}")
    else:
        docs_dir = "/home/adam/workspace/singularity/erp/expansion/docs/"
        print(f"Expansion docs root: {docs_dir}")
        if os.path.exists(docs_dir):
            for root, dirs, files in os.walk(docs_dir):
                for fname in sorted(files):
                    rel = os.path.join(root, fname).replace(docs_dir, "").lstrip("/")
                    print(f"  docs/{rel}")


def cmd_version(args):
    version_file = "/home/adam/workspace/singularity/erp/expansion/docs/VERSION.md"
    if os.path.exists(version_file):
        with open(version_file) as f:
            lines = [l for l in f.read().split("\n") if l.strip() and not l.startswith("# ")]
            print(f"Expansion version: v0.7.1 (Expansion Release)")
    else:
        print("Expansion version: v0.7.1")


def main():
    parser = argparse.ArgumentParser(prog="singularity", description="Singularity CLI — full features")
    sub = parser.add_subparsers(dest="command", required=True)

    # discover
    p = sub.add_parser("discover", help="Self-discovery: build semantic map + twin points")
    p.set_defaults(func=cmd_discover)

    # twin
    p = sub.add_parser("twin", help="Digital twin simulation")
    p.add_argument("--scenario", default="product_launch", choices=["product_launch", "campaign", "org_change"])
    p.add_argument("--budget", type=float, default=500000)
    p.add_argument("--market", default="enterprise")
    p.add_argument("--duration", type=int, default=24)
    p.add_argument("--description", default="Simulation run")
    p.add_argument("--launch-date", default="2025-12-01")
    p.add_argument("--channels", default="email,paid,outbound")
    p.add_argument("--team", default="")
    p.set_defaults(func=cmd_twin)

    # vectorize
    p = sub.add_parser("vectorize", help="Real-time vectorization pipeline")
    p.add_argument("--run", action="store_true", dest="run_cycle", help="Run one cycle")
    p.add_argument("--save", action="store_true", help="Save result to discovery/vector_result.json")
    p.set_defaults(func=cmd_vectorize)

    # dataset
    p = sub.add_parser("dataset", help="Dataset operations")
    p.add_argument("--build", action="store_true")
    p.add_argument("--show", action="store_true")
    p.add_argument("--db", default="company_dataset.db")
    p.set_defaults(func=cmd_dataset)

    # ledger
    p = sub.add_parser("ledger", help="Autonomous ledger operations")
    p.add_argument("--create", action="store_true")
    p.add_argument("--record", action="store_true")
    p.add_argument("--consolidate", action="store_true")
    p.add_argument("--name", default="singularity_erp")
    p.add_argument("--source", default=".")
    p.add_argument("--ledger", default="")
    p.add_argument("--type", default="entry")
    p.add_argument("--amount", type=float, default=0.0)
    p.add_argument("--desc", default="")
    p.add_argument("--meta", default="{}")
    p.add_argument("--db", default="autonomous_ledger.db")
    p.set_defaults(func=cmd_ledger)

    # docs
    p = sub.add_parser("docs", help="Documentation access")
    p.add_argument("--investor", action="store_true")
    p.set_defaults(func=cmd_docs)

    # version
    p = sub.add_parser("version", help="Show version")
    p.set_defaults(func=cmd_version)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
