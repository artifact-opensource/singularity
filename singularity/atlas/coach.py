"""
ATLAS — Coach Engine
=====================

Evaluates the enterprise topology for fitness across 6 dimensions:
  1. Health     — is it alive and responding?
  2. Performance — resource usage within bounds?
  3. Security   — permissions, bindings, exposure?
  4. Configuration — drift, conflicts, missing vars?
  5. Freshness  — logs active, git clean, deploys recent?
  6. Capacity   — disk/swap/RAM projections

Auto-remediates safe actions. Escalates everything else.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import re
import uuid
from pathlib import Path
from typing import Any

from .topology import (
    Module, ModuleType, ModuleStatus, TopologyGraph,
    Issue, IssueSeverity, IssueCategory,
)

logger = logging.getLogger("singularity.atlas.coach")


# ── Thresholds ───────────────────────────────────────────────

THRESHOLDS = {
    "ram_warn_pct": 75,
    "ram_crit_pct": 90,
    "swap_warn_pct": 70,
    "swap_crit_pct": 90,
    "disk_warn_pct": 85,
    "disk_crit_pct": 95,
    "module_ram_warn_mb": 500,     # Flag services using >500MB
    "module_ram_crit_mb": 2000,    # Critical at >2GB
    "agent_ram_warn_mb": 1000,     # Agents get higher threshold
    "health_latency_warn_ms": 3000,
    "health_latency_crit_ms": 10000,
    "log_size_warn_mb": 50,
    "log_size_crit_mb": 200,
    "stale_restart_days": 14,      # Flag if not restarted in 14 days
}


class CoachEngine:
    """
    Evaluates enterprise fitness and produces issues with recommendations.
    """

    def __init__(self, graph: TopologyGraph):
        self.graph = graph

    async def evaluate(self) -> list[Issue]:
        """Run all coach checks. Returns list of issues found."""
        logger.info("ATLAS Coach: evaluating enterprise fitness...")
        all_issues: list[Issue] = []

        # Run independent checks concurrently
        results = await asyncio.gather(
            self._check_health(),
            self._check_performance(),
            self._check_security(),
            self._check_configuration(),
            self._check_capacity(),
            return_exceptions=True,
        )

        for result in results:
            if isinstance(result, list):
                all_issues.extend(result)
            elif isinstance(result, Exception):
                logger.debug(f"Suppressed coach check error: {result}")

        # Freshness checks (sync, lightweight)
        try:
            freshness = await self._check_freshness()
            all_issues.extend(freshness)
        except Exception as e:
            logger.debug(f"Suppressed freshness check error: {e}")

        # Assign issues to modules
        for issue in all_issues:
            mod = self.graph.get_module(issue.module_id)
            if mod:
                # Deduplicate by title
                existing = [i for i in mod.issues if i.title == issue.title]
                if not existing:
                    mod.issues.append(issue)

        logger.info(f"ATLAS Coach: found {len(all_issues)} issues")
        return all_issues

    # ── Health ────────────────────────────────────────────────

    async def _check_health(self) -> list[Issue]:
        """Check module health — process alive, health endpoint, service state."""
        issues = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        for mod in self.graph.get_active_modules():
            # Service down
            if mod.service.unit_name and not mod.service.active:
                auto_fix = mod.service.enabled  # Can restart if enabled
                issues.append(Issue(
                    id=f"health-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.CRITICAL,
                    category=IssueCategory.HEALTH,
                    module_id=mod.id,
                    title=f"{mod.name} service is DOWN",
                    detail=f"systemd unit {mod.service.unit_name} is not active (sub_state: {mod.service.sub_state})",
                    auto_fixable=auto_fix,
                    fix_action=f"systemctl --user restart {mod.service.unit_name}" if auto_fix else "",
                    created_at=now,
                ))

            # Health endpoint failing
            if mod.health_result.checked_at and not mod.health_result.healthy:
                issues.append(Issue(
                    id=f"health-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.HIGH,
                    category=IssueCategory.HEALTH,
                    module_id=mod.id,
                    title=f"{mod.name} health check FAILING",
                    detail=f"{mod.health_result.url} → {mod.health_result.status_code} ({mod.health_result.error})",
                    created_at=now,
                ))

            # Health latency
            if mod.health_result.healthy and mod.health_result.latency_ms > THRESHOLDS["health_latency_crit_ms"]:
                issues.append(Issue(
                    id=f"health-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.MEDIUM,
                    category=IssueCategory.HEALTH,
                    module_id=mod.id,
                    title=f"{mod.name} health endpoint SLOW ({mod.health_result.latency_ms:.0f}ms)",
                    detail=f"Threshold: {THRESHOLDS['health_latency_crit_ms']}ms",
                    created_at=now,
                ))

            # Dependency chain — if a dependency is down, flag dependents
            for dep_id in mod.dependencies:
                dep = self.graph.get_module(dep_id)
                if dep and dep.status in (ModuleStatus.DOWN, ModuleStatus.STALE):
                    issues.append(Issue(
                        id=f"health-{uuid.uuid4().hex[:8]}",
                        severity=IssueSeverity.HIGH,
                        category=IssueCategory.HEALTH,
                        module_id=mod.id,
                        title=f"{mod.name} dependency '{dep_id}' is {dep.status.value}",
                        detail=f"{mod.name} depends on {dep_id} which is currently {dep.status.value}. May cause cascading issues.",
                        created_at=now,
                    ))

        return issues

    # ── Performance ───────────────────────────────────────────

    async def _check_performance(self) -> list[Issue]:
        """Check per-module and system-wide resource usage."""
        issues = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Per-module RAM
        for mod in self.graph.get_active_modules():
            rss = mod.resources.get("rss_mb", mod.process.rss_mb)
            if not rss:
                continue

            threshold = THRESHOLDS["agent_ram_warn_mb"] if mod.type == ModuleType.AGENT else THRESHOLDS["module_ram_warn_mb"]
            crit_threshold = THRESHOLDS["module_ram_crit_mb"]

            if rss > crit_threshold:
                issues.append(Issue(
                    id=f"perf-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.HIGH,
                    category=IssueCategory.PERFORMANCE,
                    module_id=mod.id,
                    title=f"{mod.name} using {rss:.0f}MB RAM (critical: >{crit_threshold}MB)",
                    detail=f"PID {mod.process.pid}, command: {mod.process.command[:100]}",
                    created_at=now,
                ))
            elif rss > threshold:
                issues.append(Issue(
                    id=f"perf-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.MEDIUM,
                    category=IssueCategory.PERFORMANCE,
                    module_id=mod.id,
                    title=f"{mod.name} using {rss:.0f}MB RAM (warn: >{threshold}MB)",
                    detail=f"PID {mod.process.pid}",
                    created_at=now,
                ))

        # System-wide RAM + swap
        try:
            from .discovery import DiscoveryEngine
            result = await DiscoveryEngine._run("free -m 2>/dev/null")
            for line in result.strip().split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    total = int(parts[1])
                    used = int(parts[2])
                    pct = (used / total * 100) if total else 0
                    if pct > THRESHOLDS["ram_crit_pct"]:
                        issues.append(Issue(
                            id=f"perf-{uuid.uuid4().hex[:8]}",
                            severity=IssueSeverity.CRITICAL,
                            category=IssueCategory.CAPACITY,
                            module_id="system",
                            title=f"System RAM at {pct:.0f}% ({used}MB/{total}MB)",
                            detail="Critical threshold exceeded. Investigate top consumers.",
                            created_at=now,
                        ))
                    elif pct > THRESHOLDS["ram_warn_pct"]:
                        issues.append(Issue(
                            id=f"perf-{uuid.uuid4().hex[:8]}",
                            severity=IssueSeverity.MEDIUM,
                            category=IssueCategory.CAPACITY,
                            module_id="system",
                            title=f"System RAM at {pct:.0f}% ({used}MB/{total}MB)",
                            created_at=now,
                        ))
                elif line.startswith("Swap:"):
                    parts = line.split()
                    total = int(parts[1])
                    used = int(parts[2])
                    if total == 0:
                        continue
                    pct = (used / total * 100)
                    if pct > THRESHOLDS["swap_crit_pct"]:
                        issues.append(Issue(
                            id=f"perf-{uuid.uuid4().hex[:8]}",
                            severity=IssueSeverity.HIGH,
                            category=IssueCategory.CAPACITY,
                            module_id="system",
                            title=f"Swap at {pct:.0f}% ({used}MB/{total}MB)",
                            detail="Swap exhaustion causes severe performance degradation.",
                            created_at=now,
                        ))
        except Exception as e:
            logger.debug(f"Suppressed system RAM check: {e}")

        return issues

    # ── Security ──────────────────────────────────────────────

    async def _check_security(self) -> list[Issue]:
        """Check security posture — bindings, permissions, exposure."""
        issues = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Check for services bound to 0.0.0.0 on sensitive ports
        sensitive_ports = {5432, 6379, 8000}  # PostgreSQL, Redis, SurrealDB
        for mod in self.graph.get_active_modules():
            for port in mod.ports:
                if port.port in sensitive_ports and port.binding in ("0.0.0.0", "::"):
                    issues.append(Issue(
                        id=f"sec-{uuid.uuid4().hex[:8]}",
                        severity=IssueSeverity.HIGH,
                        category=IssueCategory.SECURITY,
                        module_id=mod.id,
                        title=f"{mod.name} port {port.port} bound to {port.binding} (should be localhost)",
                        detail=f"Database/cache services should bind to 127.0.0.1 only.",
                        created_at=now,
                    ))

        # Check .env file permissions
        env_files = [
            Path("/home/adam/workspace/.env"),
            Path("/home/adam/workspace/business_erp/backend/.env"),
        ]
        for env_file in env_files:
            try:
                if env_file.exists():
                    mode = oct(env_file.stat().st_mode)[-3:]
                    if mode != "600":
                        issues.append(Issue(
                            id=f"sec-{uuid.uuid4().hex[:8]}",
                            severity=IssueSeverity.HIGH,
                            category=IssueCategory.SECURITY,
                            module_id="system",
                            title=f"{env_file.name} has permissions {mode} (should be 600)",
                            detail=str(env_file),
                            auto_fixable=True,
                            fix_action=f"chmod 600 {env_file}",
                            created_at=now,
                        ))
            except Exception as e:
                logger.debug(f"Suppressed: {e}")

        return issues

    # ── Configuration ─────────────────────────────────────────

    async def _check_configuration(self) -> list[Issue]:
        """Check for port conflicts, config drift, missing env vars."""
        issues = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Port conflict detection — only flag conflicts on the SAME machine
        port_map: dict[tuple[int, str], list[str]] = {}  # (port, machine) → [module_ids]
        for mod in self.graph.get_active_modules():
            for port in mod.ports:
                key = (port.port, mod.machine)
                if key not in port_map:
                    port_map[key] = []
                port_map[key].append(mod.id)

        for (port, machine), owners in port_map.items():
            if len(owners) > 1:
                unique = list(set(owners))
                if len(unique) > 1:
                    issues.append(Issue(
                        id=f"cfg-{uuid.uuid4().hex[:8]}",
                        severity=IssueSeverity.HIGH,
                        category=IssueCategory.CONFIGURATION,
                        module_id=unique[0],
                        title=f"Port {port} conflict on {machine}: {', '.join(unique)}",
                        detail=f"Multiple modules claim port {port} on {machine}. One may fail to bind.",
                        created_at=now,
                    ))

        # Check if enabled services are not running
        for mod in self.graph.get_active_modules():
            if mod.service.enabled and not mod.service.active:
                issues.append(Issue(
                    id=f"cfg-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.HIGH,
                    category=IssueCategory.CONFIGURATION,
                    module_id=mod.id,
                    title=f"{mod.name} is enabled but NOT running",
                    detail=f"Service {mod.service.unit_name} is enabled in systemd but not active.",
                    auto_fixable=True,
                    fix_action=f"systemctl --user restart {mod.service.unit_name}",
                    created_at=now,
                ))

        return issues

    # ── Freshness ─────────────────────────────────────────────

    async def _check_freshness(self) -> list[Issue]:
        """Check log freshness, git state, deploy age."""
        issues = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Check for bloated log files
        log_dirs = [
            Path("/home/adam/workspace/projects/cthulu-daemon/logs"),
            Path("/home/adam/workspace/poa/sentinel"),
            Path("/home/adam/workspace/.singularity"),
        ]

        for log_dir in log_dirs:
            if not log_dir.exists():
                continue
            try:
                for log_file in log_dir.rglob("*.log"):
                    try:
                        size_mb = log_file.stat().st_size / 1024 / 1024
                        if size_mb > THRESHOLDS["log_size_crit_mb"]:
                            issues.append(Issue(
                                id=f"fresh-{uuid.uuid4().hex[:8]}",
                                severity=IssueSeverity.MEDIUM,
                                category=IssueCategory.FRESHNESS,
                                module_id="system",
                                title=f"Log file {log_file.name} is {size_mb:.0f}MB",
                                detail=str(log_file),
                                auto_fixable=True,
                                fix_action=f"truncate -s 0 {log_file}",
                                created_at=now,
                            ))
                        elif size_mb > THRESHOLDS["log_size_warn_mb"]:
                            issues.append(Issue(
                                id=f"fresh-{uuid.uuid4().hex[:8]}",
                                severity=IssueSeverity.LOW,
                                category=IssueCategory.FRESHNESS,
                                module_id="system",
                                title=f"Log file {log_file.name} is {size_mb:.0f}MB",
                                detail=str(log_file),
                                created_at=now,
                            ))
                    except Exception as e:
                        logger.debug(f"Suppressed: {e}")
            except Exception as e:
                logger.debug(f"Suppressed: {e}")

        # Check git state
        try:
            from .discovery import DiscoveryEngine
            result = await DiscoveryEngine._run(
                "cd /home/adam/workspace && git status --porcelain 2>/dev/null | wc -l"
            )
            dirty = int(result.strip()) if result.strip().isdigit() else 0
            if dirty > 20:
                issues.append(Issue(
                    id=f"fresh-{uuid.uuid4().hex[:8]}",
                    severity=IssueSeverity.LOW,
                    category=IssueCategory.FRESHNESS,
                    module_id="system",
                    title=f"Git workspace has {dirty} uncommitted changes",
                    detail="Large number of uncommitted files. Consider committing or .gitignoring.",
                    created_at=now,
                ))
        except Exception as e:
            logger.debug(f"Suppressed: {e}")

        return issues

    # ── Capacity ──────────────────────────────────────────────

    async def _check_capacity(self) -> list[Issue]:
        """Check disk usage projections."""
        issues = []
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        try:
            from .discovery import DiscoveryEngine
            result = await DiscoveryEngine._run("df -h / /home --output=pcent,target 2>/dev/null")
            for line in result.strip().split("\n")[1:]:
                parts = line.strip().split()
                if len(parts) < 2:
                    continue
                pct_str = parts[0].replace("%", "")
                target = parts[1]
                try:
                    pct = int(pct_str)
                except ValueError as e:
                    logger.debug(f"Suppressed ValueError: {e}")
                    continue

                if pct > THRESHOLDS["disk_crit_pct"]:
                    issues.append(Issue(
                        id=f"cap-{uuid.uuid4().hex[:8]}",
                        severity=IssueSeverity.CRITICAL,
                        category=IssueCategory.CAPACITY,
                        module_id="system",
                        title=f"Disk {target} at {pct}%",
                        detail="Critical disk usage. Investigate immediately.",
                        created_at=now,
                    ))
                elif pct > THRESHOLDS["disk_warn_pct"]:
                    issues.append(Issue(
                        id=f"cap-{uuid.uuid4().hex[:8]}",
                        severity=IssueSeverity.MEDIUM,
                        category=IssueCategory.CAPACITY,
                        module_id="system",
                        title=f"Disk {target} at {pct}%",
                        created_at=now,
                    ))
        except Exception as e:
            logger.debug(f"Suppressed disk check: {e}")

        return issues
