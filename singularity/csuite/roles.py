"""
CSUITE — Native Role Engine (v2)
====================================

Self-scaling executive role system. Roles are data, not code.

v1 was hardcoded for Artifact Virtual's 4 executives.
v2 is industry-agnostic: Singularity proposes roles based on
what it discovers in the workspace audit.

Core principle: ROLES FOLLOW THE WORKSPACE, NOT THE OTHER WAY AROUND.

A fintech company needs a CRO (Chief Risk Officer).
A healthcare company needs a CCO (Chief Compliance Officer).
An engineering startup needs a CTO and maybe a VP Eng.
Singularity figures this out from the audit, proposes it, human approves.

Role anatomy:
    - Identity (name, domain, emoji)
    - Keywords (routing triggers)
    - Tools (what it can touch)
    - Prompt (behavioral instructions)
    - Audit scope (what it checks during heartbeats)
    - Escalation rules
    - Report format

Everything is serializable to/from YAML.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("singularity.csuite.roles")


# ══════════════════════════════════════════════════════════════
# ROLE TYPES — extensible enum
# ══════════════════════════════════════════════════════════════

class RoleType(str, Enum):
    """
    Standard executive roles. These are defaults —
    Singularity can create custom roles beyond this list.
    """
    CTO = "cto"
    COO = "coo"
    CFO = "cfo"
    CISO = "ciso"
    CRO = "cro"       # Chief Risk Officer
    CPO = "cpo"       # Chief Product Officer
    CMO = "cmo"       # Chief Marketing Officer
    CDO = "cdo"       # Chief Data Officer
    CCO = "cco"       # Chief Compliance Officer
    CTO_OPS = "cto_ops"  # Cthulu Trading Operations
    CUSTOM = "custom"  # User-defined roles

    @classmethod
    def from_str(cls, name: str) -> "RoleType":
        try:
            return cls(name.lower())
        except ValueError:
            return cls.CUSTOM


# ══════════════════════════════════════════════════════════════
# TOOL PERMISSIONS
# ══════════════════════════════════════════════════════════════

@dataclass
class ToolScope:
    """What an executive can access."""
    read_paths: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    can_exec: bool = True
    can_network: bool = False      # web_fetch, API calls
    can_message: bool = False      # send to external channels
    max_exec_timeout: int = 60
    allowed_tools: list[str] = field(default_factory=lambda: [
        "read", "write", "edit", "exec",
    ])

    def allows_path(self, path: str, write: bool = False) -> bool:
        """Check if a path is allowed."""
        for fp in self.forbidden_paths:
            if path.startswith(fp):
                return False
        targets = self.write_paths if write else (self.read_paths + self.write_paths)
        if not targets:
            return True  # no restrictions = allow all
        return any(path.startswith(p) for p in targets)

    def to_dict(self) -> dict:
        return {
            "read_paths": self.read_paths,
            "write_paths": self.write_paths,
            "forbidden_paths": self.forbidden_paths,
            "can_exec": self.can_exec,
            "can_network": self.can_network,
            "can_message": self.can_message,
            "max_exec_timeout": self.max_exec_timeout,
            "allowed_tools": self.allowed_tools,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolScope":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ══════════════════════════════════════════════════════════════
# ESCALATION
# ══════════════════════════════════════════════════════════════

@dataclass
class EscalationPolicy:
    """When and how an executive escalates."""
    on_failure: bool = True
    on_timeout: bool = True
    on_critical: bool = True
    max_retries: int = 2
    timeout_seconds: int = 300

    def to_dict(self) -> dict:
        return {
            "on_failure": self.on_failure,
            "on_timeout": self.on_timeout,
            "on_critical": self.on_critical,
            "max_retries": self.max_retries,
            "timeout_seconds": self.timeout_seconds,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "EscalationPolicy":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ══════════════════════════════════════════════════════════════
# AUDIT SCOPE
# ══════════════════════════════════════════════════════════════

@dataclass
class AuditScope:
    """What an executive checks during periodic audits."""
    checks: list[str] = field(default_factory=list)
    schedule: str = "0 */4 * * *"  # cron format
    model: str = ""                 # empty = use default

    def to_dict(self) -> dict:
        return {"checks": self.checks, "schedule": self.schedule, "model": self.model}

    @classmethod
    def from_dict(cls, d: dict) -> "AuditScope":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ══════════════════════════════════════════════════════════════
# REPORT FORMAT
# ══════════════════════════════════════════════════════════════

STANDARD_REPORT_FORMAT = """STATUS: [complete|in-progress|blocked|needs-input]
PRIORITY: [low|normal|high|critical]

FINDINGS:
- Bullet list of findings

ACTIONS:
- Actions taken

RECOMMENDATIONS:
- Next steps

— {emoji} {title} | {enterprise}"""


# ══════════════════════════════════════════════════════════════
# ROLE — the complete executive definition
# ══════════════════════════════════════════════════════════════

@dataclass
class Role:
    """
    Complete executive role definition.
    Serializable. Industry-agnostic. Self-scaling.
    """
    role_type: RoleType
    title: str
    emoji: str
    domain: str
    keywords: list[str] = field(default_factory=list)
    tools: ToolScope = field(default_factory=ToolScope)
    escalation: EscalationPolicy = field(default_factory=EscalationPolicy)
    audit: AuditScope = field(default_factory=AuditScope)
    system_prompt: str = ""
    report_format: str = ""
    enterprise: str = ""           # filled at runtime

    @property
    def name(self) -> str:
        return self.role_type.value.upper()

    @property
    def signature(self) -> str:
        ent = self.enterprise or "Singularity"
        return f"— {self.emoji} {self.title} | {ent}"

    def matches_task(self, task: str) -> float:
        """Score how well this role matches a task. 0.0-1.0."""
        task_lower = task.lower()
        if not self.keywords:
            return 0.0
        hits = sum(1 for kw in self.keywords if kw.lower() in task_lower)
        return min(hits / len(self.keywords), 1.0)

    def build_system_prompt(self) -> str:
        """Assemble the full system prompt with report format."""
        parts = [self.system_prompt]
        fmt = self.report_format or STANDARD_REPORT_FORMAT
        fmt = fmt.replace("{emoji}", self.emoji)
        fmt = fmt.replace("{title}", self.title)
        fmt = fmt.replace("{enterprise}", self.enterprise or "Singularity")
        parts.append(f"\n## Response Format\n{fmt}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "role_type": self.role_type.value,
            "title": self.title,
            "emoji": self.emoji,
            "domain": self.domain,
            "keywords": self.keywords,
            "tools": self.tools.to_dict(),
            "escalation": self.escalation.to_dict(),
            "audit": self.audit.to_dict(),
            "system_prompt": self.system_prompt,
            "report_format": self.report_format,
            "enterprise": self.enterprise,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Role":
        return cls(
            role_type=RoleType.from_str(d.get("role_type", "custom")),
            title=d.get("title", "Executive"),
            emoji=d.get("emoji", "👤"),
            domain=d.get("domain", ""),
            keywords=d.get("keywords", []),
            tools=ToolScope.from_dict(d.get("tools", {})),
            escalation=EscalationPolicy.from_dict(d.get("escalation", {})),
            audit=AuditScope.from_dict(d.get("audit", {})),
            system_prompt=d.get("system_prompt", ""),
            report_format=d.get("report_format", ""),
            enterprise=d.get("enterprise", ""),
        )

    def save(self, path: Path) -> None:
        """Persist role definition to JSON."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "Role":
        """Load role definition from JSON."""
        return cls.from_dict(json.loads(path.read_text()))


# ══════════════════════════════════════════════════════════════
# EXECUTIVE PROMPT BUILDER
# ══════════════════════════════════════════════════════════════

def build_executive_prompt(
    role_type: str,
    title: str,
    emoji: str,
    domain: str,
    enterprise: str,
    industry: str = "",
    workspace_context: str = "",
) -> str:
    """
    Build a system prompt for any executive role.
    Industry-agnostic. Self-scaling.
    """
    industry_line = f"Industry: {industry}" if industry else ""
    context_block = f"\n## Workspace Context\n{workspace_context}" if workspace_context else ""

    return f"""You are the {title} of {enterprise}.

## Identity
- Title: {title}
- Role: {role_type.upper()}
- Reports to: Coordinator → Administrator → CEO
- Emoji: {emoji}
{industry_line}

## Domain
{domain}

## Behavioral Rules
- Tool-first: execute ALL work before generating your final report.
- Be precise. Cite evidence. Show your work.
- No opinions without data. No recommendations without analysis.
- Flag blockers immediately. Don't sit on problems.
- Read workspace documentation before making assumptions.
- Never expose credentials, keys, or sensitive data.
- Keep reports structured. Machine-parseable. Brief.
{context_block}

## Output Contract
Every response follows this structure exactly:
```
STATUS: [complete|in-progress|blocked|needs-input]
PRIORITY: [low|normal|high|critical]

FINDINGS:
- finding 1
- finding 2

ACTIONS:
- action 1
- action 2

RECOMMENDATIONS:
- recommendation 1

— {emoji} {title} | {enterprise}
```

Deviations from this format are bugs."""


# ══════════════════════════════════════════════════════════════
# ROLE REGISTRY — manages the active set of executives
# ══════════════════════════════════════════════════════════════

class RoleRegistry:
    """
    Manages executive roles. Supports:
    - Loading from config/disk
    - Adding/removing at runtime
    - Proposing new roles from audit data
    - Serializing the full registry
    """

    def __init__(self, enterprise: str = "", industry: str = ""):
        self.enterprise = enterprise
        self.industry = industry
        self._roles: dict[str, Role] = {}

    def register(self, role: Role) -> None:
        """Register an executive role."""
        role.enterprise = self.enterprise
        self._roles[role.role_type.value] = role
        logger.info(f"Registered executive: {role.emoji} {role.title}")

    def unregister(self, role_type: str) -> bool:
        """Remove an executive role."""
        return self._roles.pop(role_type.lower(), None) is not None

    def get(self, role_type: str) -> Optional[Role]:
        """Get a role by type string."""
        return self._roles.get(role_type.lower())

    @property
    def roles(self) -> list[Role]:
        return list(self._roles.values())

    @property
    def role_types(self) -> list[str]:
        return list(self._roles.keys())

    def match(self, task: str, threshold: float = 0.05) -> list[tuple[Role, float]]:
        """Match a task to roles by relevance."""
        matches = []
        for role in self._roles.values():
            score = role.matches_task(task)
            if score >= threshold:
                matches.append((role, score))
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def propose_roles(self, audit_data: dict) -> list[dict]:
        """
        Given workspace audit data, propose which executive roles
        are needed but not yet registered.

        Returns list of proposals with justification.
        """
        proposals = []
        existing = set(self._roles.keys())

        # Analyze what the workspace contains
        has_code = audit_data.get("has_code", False)
        has_infra = audit_data.get("has_infrastructure", False)
        has_finance = audit_data.get("has_finance", False)
        has_security = audit_data.get("has_security_concerns", False)
        has_products = audit_data.get("live_products", 0) > 0
        has_customers = audit_data.get("has_customers", False)
        has_data = audit_data.get("has_data_pipeline", False)
        has_compliance = audit_data.get("has_compliance_needs", False)
        has_marketing = audit_data.get("has_marketing", False)
        project_count = audit_data.get("project_count", 0)
        team_size = audit_data.get("team_size", 1)
        industry = audit_data.get("industry", self.industry)

        # CTO — needed if there's code or infrastructure
        if (has_code or has_infra) and "cto" not in existing:
            proposals.append({
                "role": "cto",
                "title": "Chief Technology Officer",
                "justification": f"Workspace contains {audit_data.get('code_projects', 0)} code projects and infrastructure",
                "priority": "high",
            })

        # COO — needed if there are products or operations
        if (has_products or project_count > 3) and "coo" not in existing:
            proposals.append({
                "role": "coo",
                "title": "Chief Operating Officer",
                "justification": f"{project_count} projects detected, operational coordination needed",
                "priority": "high" if project_count > 5 else "medium",
            })

        # CFO — needed if there's revenue or finance
        if has_finance and "cfo" not in existing:
            proposals.append({
                "role": "cfo",
                "title": "Chief Financial Officer",
                "justification": "Financial operations detected (pricing, billing, revenue)",
                "priority": "medium",
            })

        # CISO — needed if security concerns or compliance
        if (has_security or has_compliance) and "ciso" not in existing:
            proposals.append({
                "role": "ciso",
                "title": "Chief Information Security Officer",
                "justification": "Security-sensitive assets detected (credentials, APIs, user data)",
                "priority": "high",
            })

        # CPO — needed if multiple products
        if audit_data.get("live_products", 0) > 2 and "cpo" not in existing:
            proposals.append({
                "role": "cpo",
                "title": "Chief Product Officer",
                "justification": f"{audit_data.get('live_products', 0)} live products require product strategy coordination",
                "priority": "medium",
            })

        # CDO — needed if data pipelines
        if has_data and "cdo" not in existing:
            proposals.append({
                "role": "cdo",
                "title": "Chief Data Officer",
                "justification": "Data pipelines and datasets detected",
                "priority": "medium",
            })

        # CRO — industry-specific
        if industry in ("fintech", "banking", "insurance", "trading") and "cro" not in existing:
            proposals.append({
                "role": "cro",
                "title": "Chief Risk Officer",
                "justification": f"Industry ({industry}) requires dedicated risk management",
                "priority": "high",
            })

        # CCO — compliance-heavy industries
        if industry in ("healthcare", "pharma", "banking", "legal") and "cco" not in existing:
            proposals.append({
                "role": "cco",
                "title": "Chief Compliance Officer",
                "justification": f"Industry ({industry}) has regulatory compliance requirements",
                "priority": "high",
            })

        return proposals

    def spawn_role(self, proposal: dict) -> Role:
        """
        Create a new executive role from a proposal.
        Builds the complete Role with prompt, tools, audit scope.
        """
        role_type = RoleType.from_str(proposal["role"])
        title = proposal.get("title", f"Chief {proposal['role'].upper()} Officer")
        
        # Get default config for this role type
        defaults = _ROLE_DEFAULTS.get(role_type.value, _ROLE_DEFAULTS["custom"])

        role = Role(
            role_type=role_type,
            title=title,
            emoji=defaults["emoji"],
            domain=defaults["domain"],
            keywords=defaults["keywords"],
            tools=ToolScope(
                read_paths=defaults.get("read_paths", []),
                write_paths=defaults.get("write_paths", []),
                forbidden_paths=defaults.get("forbidden_paths", [".ava-private/"]),
                can_exec=defaults.get("can_exec", True),
                can_network=defaults.get("can_network", False),
                allowed_tools=defaults.get("allowed_tools", ["read", "write", "edit", "exec"]),
            ),
            escalation=EscalationPolicy(
                timeout_seconds=defaults.get("timeout", 300),
            ),
            audit=AuditScope(
                checks=defaults.get("audit_checks", []),
                schedule=defaults.get("audit_schedule", "0 */4 * * *"),
            ),
            system_prompt=build_executive_prompt(
                role_type=role_type.value,
                title=title,
                emoji=defaults["emoji"],
                domain=defaults["domain"],
                enterprise=self.enterprise,
                industry=self.industry,
            ),
            enterprise=self.enterprise,
        )

        self.register(role)
        return role

    def save_all(self, directory: Path) -> None:
        """Persist all roles to a directory."""
        directory.mkdir(parents=True, exist_ok=True)
        for role in self._roles.values():
            role.save(directory / f"{role.role_type.value}.json")

    def load_all(self, directory: Path) -> int:
        """Load all roles from a directory."""
        count = 0
        if not directory.exists():
            return count
        for f in directory.glob("*.json"):
            try:
                role = Role.load(f)
                self.register(role)
                count += 1
            except Exception as e:
                logger.error(f"Failed to load role from {f}: {e}")
        return count

    def to_dict(self) -> dict:
        return {
            "enterprise": self.enterprise,
            "industry": self.industry,
            "roles": {k: v.to_dict() for k, v in self._roles.items()},
        }


# ══════════════════════════════════════════════════════════════
# ROLE DEFAULTS — templates for spawning new executives
# ══════════════════════════════════════════════════════════════

_ROLE_DEFAULTS: dict[str, dict] = {
    "cto": {
        "emoji": "🔧",
        "domain": "Engineering, infrastructure, architecture, deployments, CI/CD, performance, system design, technical debt",
        "keywords": [
            "infrastructure", "deploy", "architecture", "code", "build", "CI/CD",
            "docker", "git", "performance", "database", "API", "technical",
            "engineering", "backend", "frontend", "pipeline", "server",
            "debug", "refactor", "benchmark", "container", "compile",
        ],
        "audit_checks": [
            "disk_usage", "service_status", "git_status", "port_check",
            "dependency_audit", "build_health",
        ],
        "can_network": True,
        "timeout": 600,
    },
    "coo": {
        "emoji": "📋",
        "domain": "Operations, workflows, compliance, SOPs, project tracking, resource allocation, launch planning, customer operations",
        "keywords": [
            "operations", "workflow", "SOP", "process", "compliance",
            "launch", "plan", "track", "coordinate", "documentation",
            "schedule", "resource", "milestone", "deadline", "report",
            "status", "project", "customer", "onboard", "support",
        ],
        "audit_checks": [
            "project_status", "documentation_coverage", "sop_compliance",
            "milestone_tracking",
        ],
        "timeout": 300,
    },
    "cfo": {
        "emoji": "💰",
        "domain": "Finance, budgets, revenue projections, cost analysis, pricing strategy, funding, billing, runway",
        "keywords": [
            "finance", "budget", "revenue", "cost", "pricing", "money",
            "funding", "investor", "runway", "projection", "trading",
            "profit", "loss", "expense", "ROI", "subscription",
            "payment", "billing", "invoice",
        ],
        "audit_checks": [
            "cloud_costs", "billing_status", "revenue_tracking",
        ],
        "can_network": True,
        "timeout": 300,
    },
    "ciso": {
        "emoji": "🛡️",
        "domain": "Security, GRC, vulnerability assessment, penetration testing, incident response, access control, encryption, threat modeling",
        "keywords": [
            "security", "vulnerability", "audit", "penetration", "access",
            "encryption", "threat", "risk", "compliance", "incident",
            "firewall", "authentication", "authorization", "SSL",
            "certificate", "credential", "breach", "qorvex", "privacy",
        ],
        "audit_checks": [
            "failed_logins", "listening_ports", "file_permissions",
            "credential_exposure", "ssl_expiry",
        ],
        "can_network": True,
        "timeout": 300,
    },
    "cro": {
        "emoji": "⚖️",
        "domain": "Risk management, regulatory compliance, market risk, operational risk, credit risk, risk modeling",
        "keywords": [
            "risk", "regulatory", "compliance", "audit", "exposure",
            "hedging", "VaR", "stress test", "counterparty", "market risk",
            "operational risk", "credit risk", "liquidity",
        ],
        "audit_checks": ["risk_register", "exposure_report", "regulatory_status"],
        "timeout": 300,
    },
    "cpo": {
        "emoji": "🎯",
        "domain": "Product strategy, roadmap, user research, feature prioritization, product metrics, competitive analysis",
        "keywords": [
            "product", "roadmap", "feature", "user", "research",
            "prioritize", "metric", "competitor", "MVP", "backlog",
            "sprint", "release", "beta", "launch", "adoption",
        ],
        "audit_checks": ["product_metrics", "roadmap_status", "user_feedback"],
        "timeout": 180,
    },
    "cmo": {
        "emoji": "📣",
        "domain": "Marketing, brand, growth, campaigns, social media, content strategy, market positioning",
        "keywords": [
            "marketing", "brand", "growth", "campaign", "social media",
            "content", "SEO", "advertising", "audience", "engagement",
            "conversion", "funnel", "awareness", "positioning",
        ],
        "audit_checks": ["social_metrics", "campaign_performance", "brand_monitoring"],
        "timeout": 300,
    },
    "cdo": {
        "emoji": "📊",
        "domain": "Data strategy, data pipelines, analytics, data governance, ML/AI infrastructure, data quality",
        "keywords": [
            "data", "analytics", "pipeline", "ETL", "warehouse",
            "governance", "quality", "ML", "AI", "model",
            "dataset", "schema", "migration", "visualization",
        ],
        "audit_checks": ["pipeline_health", "data_quality", "model_performance"],
        "can_network": True,
        "timeout": 300,
    },
    "cco": {
        "emoji": "📜",
        "domain": "Regulatory compliance, legal, policy, licensing, audit readiness, standards adherence",
        "keywords": [
            "compliance", "regulation", "legal", "policy", "license",
            "GDPR", "HIPAA", "SOX", "ISO", "audit", "standard",
            "governance", "ethics", "privacy",
        ],
        "audit_checks": ["compliance_status", "policy_review", "license_audit"],
        "timeout": 180,
    },
    "custom": {
        "emoji": "👤",
        "domain": "Custom domain — to be defined",
        "keywords": [],
        "audit_checks": [],
        "timeout": 180,
    },
}


# Module-level cached roles for match_roles (built once, reused)
_CACHED_MATCH_ROLES: list[Role] | None = None


def _get_match_roles() -> list[Role]:
    """Get cached Role objects for keyword matching (avoid rebuilding every call)."""
    global _CACHED_MATCH_ROLES
    if _CACHED_MATCH_ROLES is None:
        roles = []
        for rt_name, defaults in _ROLE_DEFAULTS.items():
            if rt_name == "custom":
                continue
            try:
                rt = RoleType(rt_name)
                role = Role(
                    role_type=rt,
                    title=defaults.get("title", f"C{rt_name[1:].upper()}O"),
                    emoji=defaults["emoji"],
                    domain=defaults["domain"],
                    keywords=defaults.get("keywords", []),
                )
                roles.append(role)
            except (ValueError, KeyError) as e:
                logger.debug(f"Suppressed (ValueError, KeyError): {e}")
                continue
        _CACHED_MATCH_ROLES = roles
    return _CACHED_MATCH_ROLES


def match_roles(task: str, threshold: float = 0.05) -> list[tuple[Role, float]]:
    """Match a task description to roles by keyword relevance. Cached for performance."""
    roles = _get_match_roles()
    matches = []
    task_lower = task.lower()
    for role in roles:
        if not role.keywords:
            continue
        hits = sum(1 for kw in role.keywords if kw.lower() in task_lower)
        score = min(hits / len(role.keywords), 1.0)
        if score >= threshold:
            matches.append((role, score))
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches
