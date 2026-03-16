"""
Enterprise Snapshot Automation Pipeline

Captures enterprise state (modules, health, topology, metrics) on schedule.
Stores snapshots as JSON files + COMB staging for persistence.
Provides trend analysis, delta detection, and degradation alerting.
"""
import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import subprocess

import logging

logger = logging.getLogger("singularity.enterprise.snapshot")

SNAPSHOTS_DIR = Path("/home/adam/.enterprise/snapshots")
RETENTION_DAYS = 30
MAX_SNAPSHOTS = 100  # Keep max 100 snapshots even if within retention


def _run_command(cmd: list, timeout: int = 10) -> tuple:
    """Run shell command, return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return result.stdout, result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", -1
    except Exception as e:
        return "", str(e), -1


def _get_module_health() -> dict:
    """Capture module health from ATLAS."""
    # This would call ATLAS internally - for now use exec
    stdout, stderr, code = _run_command([
        "systemctl", "list-units", "--all", "--no-pager", "--no-legend"
    ])
    
    modules = {}
    if stdout:
        for line in stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4:
                unit = parts[0]
                loaded = parts[1]
                active = parts[2]
                sub = parts[3] if len(parts) > 3 else ""
                
                # Determine health status
                if active == "active":
                    status = "healthy"
                elif active in ["inactive", "dead"]:
                    status = "degraded"
                elif active == "failed":
                    status = "critical"
                else:
                    status = "unknown"
                
                modules[unit] = {
                    "unit": unit,
                    "loaded": loaded,
                    "active": active,
                    "sub": sub,
                    "status": status,
                }
    
    return modules


def _get_service_status(port: int) -> str:
    """Check if a service is responding on a port."""
    stdout, stderr, code = _run_command([
        "curl", "-sf", "-o", "/dev/null", "-w", "%{http_code}",
        f"http://127.0.0.1:{port}", "--connect-timeout", "2"
    ])
    
    if code == 0:
        if stdout.strip() == "200":
            return "healthy"
        elif stdout.strip() in ["301", "302", "304"]:
            return "healthy"
        elif stdout.strip() in ["400", "401", "403", "404"]:
            return "degraded"  # Responding but error
        elif stdout.strip() in ["500", "502", "503", "504"]:
            return "critical"
        else:
            return "unknown"
    else:
        return "unreachable"


def _get_topology() -> dict:
    """Capture enterprise topology."""
    # Parse systemctl output for active services
    stdout, stderr, code = _run_command([
        "systemctl", "list-units", "--type=service", "--no-pager", "--no-legend"
    ])
    
    services = []
    if stdout:
        for line in stdout.strip().split("\n"):
            parts = line.split()
            if parts and parts[0].endswith(".service"):
                services.append(parts[0].replace(".service", ""))
    
    return {"services": services, "captured_at": datetime.now(timezone.utc).isoformat()}


def _get_metrics() -> dict:
    """Capture system metrics."""
    metrics = {}
    
    # CPU load
    stdout, _, _ = _run_command(["cat", "/proc/loadavg"])
    if stdout:
        parts = stdout.strip().split()
        metrics["load_avg"] = {
            "1m": float(parts[0]) if parts else 0,
            "5m": float(parts[1]) if len(parts) > 1 else 0,
            "15m": float(parts[2]) if len(parts) > 2 else 0,
        }
    
    # Memory
    stdout, _, _ = _run_command(["free", "-m"])
    if stdout:
        lines = stdout.strip().split("\n")
        for line in lines:
            if line.startswith("Mem:"):
                parts = line.split()
                if len(parts) >= 7:
                    metrics["memory"] = {
                        "total_mb": int(parts[1]),
                        "used_mb": int(parts[2]),
                        "free_mb": int(parts[3]),
                        "available_mb": int(parts[6]),
                        "used_percent": round((int(parts[2]) / int(parts[1])) * 100, 1) if int(parts[1]) > 0 else 0,
                    }
    
    # Disk
    stdout, _, _ = _run_command(["df", "-h", "/home"])
    if stdout and len(stdout.strip().split("\n")) > 1:
        parts = stdout.strip().split("\n")[1].split()
        if len(parts) >= 5:
            metrics["disk"] = {
                "total": parts[1],
                "used": parts[2],
                "available": parts[3],
                "used_percent": parts[4].replace("%", ""),
            }
    
    return metrics


def _get_port_status() -> dict:
    """Check status of known enterprise ports."""
    ports = {
        "singularity": 8450,
        "comb-cloud": 8420,
        "artifact-erp": 3100,
        "mach6-gateway": 3006,
        "aria-gateway": 3007,
        "gdi-backend": 8600,
        "copilot-proxy": 3000,
        "ollama": 11434,
        "postgresql": 5432,
        "redis": 6379,
        "cthulu-daemon": 9002,
        "hektor-daemon": 20241,
    }
    
    port_status = {}
    for service, port in ports.items():
        status = _get_service_status(port)
        port_status[service] = {
            "port": port,
            "status": status,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    
    return port_status


def capture_snapshot(metadata: Optional[dict] = None) -> dict:
    """
    Capture a full enterprise snapshot.
    
    Returns:
        dict: Complete snapshot with timestamp, health, topology, metrics, ports
    """
    timestamp = datetime.now(timezone.utc)
    snapshot_id = f"snapshot-{timestamp.strftime('%Y%m%d-%H%M%S')}"
    
    logger.info(f"Capturing enterprise snapshot: {snapshot_id}")
    
    snapshot = {
        "id": snapshot_id,
        "timestamp": timestamp.isoformat(),
        "timestamp_unix": int(timestamp.timestamp()),
        "metadata": metadata or {},
        "health": _get_module_health(),
        "topology": _get_topology(),
        "metrics": _get_metrics(),
        "ports": _get_port_status(),
        "summary": {
            "total_modules": 0,
            "healthy": 0,
            "degraded": 0,
            "critical": 0,
            "unreachable": 0,
        },
    }
    
    # Calculate summary
    health_data = snapshot["health"]
    for unit, data in health_data.items():
        snapshot["summary"]["total_modules"] += 1
        status = data.get("status", "unknown")
        if status == "healthy":
            snapshot["summary"]["healthy"] += 1
        elif status == "degraded":
            snapshot["summary"]["degraded"] += 1
        elif status == "critical":
            snapshot["summary"]["critical"] += 1
        else:
            snapshot["summary"]["unreachable"] += 1
    
    # Add port summary
    port_data = snapshot["ports"]
    snapshot["summary"]["ports"] = {
        "total": len(port_data),
        "healthy": sum(1 for p in port_data.values() if p["status"] == "healthy"),
        "degraded": sum(1 for p in port_data.values() if p["status"] == "degraded"),
        "critical": sum(1 for p in port_data.values() if p["status"] == "critical"),
        "unreachable": sum(1 for p in port_data.values() if p["status"] == "unreachable"),
    }
    
    # Save to file
    snapshot_path = SNAPSHOTS_DIR / f"{snapshot_id}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, default=str))
    
    logger.info(f"Snapshot saved: {snapshot_path}")
    
    return snapshot


def list_snapshots(limit: int = 20) -> list:
    """List recent snapshots."""
    if not SNAPSHOTS_DIR.exists():
        return []
    
    snapshots = []
    for f in sorted(SNAPSHOTS_DIR.glob("snapshot-*.json"), reverse=True)[:limit]:
        try:
            data = json.loads(f.read_text())
            snapshots.append({
                "id": data.get("id"),
                "timestamp": data.get("timestamp"),
                "summary": data.get("summary"),
                "path": str(f),
            })
        except Exception:
            pass
    
    return snapshots


def compare_snapshots(id1: str, id2: str) -> dict:
    """Compare two snapshots and return delta."""
    path1 = SNAPSHOTS_DIR / f"{id1}.json"
    path2 = SNAPSHOTS_DIR / f"{id2}.json"
    
    if not path1.exists() or not path2.exists():
        return {"error": "Snapshot not found"}
    
    data1 = json.loads(path1.read_text())
    data2 = json.loads(path2.read_text())
    
    delta = {
        "id1": id1,
        "id2": id2,
        "timestamp1": data1.get("timestamp"),
        "timestamp2": data2.get("timestamp"),
        "changes": [],
    }
    
    # Compare module health
    health1 = data1.get("health", {})
    health2 = data2.get("health", {})
    
    all_units = set(health1.keys()) | set(health2.keys())
    for unit in all_units:
        h1 = health1.get(unit, {}).get("status", "unknown")
        h2 = health2.get(unit, {}).get("status", "unknown")
        if h1 != h2:
            delta["changes"].append({
                "type": "health_change",
                "unit": unit,
                "from": h1,
                "to": h2,
            })
    
    # Compare metrics
    metrics1 = data1.get("metrics", {})
    metrics2 = data2.get("metrics", {})
    
    for key in ["load_avg", "memory", "disk"]:
        m1 = metrics1.get(key, {})
        m2 = metrics2.get(key, {})
        if m1 != m2:
            delta["changes"].append({
                "type": "metrics_change",
                "metric": key,
                "from": m1,
                "to": m2,
            })
    
    # Compare ports
    ports1 = data1.get("ports", {})
    ports2 = data2.get("ports", {})
    
    for service in set(ports1.keys()) | set(ports2.keys()):
        p1 = ports1.get(service, {}).get("status", "unknown")
        p2 = ports2.get(service, {}).get("status", "unknown")
        if p1 != p2:
            delta["changes"].append({
                "type": "port_change",
                "service": service,
                "from": p1,
                "to": p2,
            })
    
    return delta


def prune_old_snapshots(retention_days: int = RETENTION_DAYS) -> int:
    """Remove snapshots older than retention period."""
    if not SNAPSHOTS_DIR.exists():
        return 0
    
    cutoff = datetime.now(timezone.utc).timestamp() - (retention_days * 86400)
    removed = 0
    
    for f in SNAPSHOTS_DIR.glob("snapshot-*.json"):
        try:
            data = json.loads(f.read_text())
            ts = data.get("timestamp_unix", 0)
            if ts < cutoff:
                f.unlink()
                removed += 1
                logger.info(f"Pruned old snapshot: {f.name}")
        except Exception:
            pass
    
    # Also enforce max count
    all_snapshots = sorted(SNAPSHOTS_DIR.glob("snapshot-*.json"))
    if len(all_snapshots) > MAX_SNAPSHOTS:
        for f in all_snapshots[:-MAX_SNAPSHOTS]:
            f.unlink()
            removed += 1
            logger.info(f"Pruned excess snapshot: {f.name}")
    
    return removed


def get_trend(limit: int = 10) -> dict:
    """Analyze trend across recent snapshots."""
    snapshots = list_snapshots(limit)
    
    if len(snapshots) < 2:
        return {"error": "Insufficient snapshots for trend analysis"}
    
    trend = {
        "snapshots_analyzed": len(snapshots),
        "oldest": snapshots[-1]["timestamp"],
        "newest": snapshots[0]["timestamp"],
        "health_trend": [],
        "degradation_events": [],
    }
    
    # Analyze health trend
    for i, snap in enumerate(snapshots):
        summary = snap.get("summary", {})
        trend["health_trend"].append({
            "id": snap["id"],
            "timestamp": snap["timestamp"],
            "healthy": summary.get("healthy", 0),
            "degraded": summary.get("degraded", 0),
            "critical": summary.get("critical", 0),
        })
    
    # Find degradation events
    for i in range(len(snapshots) - 1):
        curr = snapshots[i]
        prev = snapshots[i + 1]
        
        curr_critical = curr.get("summary", {}).get("critical", 0)
        prev_critical = prev.get("summary", {}).get("critical", 0)
        
        if curr_critical > prev_critical:
            trend["degradation_events"].append({
                "from": prev["id"],
                "to": curr["id"],
                "critical_count_change": curr_critical - prev_critical,
            })
    
    return trend
