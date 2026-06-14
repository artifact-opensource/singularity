# Singularity [AE] — Architecture Reference

> **Autonomous Enterprise Runtime**  
> _Not a chatbot. An operating system for organizations._

---

## Table of Contents

1. [Overview](#overview)
2. [System Topology](#system-topology)
3. [Event Bus](#event-bus)
4. [Subsystems](#subsystems)
   - [CORTEX — Brain](#cortex--brain)
   - [NERVE — Communications](#nerve--communications)
   - [MARROW — Memory](#marrow--memory)
   - [VOICE — LLM Providers](#voice--llm-providers)
   - [SINEW — Tool Execution](#sinew--tool-execution)
   - [IMMUNE — Health & Recovery](#immune--health--recovery)
   - [PULSE — Scheduler](#pulse--scheduler)
   - [SPINE — Configuration](#spine--configuration)
   - [AUDITOR — Workspace Intelligence](#auditor--workspace-intelligence)
   - [CLI — Command Interface](#cli--command-interface)
5. [C-Suite Layer](#c-suite-layer)
   - [Executive Lifecycle](#executive-lifecycle)
   - [Coordinator](#coordinator)
   - [Self-Heal Engine](#self-heal-engine)
   - [Dispatch Flow](#dispatch-flow)
6. [POA Layer](#poa-layer)
   - [Product Owner Agents](#product-owner-agents)
   - [Release Manager](#release-manager)
7. [ATLAS — Enterprise Topology](#atlas--enterprise-topology)
   - [Discovery Engine](#discovery-engine)
   - [Topology Graph](#topology-graph)
   - [Coach Engine](#coach-engine)
   - [Board Reporter](#board-reporter)
8. [NEXUS — Self-Optimization](#nexus--self-optimization)
   - [Code Analyzer](#code-analyzer)
   - [Hot-Swap Engine](#hot-swap-engine)
   - [Evolution Engine](#evolution-engine)
9. [ExfilGuard Integration](#exfilguard-integration)
10. [Data Flow Diagrams](#data-flow-diagrams)
11. [File Layout](#file-layout)
12. [Design Principles](#design-principles)

---

## Overview

Singularity is a **self-scaling autonomous enterprise runtime**. It deploys AI executive agents, monitors live products, heals degraded systems, and evolves its own codebase — from a solo founder environment to a multinational.

**13 subsystems.** All communicate through a central async event bus. Any component can fail independently. The system heals faster than it degrades.

```
                          ┌────────────────────────────────────┐
                          │        SINGULARITY RUNTIME         │
                          │                                    │
  CLI / Discord ──────▶   │  NERVE → CORTEX → SINEW → VOICE   │
  Cron / PULSE ──────▶   │       │         │                  │
  Inbox files ──────▶    │       └── EVENT BUS ────────────── │
                          │             │                      │
                          │    IMMUNE / PULSE / MARROW / SPINE │
                          │             │                      │
                          │   C-SUITE   │   POA   │   ATLAS   │
                          │             │         │           │
                          │            NEXUS                  │
                          └────────────────────────────────────┘
```

---

## System Topology

```
singularity/
├── bus.py                   # Async pub/sub event bus
├── config.py                # SPINE — hot-reload configuration
├── runtime.py               # Boot sequence, main loop, inbox poll
│
├── cortex/                  # 🧠 CORTEX — Agent loop
├── nerve/                   # 🔌 NERVE — Channel adapters
├── memory/                  # 🦴 MARROW — Persistence
├── voice/                   # 🗣️ VOICE — LLM providers
├── sinew/                   # 💪 SINEW — Tool execution
├── immune/                  # 🛡️ IMMUNE — Health & recovery
├── pulse/                   # 💓 PULSE — Scheduler
├── csuite/                  # 👔 C-SUITE — Executive agents
├── poa/                     # 📋 POA — Product owner agents
├── atlas/                   # 🗺️ ATLAS — Enterprise topology
├── nexus/                   # 🔁 NEXUS — Self-optimization
├── auditor/                 # 🔍 AUDITOR — Workspace intelligence
└── cli/                     # 🖥️ CLI — Command-line interface
```

---

## Event Bus

**File:** `singularity/bus.py`

The central nervous system of Singularity. Every subsystem communicates exclusively through async pub/sub — no direct imports between components at runtime.

### Key Properties
- Wildcard subscriptions (`atlas.*`, `csuite.*`)
- Emission history with configurable depth
- Per-subscriber error isolation (one bad handler never kills the bus)
- Async-native — `asyncio` queue-backed

### Event Namespaces

| Namespace | Source | Examples |
|-----------|--------|---------|
| `atlas.*` | ATLAS | `atlas.cycle.complete`, `atlas.alert`, `atlas.module.discovered` |
| `csuite.*` | C-Suite | `csuite.dispatch.started`, `csuite.task.completed`, `csuite.escalation` |
| `nexus.*` | NEXUS | `nexus.cycle.started`, `nexus.cycle.completed`, `nexus.rollback.all` |
| `health.*` | IMMUNE | `health.degraded`, `health.recovered` |
| `poa.*` | POA | `poa.audit.complete`, `poa.alert` |
| `config.*` | SPINE | `config.loaded`, `config.changed` |

### Cascade Example

```
health.degraded
  → IMMUNE emits "health.degraded"
    → PULSE reschedules check interval (increase frequency)
      → SINEW executes restart command
        → NERVE sends Discord alert
          → CORTEX logs the incident to MARROW
```

One signal. Butterfly effects. Managed cascade.

---

## Subsystems

### CORTEX — Brain

**Files:** `singularity/cortex/`

The agent loop. Think → Act → Observe. Not just LLM-call-repeat — a stateful loop with context assembly, tool dispatch, and PULSE budget management.

#### Agent Loop
```python
for iteration in range(max_iterations):
    response = await voice.chat(messages, tools=scoped_tools)
    if response.tool_calls:
        results = await sinew.execute_all(response.tool_calls)
        messages.extend(results)
    else:
        break  # Final text response — done
```

#### Context Assembly
- System prompt from role + COMB recall
- History truncation at token window
- Auto-compaction detection (triggers MARROW summary)

#### BLINK Continuation
When PULSE budget nears exhaustion, BLINK auto-extends the budget (20 → 100 iterations) for complex tasks. Transparent to the user.

---

### NERVE — Communications

**Files:** `singularity/nerve/`

Platform-agnostic channel layer. Every surface (Discord, HTTP, webhooks) speaks the same internal `BusEnvelope` format.

#### Adapters
| Adapter | File | Protocol |
|---------|------|---------|
| Discord | `discord.py` | Gateway v10, reconnect with backoff |
| HTTP API | `http_api.py` | REST — used by CLI and inbox polling |
| Formatter | `formatter.py` | Platform-aware markdown conversion |

#### Message Router
`router.py` — inbound routing with:
- Rate limiting per channel
- Sibling-bot yield (avoids AVA/Aria loops)
- Policy enforcement (which channels are read vs. write-only)

#### Deployer
`deployer.py` — manages Discord bot deployment state. Tracks active deployments in `.singularity/deployments/`.

---

### MARROW — Memory

**Files:** `singularity/memory/`

COMB-native persistence. Every session, every tool result, every key decision flows through COMB.

| Component | File | Purpose |
|-----------|------|---------|
| Sessions | `sessions.py` | Create, load, archive sessions with token tracking |
| COMB Bridge | `comb.py` | `stage` (save) / `recall` (load) / `rollup` (compact) |
| HEKTOR | `hektor.py` | Sub-millisecond vector search for memory retrieval |

**Wake-up protocol:** On every boot, CORTEX calls `comb_recall` before any substantive work. The runtime never starts blind.

---

### VOICE — LLM Providers

**Files:** `singularity/voice/`

Provider chain with automatic fallback. The brain's connection to language — not the brain itself.

```
Primary: HuggingFace (router.huggingface.co — OpenAI-compatible, 120+ models)
    ↓ (3 failures → circuit open)
Fallback: GitHub Copilot Proxy (localhost)
    ↓ (3 failures → circuit open)
Local: Ollama (qorvex mode — zero external deps)
    ↓ (all fail)
Degraded mode: structured error response
```

#### Circuit Breaker
Each provider tracks failures. After 3 consecutive failures, the circuit opens and requests route to the next provider. The circuit resets after a configurable cooldown.

#### Streaming
SSE streaming supported on Copilot proxy and HuggingFace. Ollama uses the native streaming API.

---

### SINEW — Tool Execution

**Files:** `singularity/sinew/`

Sandboxed tool runner with schema validation, permission scoping, and timeout enforcement.

#### Built-in Tools

| Tool | Description | Scope |
|------|-------------|-------|
| `read` | Read file contents | All roles |
| `write` | Write/create files | CTO, COO, selected |
| `edit` | Targeted find/replace | CTO, COO, selected |
| `exec` | Shell command execution | CTO, CISO, selected |
| `web_fetch` | HTTP GET requests | All roles |
| `search` | HEKTOR hybrid search | All roles |
| `spawn` | Spawn sub-agent | CORTEX only |

#### Safety Guarantees
- Every `exec` has a configurable timeout (default: 30s per role)
- Output capped at configurable byte limit (prevents runaway tools)
- Path permission checking per role (`allows_path()`)
- `.env` files and credential paths blocked at sandbox level

---

### IMMUNE — Health & Recovery

**Files:** `singularity/immune/`

Self-healing at every grain. Not "restart the service" — structured detection, classification, and recovery.

#### Components

| Component | File | What It Does |
|-----------|------|-------------|
| Watchdog | `watchdog.py` | Monitors subsystem health events, coordinates failover |
| Health | `health.py` | Periodic health check orchestrator |
| Vitals | `vitals.py` | System vitals (disk, memory, CPU load, uptime) |
| Auditor | `auditor.py` | Configurable audit loop with channel alerting |
| Reflector | `reflector.py` | Feedback loop — health findings into ATLAS |
| Feedback | `feedback.py` | Structured health feedback format |

#### Health Check Flow
```
IMMUNE.health_check() → collect vitals
  → disk > 90% → emit health.degraded
    → Watchdog receives → schedules cleanup task
      → SINEW executes cleanup → emits health.recovered
```

---

### PULSE — Scheduler

**Files:** `singularity/pulse/`

Cron + event triggers + iteration budget management.

#### Scheduler (`scheduler.py`)
- Cron expressions (standard 5-field)
- Named one-shot timers
- Event-driven triggers ("when X, do Y")

#### Budget Manager (`budget.py`)
- Per-agent iteration tracking
- Auto-expansion trigger at 80% budget consumption
- Hard cap enforcement (prevents runaway loops)

#### POA Audit Schedule (Default)

| Org Tier | Audit Interval |
|----------|---------------|
| Solo | Daily |
| Startup | Every 6h |
| SMB | Every 4h |
| Enterprise | Every 2h |

---

### SPINE — Configuration

**File:** `singularity/config.py`

Hot-reload YAML/JSON configuration. Layered priority:

```
CLI arguments
    ↓ (highest)
Environment variables (SINGULARITY_{SECTION}_{KEY})
    ↓
config/singularity.yaml
    ↓ (lowest)
Defaults
```

Change any layer → system adapts. No restart required for most config keys. Emits `config.changed` on the bus when values update.

---

## C-Suite Layer

**Files:** `singularity/csuite/`

Executive agents with scoped access. Industry-specific roles. The organizational intelligence layer.

### Executive Roles

| Role | File key | Domain | Tools |
|------|----------|--------|-------|
| CTO | `cto` | Engineering, infrastructure, code | read, write, edit, exec, web_fetch |
| COO | `coo` | Operations, process, compliance | read, write, exec |
| CFO | `cfo` | Finance, budgets, pricing | read, write, web_fetch |
| CISO | `ciso` | Security, risk, vulnerabilities | read, exec, web_fetch |

Additional roles (industry-specific):
- CRO (Risk) — Fintech/Banking
- CCO (Compliance) — Healthcare/Pharma
- CPO (Product) — SaaS/Platform
- CDO (Data) — AI/ML, Healthcare
- CMO (Marketing) — E-Commerce, SaaS

### Executive Lifecycle

```
PROPOSED ──▶ APPROVED ──▶ ACTIVE ──▶ RUNNING TASK
                              │               │
                              ◀── IDLE ◀──────┘
                              │
                              ▼
                           RETIRED
```

Each executive is **ephemeral** — spawned on demand, terminated after delivering results. No persistent processes. State is the task queue.

### Coordinator

**File:** `singularity/csuite/coordinator.py`

Pure orchestration logic. No LLM loop of its own.

```
Coordinator.dispatch(description, target, priority)
  → _resolve_targets()     # keyword match or direct name
  → _run_task(exec, task)  # asyncio.gather() for multi-exec
  → _save_dispatch()       # persist to .singularity/csuite/dispatches/
  → _webhook_reporter()    # post to Discord channels
  → return DispatchResult
```

**Target resolution:** if `target="auto"`, keyword matching against all executive role keyword lists. If multiple roles match, fan-out dispatches to all.

### Self-Heal Engine

**File:** `singularity/csuite/self_heal.py`

Autonomous failure classification and healing. Wired to the event bus — listens for `csuite.task.completed` events where status ≠ `complete`.

#### Healing Strategies

| Strategy | Trigger | Action |
|----------|---------|--------|
| `RETRY` | Rate limit, network blip, timeout | Re-dispatch with exponential backoff (2s → 5s → 15s) |
| `REROUTE` | Auth failure, quota exhausted, model unavailable | Rotate provider chain, re-dispatch |
| `EXPAND` | Iteration cap hit | Increase max_iterations (up to 50), re-dispatch |
| `PATCH` | ImportError, AttributeError, code bugs | Dispatch repair task to CTO, hot-reload fixed module |
| `ESCALATE` | All strategies exhausted, circuit breaker open | Alert #bridge, write post-mortem |

#### Circuit Breaker
5 failures in 5 minutes → circuit opens for 60s. Prevents cascade loops where heal→retry→fail→heal→retry loops consume all resources.

#### Reroute Cooldown
After a reroute dispatch, a 120s cooldown prevents the same pattern from triggering again immediately. Breaks the `timeout → reroute → timeout → reroute` cascade.

### Dispatch Flow

Complete end-to-end pipeline for a single dispatch:

```
CLI / AVA / Cron
      │
      ▼
.singularity/csuite/inbox/<request_id>.json
      │  (2s poll — runtime._poll_dispatch_inbox)
      ▼
Dispatcher.dispatch_to(target, description, priority)
      │
      ▼
Coordinator.dispatch()
  1. Generate dispatch_id
  2. Emit "csuite.dispatch.started"
  3. _resolve_targets() — keyword match
  4. Create Task objects
  5. Execute (single: direct, multiple: asyncio.gather)
  6. Collect TaskResults
  7. _save_dispatch() → .singularity/csuite/dispatches/
  8. WebhookReporter → Discord channels
  9. Emit "csuite.dispatch.completed"
      │
      ▼
Executive.execute(task)
  1. Build scoped system prompt
  2. Agent loop (max 8 iterations default):
     a. LLM call with scoped tool defs
     b. If tool_calls → execute with permission guard
     c. If text only → break (done)
     d. If last iteration → inject "summarize now" + remove tools
  3. Extract findings from response
  4. Return TaskResult
      │
      ▼
Results → .singularity/csuite/results/<request_id>.json
Discord → #cto | #coo | #cfo | #ciso | #dispatch
Archive → .singularity/csuite/dispatches/<timestamp>-<dispatch_id>.json
```

#### Timing Reference (Real CISO dispatch, 2026-03-04)

| Step | Duration |
|------|----------|
| Inbox pickup | < 2s |
| LLM iteration (tool call) | ~2–5s |
| LLM iteration (final report, 415 tokens) | ~10s |
| Webhook posting | ~2s |
| Dispatch archive | < 0.1s |
| **Total (5 iterations)** | **22.1s** |

---

## POA Layer

**Files:** `singularity/poa/`

Product Owner Agents — persistent monitors for live products.

### Product Owner Agents

**File:** `singularity/poa/manager.py`

#### POA Lifecycle

```
PROPOSED ──▶ APPROVED ──▶ ACTIVE ──▶ PAUSED
                              │
                              ▼
                           RETIRED
```

Each POA owns one product and runs these checks on schedule:

| Check | What It Monitors |
|-------|-----------------|
| Endpoints | HTTP status, latency, response body validation |
| SSL | Certificate expiry, issuer, chain validity |
| Service | systemd/Docker status, uptime, restart count |
| Disk | Usage %, free space against threshold |
| Memory | System memory pressure |
| Logs | Journal errors, critical log entries |
| Nginx | Error log entries, config validity |

Results → structured JSON + Markdown in `.singularity/audits/`.

Severity classification: `GREEN` (all pass) → `YELLOW` (warnings) → `RED` (failures) → escalation to Discord `#dispatch`.

### Release Manager

**File:** `singularity/poa/release.py`

Autonomous GitHub release pipeline. Triggered by PULSE every 4h.

#### Flow

```
PULSE (every 4h)
  → ReleaseManager.scan_all()
    → Per repo: git log <last_tag>..HEAD
      → classify_commit() per commit (conventional commits)
        → determine bump_type (major/minor/patch)
          → generate_changelog()
            → ReleaseProposal (status: pending)
              → Singularity reviews → confirms
                → ship():
                  1. git tag -a <version>
                  2. git push origin <version>
                  3. gh release create <version>
                  → proposal.status = "shipped"
                  → archive to history/
```

#### Version Bump Rules (Conventional Commits)

| Commit type | Bump |
|-------------|------|
| `BREAKING CHANGE` or `feat!:` | major |
| `feat:` | minor |
| `fix:`, `perf:`, `docs:`, `chore:` | patch |

---

## ATLAS — Enterprise Topology

**Files:** `singularity/atlas/`

Auto-discovery and health monitoring of the entire enterprise. No manual registration. If it exists, ATLAS finds it.

### Discovery Engine

**File:** `singularity/atlas/discovery.py`

Scans continuously for modules via:
- `systemd` unit files (user + system services)
- `ss -tlnp` — listening ports
- nginx `sites-enabled/` — backend mapping
- Cloudflare tunnel config — public hostnames
- Process table — resource usage
- Remote machines — SSH probe
- Known filesystem paths (`KNOWN_MODULES` registry)

### Topology Graph

**File:** `singularity/atlas/topology.py`

#### Module Types

| Type | Examples |
|------|---------|
| `AGENT` | Singularity, AVA, Aria |
| `GATEWAY` | Mach6 Gateway, Copilot Proxy |
| `SERVICE` | COMB Cloud, ERP, GDI |
| `DAEMON` | HEKTOR, Sentinel |
| `INFRASTRUCTURE` | Nginx, PostgreSQL, Ollama, Cloudflared |
| `SUPPORT` | PULSE, NEXUS, Event Bus |

#### Module Status FSM

```
UNKNOWN → HEALTHY → DEGRADED → DOWN → STALE → GONE
           │                              │
           └──────────── HEALTHY ◀────────┘ (revive on rediscovery)
```

#### Edge Types

| Type | Meaning |
|------|---------|
| `DEPENDS_ON` | Hard dependency (ERP → PostgreSQL) |
| `PROXIES_TO` | Nginx → backend service |
| `FEEDS_DATA` | MT5 → Cthulu webhook |
| `SHARES_RESOURCE` | Multiple services → Copilot Proxy |
| `MONITORS` | Sentinel → everything |

#### Visibility Index

Modules can be **hidden** from board reports and topology views without stopping discovery/monitoring. Used for confidential products (trading systems, internal tools). Hidden modules are still health-checked — they're just excluded from output.

```python
atlas.set_visibility("gdi-trading", visible=False)
# GDI is still monitored but doesn't appear in reports
```

### Coach Engine

**File:** `singularity/atlas/coach.py`

Evaluates all active modules across 6 fitness dimensions:

| Dimension | What It Checks |
|-----------|---------------|
| Health | Process alive, health endpoint responding |
| Performance | RAM %, swap %, CPU load vs. threshold |
| Security | Ports bound to 0.0.0.0, world-readable credential files |
| Configuration | Missing env vars, config drift, conflicts |
| Freshness | Log activity, git staleness, deploy recency |
| Capacity | Disk/RAM projection — days until exhaustion |

Auto-remediates safe issues (log rotation, temp cleanup). Escalates everything else to ATLAS alerts.

#### Issue Severity

| Severity | Meaning | Auto-Fix |
|----------|---------|---------|
| CRITICAL | Service down, cascade risk | Never |
| HIGH | Security exposure, resource exhaustion imminent | Never |
| MEDIUM | Performance degradation, config drift | Sometimes |
| LOW | Hygiene — log rotation, stale git | Yes |
| INFO | New module found, topology change | N/A |

### Board Reporter

**File:** `singularity/atlas/board.py`

Generates enterprise-wide board reports. Scheduled every 6h via PULSE. Also on-demand.

Report sections:
1. **Executive Summary** — module counts by status, critical issue count
2. **Topology Map** — ASCII art showing module relationships
3. **Issues** — grouped by severity with affected module and recommended action
4. **Host Resources** — disk, memory, load per machine
5. **Auto-Actions Taken** — what the Coach fixed automatically

### ATLAS Cycle

```
Atlas.run_cycle()
  1. DiscoveryEngine.run_full_scan()
     → discover_modules() + collect_host_resources()
  2. TopologyGraph.upsert_module() per discovered module
     → mark new modules, emit "atlas.module.discovered"
  3. TopologyGraph.mark_missed() for absent modules
     → STALE after 3 cycles, GONE after 10
  4. CoachEngine.evaluate()
     → 6-dimension fitness check per active module
  5. ActionExecutor.execute_safe_fixes(issues)
     → auto-remediate LOW severity issues
  6. TopologyGraph.save() — persist state
  7. BoardReporter generates report
  8. Emit "atlas.cycle.complete" + "atlas.alert" (if critical issues)
```

---

## NEXUS — Self-Optimization

**Files:** `singularity/nexus/`

The self-improvement engine. Singularity reads its own code, finds anti-patterns, generates fixes, validates them, and applies them — live, with rollback capability.

### Modes

| Mode | What It Does |
|------|-------------|
| `audit` | Scan code, report findings only |
| `propose` | Audit + generate concrete proposals with diffs |
| `optimize` | Propose + auto-apply HIGH/CERTAIN confidence proposals |
| `report` | Full optimization report for human review |

### Code Analyzer

**File:** `singularity/nexus/analyzer.py`

AST-based static analysis. Scans for:
- Silent exceptions (`except: pass`)
- Missing error logging
- Dead imports
- Type safety gaps in critical paths
- Redundant code patterns

Reports findings with severity (CRITICAL / HIGH / MEDIUM / LOW) and affected file/function.

### Hot-Swap Engine

**File:** `singularity/nexus/hotswap.py`

Runtime function replacement with full rollback.

```
1. Capture original function object from module namespace
2. Store in rollback journal (memory + disk backup)
3. Replace function in module.__dict__
4. Run validation (health check or test function)
5. If validation fails → automatic rollback
6. Emit "nexus.hotswap.applied" bus event
```

#### Safety Guarantees
- Every swap has a journal entry with original function source
- `rollback(swap_id)` restores original instantly
- `rollback_all()` restores everything to pre-NEXUS state
- On-disk journal survives process crashes
- NEVER swaps `__init__`, `__del__`, or dunder methods
- NEVER swaps functions in the `nexus` module itself (no self-modifying the self-modifier)

### Evolution Engine

**File:** `singularity/nexus/evolve.py`

Pattern-matched mechanical code transformations. Targets safe, verifiable changes only:

| Evolution | Pattern | Action |
|-----------|---------|--------|
| Exception Visibility | `except Exception: pass` | → `except Exception as e: logger.debug(f"Suppressed: {e}")` |
| Bare Except | `except:` | → `except Exception:` |
| Async Guard | Missing cleanup in async generators | Add `try/finally` guard |
| Dead Import | Unused imports | Remove after AST verification |

Each evolution is:
1. Validated by AST parsing before application
2. Applied via hot-swap (live in memory)
3. Persisted to disk (survives restart)
4. Journaled for rollback
5. Verified by re-scanning after application

---

## ExfilGuard Integration

ExfilGuard is the credential and data exfiltration prevention layer, integrated directly into SINEW's sandbox and the CISO executive's tool scope.

### SINEW Sandbox (`singularity/sinew/sandbox_exec.py`)

The sandbox enforces these rules at execution time:

| Rule | Enforcement |
|------|------------|
| `.env` file access | Blocked — path match against `.env`, `.env.*`, `*.key`, `*.pem` |
| Credential patterns | Regex scan on tool arguments before execution |
| Shell injection | Command argument validation — no `;`, `&&`, `\|` chaining outside `exec` |
| Self-modification guard | No writes to `singularity/nexus/` by non-NEXUS tools |
| Output scrubbing | API keys, tokens, passwords removed from tool output before LLM sees them |

### CISO Auto-Dispatch

**Trigger:** ATLAS coach emits a `HIGH` or `CRITICAL` security-category issue.

```
atlas.alert (security issue)
  → bus subscriber in runtime.py
    → csuite_dispatch(target="ciso", description=issue_detail, priority="critical")
      → CISO executive runs security audit
        → findings posted to #ciso Discord channel
          → DispatchResult archived
```

This creates a feedback loop: ATLAS discovers a security exposure → CISO investigates → CISO report feeds back into ATLAS topology notes for the next cycle.

### Credential Isolation

- `.env` is in `.gitignore` — never committed
- `config/singularity.example.yaml` contains only placeholder values
- Secrets vault (`singularity/auditor/`) uses Fernet (AES-128-CBC) for at-rest encryption
- LLM provider chains never receive workspace secrets — only API authentication tokens

---

## Data Flow Diagrams

### Inbound Message → Response

```
Discord message
  → NERVE.discord.on_message()
    → InboundRouter.route() (policy check, rate limit, bot yield)
      → bus.emit("message.received", envelope)
        → CORTEX.process(envelope)
          → MARROW.comb_recall() (boot context)
            → VOICE.chat(messages, tools)
              → SINEW.execute(tool_calls)
                → messages.append(results)
                  → VOICE.chat(messages) → final response
                    → NERVE.send(channel, response)
                      → MARROW.comb_stage(session)
```

### Health Degradation → Recovery

```
IMMUNE.vitals.collect()
  → disk_pct > 90
    → bus.emit("health.degraded", {subsystem: "disk", value: 92})
      → Watchdog._on_health_event()
        → SINEW.exec("find /tmp -mtime +7 -delete")
          → bus.emit("health.recovered", {subsystem: "disk", value: 71})
            → NERVE.send("#dispatch", "✅ Disk cleanup complete: 92% → 71%")
```

### NEXUS Self-Evolution

```
PULSE (weekly cron)
  → nexus.evolve(target="sinew/")
    → EvolutionEngine.scan_patterns()
      → find: except Exception: pass  (3 instances)
        → generate replacement code (AST-validated)
          → HotSwap.apply(module, function, new_code)
            → validate (re-scan → no findings for this pattern)
              → persist to disk
                → journal entry
                  → bus.emit("nexus.evolution.applied", {count: 3})
```

---

## File Layout

```
singularity/
├── singularity/                # Runtime package
│   ├── bus.py                  # Event bus
│   ├── config.py               # SPINE configuration
│   ├── runtime.py              # Boot + main loop
│   │
│   ├── cortex/
│   │   ├── agent.py            # Agent loop (Think→Act→Observe)
│   │   ├── blink.py            # Budget continuation
│   │   ├── context.py          # Context assembly + compaction
│   │   └── engine.py           # Cortex orchestrator
│   │
│   ├── nerve/
│   │   ├── adapter.py          # Abstract channel adapter
│   │   ├── deployer.py         # Bot deployment manager
│   │   ├── discord.py          # Discord gateway v10
│   │   ├── formatter.py        # Platform-aware formatting
│   │   ├── http_api.py         # REST API adapter
│   │   ├── presence.py         # Online/status management
│   │   ├── router.py           # Inbound routing + policy
│   │   └── types.py            # Message types + channel state
│   │
│   ├── memory/
│   │   ├── comb.py             # COMB bridge (stage/recall/rollup)
│   │   ├── hektor.py           # HEKTOR vector search integration
│   │   ├── sessions.py         # Session management + SQLite
│   │   └── __init__.py
│   │
│   ├── voice/
│   │   ├── chain.py            # Provider cascade + circuit breakers
│   │   ├── huggingface.py      # HuggingFace Inference API (primary — router.huggingface.co)
│   │   ├── ollama.py           # Local Ollama (qorvex mode)
│   │   ├── provider.py         # Abstract provider + ChatMessage types
│   │   └── proxy.py            # GitHub Copilot proxy
│   │
│   ├── sinew/
│   │   ├── changeset.py        # File changeset tracking
│   │   ├── definitions.py      # Tool schemas (OpenAI function format)
│   │   ├── executor.py         # Sandboxed tool runner
│   │   ├── sandbox.py          # Safety + permission enforcement
│   │   └── sandbox_exec.py     # ExfilGuard execution sandbox
│   │
│   ├── immune/
│   │   ├── auditor.py          # Audit loop + alerting
│   │   ├── feedback.py         # Structured health feedback
│   │   ├── health.py           # Health check orchestrator
│   │   ├── reflector.py        # ATLAS feedback loop
│   │   ├── vitals.py           # System vitals collection
│   │   └── watchdog.py         # Process watchdog + failover
│   │
│   ├── pulse/
│   │   ├── budget.py           # Iteration budget manager
│   │   ├── health.py           # PULSE health monitor
│   │   ├── scheduler.py        # Cron + timers + triggers
│   │   └── __init__.py
│   │
│   ├── csuite/
│   │   ├── coordinator.py      # Dispatch orchestration
│   │   ├── dispatch.py         # High-level dispatch API
│   │   ├── executive.py        # Executive agent loop
│   │   ├── reports.py          # Structured report format
│   │   ├── roles.py            # Role registry + permissions
│   │   ├── self_heal.py        # Autonomous failure recovery
│   │   └── webhooks.py         # Discord webhook reporter
│   │
│   ├── poa/
│   │   ├── manager.py          # POA lifecycle management
│   │   ├── release.py          # Release Manager pipeline
│   │   ├── runtime.py          # Audit execution + monitoring
│   │   └── setup.py            # POA provisioning
│   │
│   ├── atlas/
│   │   ├── actions.py          # Auto-fix action executor
│   │   ├── board.py            # Board report generator
│   │   ├── coach.py            # 6-dimension fitness evaluator
│   │   ├── discovery.py        # Multi-source module discovery
│   │   ├── manager.py          # ATLAS orchestrator (run_cycle)
│   │   └── topology.py         # Graph data models + FSM
│   │
│   ├── nexus/
│   │   ├── analyzer.py         # AST-based code analysis
│   │   ├── applicator.py       # Proposal application engine
│   │   ├── daemon.py           # NEXUS background daemon
│   │   ├── engine.py           # NexusEngine (audit/propose/optimize)
│   │   ├── evolve.py           # Evolution Engine (pattern transforms)
│   │   ├── hotswap.py          # Hot-swap + rollback journal
│   │   └── proposals.py        # Proposal generator + confidence scoring
│   │
│   └── auditor/
│       ├── analyzer.py         # Workspace maturity scoring
│       ├── report.py           # JSON + Markdown report generation
│       ├── scanner.py          # Filesystem + git analysis
│       ├── templates.py        # Industry-specific templates
│       └── __init__.py
│
│   ├── cli/
│   │   ├── main.py             # CLI entry point + command registry
│   │   ├── formatters.py       # Output formatters
│   │   ├── wizard.py           # Interactive setup wizard
│   │   └── __init__.py
│
├── config/
│   ├── singularity.yaml        # Active config (gitignored)
│   └── singularity.example.yaml
│
├── docs/
│   └── ARCHITECTURE.md         # This document
│
├── scripts/
│   ├── deploy_guild.py         # Discord guild deployment
│   ├── dispatch.py             # CLI dispatch (drops inbox JSON)
│   ├── fresh_install.py        # First-time setup
│   ├── redeploy_guild.py       # Re-deploy existing guild
│   └── stress_test.py          # Load testing
│
├── tests/
│   ├── test_e2e.py             # 30 end-to-end tests (all subsystems)
│   ├── test_deployer_live.py   # Live deployer tests
│   └── test_hektor.py          # HEKTOR memory tests
│
├── .singularity/               # Runtime state (gitignored)
│   ├── audits/                 # POA audit reports
│   ├── csuite/                 # C-Suite dispatches, results, inbox
│   ├── deployments/            # Discord deployment state
│   └── nexus/                  # NEXUS optimization results
│
└── .core/                      # Operational data
    ├── AGENTS.md               # Operating protocol
    ├── IDENTITY.md             # Runtime identity
    ├── SOUL.md                 # Core character
    └── profiles/               # Agent identity profiles
```

---

## Design Principles

### 1. Heal Faster Than You Degrade
The Turing Problem is real — everything degrades. Software rots. Services crash. Entropy wins unless you build immune systems that heal faster than things break. Singularity doesn't prevent failure. It recovers before anyone notices.

### 2. Event-Driven, Not Request-Response
No direct inter-subsystem imports at runtime. Everything communicates through the event bus. Loose coupling means any component can fail without killing the others.

### 3. Memory-Native
COMB isn't a library call. It's the bloodstream. Every interaction persists. Every context window has history. The runtime wakes up knowing what it is.

### 4. Single Trigger → Butterfly Effects
One event cascades through the entire system. A health check failure triggers an alert, a restart, a status update, and a report — all from one bus emission.

### 5. Approval Gates, Not Automation Gates
Monitoring is autonomous. Mutation is gated. Every executive spawn, every POA deployment, every production action requires explicit human approval. Singularity proposes. You decide. Always.

### 6. Zero Vendor Lock-In
No OpenAI dependency. No Anthropic dependency. No cloud dependency. The provider chain falls through automatically: cloud → proxy → local. Your enterprise doesn't stop because a vendor has an outage.

### 7. Roles Follow the Workspace
Singularity doesn't impose org structure. It discovers what you have and proposes what you need. A fintech company gets a CRO. A healthcare company gets a CCO. A solo founder gets minimal overhead. The workspace is the truth.

---

*Architecture Reference — Singularity [AE] v0.2.0*  
*Artifact Virtual · Built by Ali Shakil & AVA · 2026*
