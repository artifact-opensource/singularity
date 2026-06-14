# Changelog

All notable changes to Singularity [AE] will be documented in this file.

## [0.1.0] — 2026-03-03

### 🎉 Initial Release — "Genesis"

The first release of Singularity, the Autonomous Enterprise Runtime.

**10 subsystems, event-bus architecture, built from ground up in 19 days.**

### Added

#### Core Runtime
- **Event Bus** — async pub/sub backbone with wildcard subscriptions, emission history, and error isolation
- **SPINE** — hot-reload YAML/JSON configuration with environment variable overrides and change notification
- **Runtime** — boot sequence, main loop, graceful shutdown

#### Brain (CORTEX)
- **Agent Loop** — Think → Act → Observe cycle with parallel tool execution
- **Context Assembly** — system prompt building, history truncation, compaction detection
- **PULSE Integration** — auto-budget expansion (20 → 100 iterations) for complex tasks

#### Communications (NERVE)
- **Discord Adapter** — gateway v10, reconnect with backoff, DM/guild/mention policies
- **Message Router** — inbound routing with policy enforcement, rate limiting, sibling bot yield
- **Platform Formatter** — Discord markdown, WhatsApp bold/strike conversion, smart message splitting
- **Type System** — full message types, channel capabilities, health state machine

#### Memory (MARROW)
- **Session Manager** — create, load, archive sessions with token tracking
- **COMB Bridge** — native integration with COMB persistence (stage/recall/rollup)

#### LLM Providers (VOICE)
- **Provider Chain** — automatic cascade through multiple providers with circuit breakers
- **GitHub Copilot Proxy** — SSE streaming, token exchange, OpenAI-compatible
- **Ollama Provider** — local/qorvex mode, no API keys required
- **Circuit Breakers** — per-provider failure tracking, automatic cooldown, event emission

#### Tool Execution (SINEW)
- **Sandboxed Executor** — timeout enforcement, output limits, error capture
- **Tool Registry** — schema validation, permission scoping per role
- **Tool Definitions** — read, write, edit, exec, web_fetch, search, spawn

#### Health & Recovery (IMMUNE)
- **Watchdog** — process monitoring with automatic restart
- **System Vitals** — disk, memory, load average, uptime monitoring
- **Health Orchestrator** — periodic checks, threshold alerting
- **Audit Loop** — configurable interval, channel-based alerting

#### Scheduling (PULSE)
- **Cron Scheduler** — cron expressions, one-shot timers, named triggers
- **Budget Manager** — iteration tracking, auto-expansion, budget enforcement
- **Health Monitor** — PULSE-specific health tracking and reporting

#### Executive Agents (C-SUITE)
- **Role Registry** — 10 executive roles with industry-specific variants
- **Industry Templates** — fintech, healthcare, SaaS, aerospace, e-commerce, AI/ML
- **Coordinator** — multi-exec dispatch, task routing, result aggregation
- **Structured Reports** — executive-format reporting with audit trails
- **Scoped Access** — per-role tool permissions, domain boundaries

#### Product Owner Agents (POA)
- **POA Manager** — lifecycle management (propose → approve → activate → pause)
- **Audit Runtime** — endpoint health, SSL, service status, disk, memory, logs
- **Report Generation** — JSON + Markdown audit reports with severity classification

#### Workspace Intelligence (AUDITOR)
- **Scanner** — filesystem traversal, project detection (Python, Node, Rust, Go, Java, Ruby)
- **Git Analysis** — branch, remotes, uncommitted changes, staleness detection
- **LOC Counter** — per-project lines of code with language detection
- **Analyzer** — maturity scoring (0-100), gap detection, risk assessment
- **Report Generator** — JSON + Markdown with project table, recommendations, priority actions

#### CLI
- **Interactive Wizard** — guided workspace initialization with industry detection
- **Commands** — init, audit, status, spawn-exec, poa, scale-report, health, test
- **Terminal Formatting** — colored output, tables, progress indicators, box drawing

#### Security
- **Secrets Vault** — encrypted at-rest secret storage with Fernet (AES-128-CBC)
- **Scoped Permissions** — per-role tool access control
- **Credential Isolation** — .env never committed, config examples only

#### Testing
- **30 end-to-end tests** covering all 10 subsystems
- **6 industry scaling tests** (fintech, healthcare, SaaS, aerospace, e-commerce, AI)
- **Zero external dependencies** — all tests run offline

### Architecture Decisions
- **Python 3.11+** — async-native, stdlib-only core, zero mandatory dependencies
- **Event Bus** — loose coupling, any component can fail independently
- **Body Metaphor** — subsystems named after biological systems for intuitive understanding
- **Approval Gates** — monitoring is autonomous, mutation requires human approval
- **Provider Agnostic** — works with any LLM (Ollama, Copilot, Anthropic, OpenAI, Gemini)

---

*Built by Artifact Virtual. Genesis release after 19 days of continuous development.*

## [0.8.0] — 2026-03-14

### Added
- **Artifact Social subsystem** — enterprise social intelligence platform documentation. 7 platform connectors (Twitter/X, LinkedIn, Instagram, Facebook, Telegram, Discord, Substack), NEXUS unified CLI, ML intelligence pipeline, CMO pipeline integration.
- **Google Workspace integration** — native module for enterprise Google services.
- **README overhaul** — best-in-class documentation with ASCII banner, shield badges, architecture diagrams.

### Fixed
- **Context truncation** — emergency context truncation in agent loop to prevent budget overflow.
- **Tool call estimation** — accurate tool_call size estimation with lower 75K budget.
- **ExfilGuard alerts** — proper @mentions and channel routing in security alert pipeline.
- **ATLAS topology** — None guard to prevent NoneType crash during concurrent board cycles.
- **ATLAS manager** — board manager updates for topology stability.
