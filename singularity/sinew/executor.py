"""
SINEW — Tool Executor
========================

Native tool execution engine for Singularity.

Handles: exec (shell commands), read (files), write (files),
         web_fetch, discord_send, discord_react, comb_stage, comb_recall,
         memory_search, and extensible custom tools.

Safety:
    - Path validation (no escaping workspace)
    - Command filtering (no destructive ops without explicit allow)
    - Timeout enforcement (no runaway processes)
    - Output capping (no memory bombs)
    - All executions logged to event bus

Design:
    Plug's tool executor was 582 lines with everything mixed together.
    Singularity separates concerns:
        - executor.py: the execution engine (this file)
        - sandbox.py: safety validation
        - definitions.py: tool schemas for LLM
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from .sandbox import validate_command, validate_path

logger = logging.getLogger("singularity.sinew.executor")

# Pre-compiled regex for mention detection/stripping (hot path)
_RE_DISCORD_MENTION = re.compile(r'<@!?\d+>')
_RE_MENTION_STRIP = re.compile(r'<@!?\d+>')
_RE_AT_USERNAME = re.compile(r'@\w+')


class ToolExecutor:
    """Execute tools with safety, timeouts, and event bus integration.
    
    Each tool is a method: _tool_{name}(arguments) -> str
    Adding a new tool = adding a new method + schema in definitions.py
    """
    
    def __init__(self, workspace: str, bus: Any = None, 
                 exec_timeout: int = 30, max_output: int = 50_000):
        self.workspace = Path(workspace)
        self.bus = bus
        self.exec_timeout = exec_timeout
        self.max_output = max_output
        self._background_procs: dict[str, asyncio.subprocess.Process] = {}
        self._discord_adapter: Any = None  # Set by runtime after boot
        self._csuite_dispatcher: Any = None  # Set by runtime after C-Suite boot
        self._nexus: Any = None  # Set by runtime after NEXUS boot
        self._comb: Any = None  # Set by runtime after memory boot
        self._vdb: Any = None   # Set by runtime after memory boot
        self._poa_manager: Any = None  # Set by runtime after POA boot
        self._atlas: Any = None  # Set by runtime after ATLAS boot
        self._release_manager: Any = None  # Set by runtime after release boot
        self._hektor: Any = None  # Legacy — kept for backward compat
        self._current_sender_id: str | None = None  # For @mention enforcement
    
    def set_discord_adapter(self, adapter: Any) -> None:
        """Wire the Discord adapter for discord_send/react tools."""
        self._discord_adapter = adapter
    
    def set_csuite_dispatcher(self, dispatcher: Any) -> None:
        """Wire the C-Suite dispatcher for csuite_dispatch tool."""
        self._csuite_dispatcher = dispatcher
    
    def set_comb(self, comb: Any) -> None:
        """Wire the COMB memory instance (shared with runtime, avoids re-init per call)."""
        self._comb = comb
    
    def set_vdb(self, vdb: Any) -> None:
        """Wire the VDB instance for memory_recall/ingest/stats tools."""
        self._vdb = vdb
    
    def set_nexus(self, nexus: Any) -> None:
        """Wire the NEXUS self-optimization engine."""
        self._nexus = nexus
    
    def set_poa_manager(self, manager: Any) -> None:
        """Wire the POA manager for poa_manage tool."""
        self._poa_manager = manager
    
    def set_atlas(self, atlas: Any) -> None:
        """Wire the ATLAS board manager for atlas_* tools."""
        self._atlas = atlas
    
    def set_release_manager(self, manager: Any) -> None:
        """Wire the release manager for release_* tools."""
        self._release_manager = manager
    
    def set_current_sender(self, sender_id: str | None) -> None:
        """Set the current message sender for @mention enforcement."""
        self._current_sender_id = sender_id
    
    async def execute(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool by name. Returns the result as a string."""
        method_name = f"_tool_{tool_name}"
        method = getattr(self, method_name, None)
        
        if method is None:
            error = f"Unknown tool: {tool_name}"
            logger.warning(error)
            return error
        
        t0 = time.perf_counter()
        try:
            result = await method(arguments)
            latency = time.perf_counter() - t0
            
            # Cap output
            if len(result) > self.max_output:
                result = result[:self.max_output] + f"\n\n[Output truncated at {self.max_output} chars]"
            
            if self.bus:
                await self.bus.emit_nowait("sinew.tool.executed", {
                    "tool": tool_name,
                    "latency_ms": round(latency * 1000),
                    "output_chars": len(result),
                    "success": True,
                }, source="sinew")
            
            return result
            
        except Exception as e:
            latency = time.perf_counter() - t0
            error = f"Tool error ({tool_name}): {type(e).__name__}: {e}"
            logger.error(error, exc_info=True)
            
            if self.bus:
                await self.bus.emit_nowait("sinew.tool.failed", {
                    "tool": tool_name,
                    "error": str(e),
                    "latency_ms": round(latency * 1000),
                }, source="sinew")
            
            return error
    
    async def close(self) -> None:
        """Clean up background processes."""
        for pid, proc in self._background_procs.items():
            try:
                proc.terminate()
            except Exception as e:
                logger.debug(f"Suppressed: {e}")
        self._background_procs.clear()
    
    # ── Tool implementations ─────────────────────────────────────────
    
    async def _tool_exec(self, args: dict) -> str:
        """Execute a shell command."""
        command = args.get("command", "")
        timeout = args.get("timeout", self.exec_timeout)
        workdir = args.get("workdir", str(self.workspace))
        background = args.get("background", False)
        
        if not command:
            return "Error: no command provided"
        
        # Sandbox check
        violation = validate_command(command)
        if violation:
            return f"Blocked: {violation}"
        
        if background:
            return await self._exec_background(command, workdir)
        
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=workdir,
                env={**os.environ, "TERM": "dumb"},
            )
            
            try:
                stdout, _ = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                return f"Error: Command timed out after {timeout}s"
            
            output = stdout.decode("utf-8", errors="replace")
            
            if proc.returncode != 0:
                output += f"\n\nExit code: {proc.returncode}"
            
            return output or "(no output)"
            
        except Exception as e:
            return f"Exec error: {e}"
    
    async def _exec_background(self, command: str, workdir: str) -> str:
        """Run a command in the background."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=workdir,
            )
            pid = str(proc.pid)
            self._background_procs[pid] = proc
            return f"Background process started: PID {pid}"
        except Exception as e:
            return f"Background exec error: {e}"
    
    async def _tool_read(self, args: dict) -> str:
        """Read a file."""
        path = args.get("path", "")
        offset = args.get("offset", 0)
        limit = args.get("limit", 0)
        
        if not path:
            return "Error: no path provided"
        
        # Resolve relative paths against workspace (not cwd)
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        
        violation = validate_path(str(p))
        if violation:
            return f"Blocked: {violation}"
        
        try:
            if not p.exists():
                return f"File not found: {path}"
            if not p.is_file():
                return f"Not a file: {path}"
            
            text = p.read_text(encoding="utf-8", errors="replace")
            lines = text.split("\n")
            
            if offset > 0:
                lines = lines[offset - 1:]  # 1-indexed
            if limit > 0:
                lines = lines[:limit]
            
            return "\n".join(lines)
            
        except Exception as e:
            return f"Read error: {e}"
    
    async def _tool_write(self, args: dict) -> str:
        """Write content to a file."""
        path = args.get("path", "")
        content = args.get("content", "")
        
        if not path:
            return "Error: no path provided"
        
        # Resolve relative paths against workspace
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        
        violation = validate_path(str(p), write=True)
        if violation:
            return f"Blocked: {violation}"
        
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"Wrote {len(content)} bytes to {path}"
        except Exception as e:
            return f"Write error: {e}"
    
    async def _tool_edit(self, args: dict) -> str:
        """Edit a file by replacing exact text."""
        path = args.get("path", "")
        old_text = args.get("oldText", "")
        new_text = args.get("newText", "")
        
        if not path or not old_text:
            return "Error: path and oldText required"
        
        # Resolve relative paths against workspace
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        
        violation = validate_path(str(p), write=True)
        if violation:
            return f"Blocked: {violation}"
        
        try:
            if not p.exists():
                return f"File not found: {path}"
            
            content = p.read_text(encoding="utf-8")
            if old_text not in content:
                return f"oldText not found in {path}"
            
            count = content.count(old_text)
            new_content = content.replace(old_text, new_text, 1)
            p.write_text(new_content, encoding="utf-8")
            
            old_lines = old_text.count("\n") + 1
            new_lines = new_text.count("\n") + 1
            return f"Edited {path}: replaced {old_lines} line(s) with {new_lines} line(s)"
            
        except Exception as e:
            return f"Edit error: {e}"
    
    async def _tool_web_fetch(self, args: dict) -> str:
        """Fetch content from a URL."""
        url = args.get("url", "")
        max_chars = args.get("maxChars", 50_000)
        
        if not url:
            return "Error: no URL provided"
        
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    text = await resp.text()
                    
                    # Strip HTML if content type suggests it
                    ct = resp.headers.get("content-type", "")
                    if "html" in ct.lower():
                        try:
                            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                            text = re.sub(r'<[^>]+>', ' ', text)
                            text = re.sub(r'\s+', ' ', text).strip()
                        except Exception as e:
                            logger.debug(f"Suppressed: {e}")
                    
                    if len(text) > max_chars:
                        text = text[:max_chars] + f"\n\n[Truncated at {max_chars} chars]"
                    
                    return f"HTTP {resp.status}\n\n{text}"
                    
        except Exception as e:
            return f"Fetch error: {e}"
    
    # ── Discord tools ────────────────────────────────────────────
    
    async def _tool_discord_send(self, args: dict) -> str:
        """Send a message to a Discord channel."""
        channel_id = args.get("channel_id", "")
        content = args.get("content", "")
        
        if not channel_id or not content:
            return "Error: channel_id and content required"
        
        # ── ANTI-LOOP SYSTEM: Check for mention suppression ──
        should_suppress = self._should_suppress_mentions(content)
        if should_suppress:
            # Strip all @mentions to prevent response loops
            content = self._strip_mentions(content)
            # Replace @end with empty string
            content = content.replace("@end", "").strip()
            if not content:
                content = "(message sent without mention to prevent loop)"
        else:
            # Normal @mention enforcement — if sender is known and not already mentioned, prepend
            if self._current_sender_id and f"<@{self._current_sender_id}>" not in content and f"<@!{self._current_sender_id}>" not in content:
                # Only auto-prepend if no OTHER @mention is present (LLM may be addressing someone specific)
                if not _RE_DISCORD_MENTION.search(content):
                    content = f"<@{self._current_sender_id}> {content}"
        
        # Use the adapter reference if wired
        if self._discord_adapter:
            from ..nerve.types import OutboundMessage
            try:
                result = await self._discord_adapter.send(
                    channel_id, OutboundMessage(content=content)
                )
                if result.success:
                    return f"Sent to {channel_id} (msg_id: {result.message_id})"
                return f"Send failed: {result.error}"
            except Exception as e:
                return f"Discord send error: {e}"
        
        return "Error: Discord adapter not available"
    
    def _should_suppress_mentions(self, content: str) -> bool:
        """Check if we should suppress @mentions to prevent loops."""
        # Look for explicit suppression signals
        if "@end" in content.lower():
            return True
        # If content suggests loop prevention, suppress mentions
        if any(phrase in content.lower() for phrase in [
            "don't respond", "no mention", "suppress mention", "prevent loop",
            "without mention", "loop prevention", "echo prevention"
        ]):
            return True
        return False
    
    def _strip_mentions(self, content: str) -> str:
        """Remove @mentions from content."""
        # Remove Discord mentions: <@123456789> and <@!123456789>
        content = _RE_MENTION_STRIP.sub('', content)
        # Remove @username patterns
        content = _RE_AT_USERNAME.sub('', content)
        return content.strip()
    
    async def _tool_discord_react(self, args: dict) -> str:
        """React to a Discord message with an emoji."""
        channel_id = args.get("channel_id", "")
        message_id = args.get("message_id", "")
        emoji = args.get("emoji", "")
        
        if not channel_id or not message_id or not emoji:
            return "Error: channel_id, message_id, and emoji required"
        
        if self._discord_adapter:
            try:
                await self._discord_adapter.react(channel_id, message_id, emoji)
                return f"Reacted with {emoji} on {message_id}"
            except Exception as e:
                return f"Discord react error: {e}"
        
        return "Error: Discord adapter not available"
    
    # ── COMB tools ───────────────────────────────────────────────
    
    async def _tool_comb_stage(self, args: dict) -> str:
        """Stage information in COMB for persistence."""
        content = args.get("content", "")
        if not content:
            return "Error: content required"
        
        try:
            if self._comb:
                success = await self._comb.stage(content)
            else:
                # Fallback: create instance (shouldn't happen if runtime wired correctly)
                from ..memory.comb import CombMemory
                comb_path = self.workspace / "singularity" / ".core" / "memory" / "comb"
                comb = CombMemory(store_path=str(comb_path))
                await comb.initialize()
                success = await comb.stage(content)
            
            if success:
                return f"✅ Staged {len(content)} chars into COMB"
            return "COMB stage failed"
        except Exception as e:
            return f"COMB stage error: {e}"
    
    async def _tool_comb_recall(self, args: dict) -> str:
        """Recall operational memory from COMB."""
        try:
            if self._comb:
                result = await self._comb.recall()
            else:
                # Fallback: create instance
                from ..memory.comb import CombMemory
                comb_path = self.workspace / "singularity" / ".core" / "memory" / "comb"
                comb = CombMemory(store_path=str(comb_path))
                await comb.initialize()
                result = await comb.recall()
            
            return result or "(no COMB data)"
        except Exception as e:
            return f"COMB recall error: {e}"
    
    # ── Memory tools (VDB) ──────────────────────────────────────────
    
    async def _tool_memory_recall(self, args: dict) -> str:
        """Search persistent memory using native VDB (BM25 + TF-IDF hybrid)."""
        query = args.get("query", "")
        k = int(args.get("k", 5))
        source = args.get("source")
        
        if not query:
            return "Error: query required"
        
        if not self._vdb:
            return "Error: VDB not initialized. Memory system not booted."
        
        try:
            results = self._vdb.search(query, k=k, source=source)
            
            if not results:
                return f"No results for: {query}"
            
            lines = [f"Found {len(results)} results for '{query}':\n"]
            for i, r in enumerate(results, 1):
                # Truncate text for display
                snippet = r.text[:200].replace('\n', ' ')
                lines.append(f"  [{i}] [{r.source}] score={r.score:.3f}")
                lines.append(f"      {snippet}")
                lines.append("")
            return "\n".join(lines)
        except Exception as e:
            return f"Memory recall error: {e}"
    
    async def _tool_memory_ingest(self, args: dict) -> str:
        """Ingest sessions, identity files, and memory files into VDB."""
        if not self._vdb:
            return "Error: VDB not initialized."
        
        try:
            from ..memory.vdb import ingest_sessions, ingest_identity_files, ingest_memory_files
            
            results = []
            
            # Ingest sessions from SQLite
            sessions_db = self.workspace / ".singularity" / "sessions.db"
            if sessions_db.exists():
                r = ingest_sessions(self._vdb, str(sessions_db))
                results.append(f"Sessions: processed {r['processed']}, indexed {r['indexed']}")
            
            # Ingest identity files
            core_dir = self.workspace / "singularity" / ".core"
            if core_dir.exists():
                count = ingest_identity_files(self._vdb, str(core_dir))
                results.append(f"Identity: indexed {count} chunks")
            
            # Ingest memory files
            memory_dir = self.workspace / "memory"
            if memory_dir.exists():
                count = ingest_memory_files(self._vdb, str(memory_dir))
                results.append(f"Memory files: indexed {count} chunks")
            
            return "✅ Memory ingestion complete:\n" + "\n".join(f"  • {r}" for r in results)
        except Exception as e:
            return f"Memory ingest error: {e}"
    
    async def _tool_memory_stats(self, args: dict) -> str:
        """Get VDB statistics."""
        if not self._vdb:
            return "Error: VDB not initialized."
        
        try:
            stats = self._vdb.stats()
            lines = [
                "═══ VDB Memory Stats ═══",
                f"Documents: {stats.document_count}",
                f"Terms: {stats.term_count}",
                f"Disk: {stats.disk_bytes:,} bytes ({stats.disk_bytes / 1024:.1f} KB)",
                f"Last indexed: {stats.last_indexed}",
                "",
                "Sources:",
            ]
            for source, count in sorted(stats.sources.items(), key=lambda x: -x[1]):
                lines.append(f"  {source}: {count}")
            return "\n".join(lines)
        except Exception as e:
            return f"Memory stats error: {e}"
    
    # ── Memory search (legacy compat — routes to VDB) ────────────────
    
    async def _tool_memory_search(self, args: dict) -> str:
        """Legacy memory_search — routes to memory_recall via VDB."""
        return await self._tool_memory_recall(args)
    
    # ── C-Suite Executive Discord Channel Map ──
    # Maps executive role names to their dedicated Discord channel IDs
    CSUITE_CHANNEL_MAP: dict[str, str] = {
        "cto":  "1478716101289447527",
        "coo":  "1478716105458450473",
        "cfo":  "1478716109053104228",
        "ciso": "1478716112827842661",
    }
    CSUITE_DISPATCH_CHANNEL: str = "1478716096667189292"

    async def _tool_csuite_dispatch(self, args: dict) -> str:
        """Dispatch a task to the C-Suite executives.
        
        Routes tasks to CTO/COO/CFO/CISO through the native Coordinator.
        Results are forwarded to each executive's dedicated Discord channel.
        """
        if not self._csuite_dispatcher:
            return "Error: C-Suite not initialized. Check config csuite.enabled."
        
        description = args.get("description", "")
        target = args.get("target", "auto")
        priority = args.get("priority", "normal")
        max_iterations = args.get("max_iterations", 25)
        
        if not description:
            return "Error: description required"
        
        try:
            result = await self._csuite_dispatcher.dispatch_to(
                target=target,
                description=description,
                priority=priority,
                max_iterations=max_iterations,
            ) if target != "auto" else await self._csuite_dispatcher.dispatch(
                description=description,
                priority=priority,
                max_iterations=max_iterations,
            )
            
            # Format response
            lines = [f"📋 Dispatch {result.dispatch_id} — {len(result.tasks)} task(s), {result.duration:.1f}s"]
            for t in result.tasks:
                icon = "✅" if t.status.value == "complete" else "❌" if t.status.value == "failed" else "⏱️"
                lines.append(f"  {icon} {t.role.value.upper()}: {t.status.value}")
                if t.response:
                    lines.append(f"  Response: {t.response[:500]}")
                if t.error:
                    lines.append(f"  Error: {t.error[:200]}")
            
            # ── Forward results to dedicated executive Discord channels ──
            # NOTE: Webhook-based reporting is now handled by coordinator.py → WebhookReporter
            # The adapter-based forwarding below is disabled to prevent double-posting.
            # await self._forward_csuite_to_discord(result, description)
            
            return "\n".join(lines)
        except Exception as e:
            return f"C-Suite dispatch error: {e}"

    async def _forward_csuite_to_discord(self, result: Any, task_description: str) -> None:
        """Forward C-Suite dispatch results to dedicated executive Discord channels.
        
        Each executive's result gets posted to their own channel.
        A summary is posted to the #dispatch channel.
        """
        if not self._discord_adapter:
            logger.warning("Cannot forward C-Suite results — Discord adapter not available")
            return
        
        from ..nerve.types import OutboundMessage
        
        # Post individual results to each executive's channel
        for t in result.tasks:
            role_name = t.role.value.lower()
            channel_id = self.CSUITE_CHANNEL_MAP.get(role_name)
            if not channel_id:
                continue
            
            icon = "✅" if t.status.value == "complete" else "❌" if t.status.value == "failed" else "⏱️"
            
            # Build the message for this executive's channel
            msg_lines = [
                f"{icon} **{role_name.upper()} — Dispatch {result.dispatch_id}**",
                f"**Task:** {task_description[:200]}",
                f"**Status:** {t.status.value} | {t.iterations_used} iterations | {t.duration_seconds:.1f}s",
                "",
            ]
            
            if t.response:
                # Cap at 1800 chars to stay under Discord's 2000 limit
                parts = [t.response[:1800]]
                if len(t.response) > 1800:
                    parts.append("\n... (truncated)")
                msg_lines.append("".join(parts))
            
            if t.error:
                msg_lines.append(f"\n⚠️ **Error:** {t.error[:300]}")
            
            msg = "\n".join(msg_lines)
            
            try:
                await self._discord_adapter.send(
                    channel_id, OutboundMessage(content=msg)
                )
                logger.info(f"C-Suite result forwarded to #{role_name} channel ({channel_id})")
            except Exception as e:
                logger.error(f"Failed to forward {role_name} result to Discord: {e}")
        
        # Post summary to #dispatch channel
        summary_lines = [
            f"📋 **Dispatch {result.dispatch_id}** — {len(result.tasks)} task(s), {result.duration:.1f}s",
            f"**Task:** {task_description[:200]}",
            "",
        ]
        for t in result.tasks:
            icon = "✅" if t.status.value == "complete" else "❌" if t.status.value == "failed" else "⏱️"
            summary_lines.append(f"{icon} **{t.role.value.upper()}**: {t.status.value} ({t.duration_seconds:.1f}s)")
        
        summary = "\n".join(summary_lines)
        
        try:
            await self._discord_adapter.send(
                self.CSUITE_DISPATCH_CHANNEL, OutboundMessage(content=summary)
            )
            logger.info(f"Dispatch summary forwarded to #dispatch channel")
        except Exception as e:
            logger.error(f"Failed to forward dispatch summary to Discord: {e}")

    # ── NEXUS Tools ──────────────────────────────────────────

    async def _tool_nexus_audit(self, args: dict) -> str:
        """Run NEXUS self-optimization audit on Singularity's own codebase."""
        if not self._nexus:
            return "Error: NEXUS engine not initialized."
        
        target = args.get("target")  # Optional: specific file or subdirectory
        mode = args.get("mode", "audit")  # audit, propose, optimize, report
        
        try:
            result = await self._nexus.run(mode=mode, target=target)
            
            lines = [result.summary()]
            
            # Include top findings for audit/report modes
            if mode in ("audit", "report") and result.report.findings:
                lines.append("")
                lines.append("── Top Findings ──")
                shown = 0
                for f in result.report.findings:
                    if f.severity in ("critical", "issue"):
                        lines.append(str(f))
                        shown += 1
                        if shown >= 15:
                            remaining = sum(1 for x in result.report.findings 
                                          if x.severity in ("critical", "issue")) - shown
                            if remaining > 0:
                                lines.append(f"  ... and {remaining} more issues")
                            break
            
            # Include proposals for propose/optimize modes
            if mode in ("propose", "optimize") and result.proposals:
                lines.append("")
                lines.append("── Proposals ──")
                for p in result.proposals[:10]:
                    lines.append(str(p))
                if len(result.proposals) > 10:
                    lines.append(f"  ... and {len(result.proposals) - 10} more proposals")
            
            return "\n".join(lines)
        except Exception as e:
            return f"NEXUS audit error: {e}"

    async def _tool_nexus_status(self, args: dict) -> str:
        """Get current NEXUS engine status including active swaps."""
        if not self._nexus:
            return "Error: NEXUS engine not initialized."
        
        try:
            status = self._nexus.get_status()
            active = self._nexus.get_active_swaps()
            
            lines = [
                "═══ NEXUS Status ═══",
                f"Started: {status['started']}",
                f"Optimization runs: {status['run_count']}",
                f"Active swaps: {status['active_swaps']}",
                f"Journal entries: {status['journal_entries']}",
                f"Source root: {status['source_root']}",
            ]
            
            if active:
                lines.append("")
                lines.append("── Active Swaps ──")
                for swap in active:
                    lines.append(
                        f"  [{swap.swap_id}] {swap.module_name}."
                        f"{(swap.class_name + '.') if swap.class_name else ''}"
                        f"{swap.function_name} — {swap.reason}"
                    )
            
            return "\n".join(lines)
        except Exception as e:
            return f"NEXUS status error: {e}"

    async def _tool_nexus_swap(self, args: dict) -> str:
        """Hot-swap a function at runtime via NEXUS."""
        if not self._nexus:
            return "Error: NEXUS engine not initialized."
        
        module_name = args.get("module_name", "")
        function_name = args.get("function_name", "")
        new_source = args.get("new_source", "")
        reason = args.get("reason", "Manual hot-swap")
        class_name = args.get("class_name")
        
        if not all([module_name, function_name, new_source]):
            return "Error: module_name, function_name, and new_source are required."
        
        try:
            swap_id = await self._nexus.hotswap.swap(
                module_name=module_name,
                function_name=function_name,
                new_source=new_source,
                reason=reason,
                class_name=class_name,
                validate=False,  # Manual swaps — caller is responsible
            )
            return f"✅ Swap successful: {swap_id}\nTarget: {module_name}.{(class_name + '.') if class_name else ''}{function_name}\nReason: {reason}"
        except (ValueError, RuntimeError) as e:
            return f"❌ Swap failed: {e}"

    async def _tool_nexus_rollback(self, args: dict) -> str:
        """Rollback a NEXUS hot-swap by swap ID, or rollback all."""
        if not self._nexus:
            return "Error: NEXUS engine not initialized."
        
        swap_id = args.get("swap_id")
        rollback_all = args.get("all", False)
        
        try:
            if rollback_all:
                count = await self._nexus.rollback_all()
                return f"✅ Rolled back {count} active swap(s)."
            elif swap_id:
                success = await self._nexus.rollback(swap_id)
                if success:
                    return f"✅ Rolled back {swap_id}"
                else:
                    return f"❌ Rollback failed — swap_id {swap_id} not found or already rolled back"
            else:
                return "Error: provide swap_id or set all=true"
        except Exception as e:
            return f"Rollback error: {e}"

    async def _tool_nexus_evolve(self, args: dict) -> str:
        """Run NEXUS self-evolution cycle — find safe transformations, validate, and apply."""
        if not self._nexus:
            return "Error: NEXUS engine not initialized."
        
        target = args.get("target")
        dry_run = args.get("dry_run", True)  # Default to dry run for safety
        max_evolutions = args.get("max_evolutions", 50)
        
        try:
            report = await self._nexus.evolve(
                target=target,
                dry_run=dry_run,
                max_evolutions=max_evolutions,
            )
            return report.summary()
        except Exception as e:
            return f"NEXUS evolution error: {e}"

    async def _tool_poa_setup(self, args: dict) -> str:
        """Run the double-audit POA setup flow."""
        from singularity.poa.setup import SetupFlow
        import json as _json
        
        workspace = args.get("workspace", str(self.workspace))
        auto_approve = args.get("auto_approve", False)
        
        try:
            flow = SetupFlow(workspace=workspace)
            report = flow.run()
            
            result_lines = [
                f"📊 POA Setup — Double Audit Complete",
                f"",
                f"**Phase 1 (Broad):** {report.broad_summary.get('total_projects', '?')} projects, "
                f"{report.broad_summary.get('total_lines', 0):,} LOC, "
                f"health {report.broad_summary.get('health_score', '?')}/100",
                f"",
                f"**Phase 2 (Review):** {report.review_summary.get('product_count', '?')} products identified, "
                f"{report.review_summary.get('skipped_count', '?')} filtered out",
                f"",
                f"**Phase 3 (Focused):** {len(report.focused_results)} products audited",
            ]
            
            # Status summary
            green = sum(1 for r in report.focused_results if r.get("status") == "green")
            yellow = sum(1 for r in report.focused_results if r.get("status") == "yellow")
            red = sum(1 for r in report.focused_results if r.get("status") == "red")
            result_lines.append(f"  🟢 {green} green | 🟡 {yellow} yellow | 🔴 {red} red")
            result_lines.append(f"")
            
            # Proposed POAs
            result_lines.append(f"**Phase 4:** {len(report.proposed_poas)} POAs proposed")
            for poa in report.proposed_poas[:10]:
                status = poa.get("audit_status", "?")
                icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(status, "⚪")
                result_lines.append(
                    f"  {icon} {poa['product_name']} [{poa['priority']}] — "
                    f"{len(poa.get('endpoints', []))} endpoints"
                )
            if len(report.proposed_poas) > 10:
                result_lines.append(f"  ... +{len(report.proposed_poas) - 10} more")
            
            # Auto-approve if requested
            if auto_approve:
                from singularity.poa.setup import ReviewResult, ProductClassification
                # Reload the review from disk
                review_path = flow.sg_dir / "audits" / "setup" / "review" / "latest.json"
                if review_path.exists():
                    review_data = _json.loads(review_path.read_text())
                    # Reconstruct a minimal ReviewResult
                    review = ReviewResult()
                    for pd in review_data.get("products", []):
                        pc = ProductClassification(
                            project_name=pd["project_name"],
                            project_path=pd["project_path"],
                            total_lines=pd.get("total_lines", 0),
                            is_product=True,
                            proposed_config=pd.get("proposed_config"),
                        )
                        review.products.append(pc)
                    
                    green_ids = [
                        poa["product_id"] for poa in report.proposed_poas
                        if poa.get("audit_status") == "green"
                    ]
                    activated = flow.activate(green_ids, review)
                    result_lines.append(f"")
                    result_lines.append(f"✅ Auto-approved {len(activated)} green POAs")
                    for a in activated:
                        result_lines.append(f"  🟢 {a.product_name}")
            
            return "\n".join(result_lines)
            
        except Exception as e:
            logger.error(f"POA setup error: {e}", exc_info=True)
            return f"POA setup error: {e}"

    async def _tool_poa_manage(self, args: dict) -> str:
        """Manage POA lifecycle."""
        from singularity.poa.manager import POAManager
        from singularity.poa.runtime import POARuntime
        
        action = args.get("action", "list")
        product_id = args.get("product_id", "")
        
        # Always discover both workspaces — local first (has active POAs)
        sg_dirs = []
        own = Path(str(self.workspace)) / ".singularity"
        if own.exists():
            sg_dirs.append(own)
        enterprise = Path("/home/adam/workspace/enterprise/.singularity")
        if enterprise.exists() and enterprise != own:
            sg_dirs.append(enterprise)
        
        if not sg_dirs:
            return "Error: no workspace with .singularity found"
        
        all_managers = [POAManager(d) for d in sg_dirs]
        
        mgr = all_managers[0]  # Primary
        sg_dir = sg_dirs[0]
        
        if action == "list":
            seen = {}  # product_id → POAConfig (prefer active over retired)
            for m in all_managers:
                for p in m.list_all():
                    existing = seen.get(p.product_id)
                    if existing is None:
                        seen[p.product_id] = p
                    elif p.status.value == "active" and existing.status.value != "active":
                        seen[p.product_id] = p  # Active takes priority
            
            active_poas = [p for p in seen.values() if p.status.value == "active"]
            other_poas = [p for p in seen.values() if p.status.value != "active"]
            
            lines = ["📋 **POA List:**"]
            lines.append(f"**Active:** {len(active_poas)} | **Other:** {len(other_poas)} | **Total:** {len(seen)}")
            lines.append("")
            
            # Always show active POAs with detail
            for p in sorted(active_poas, key=lambda x: x.product_name):
                ep_info = f" ({len(p.endpoints)} endpoints)" if p.endpoints else " (no endpoints)"
                svc_info = f" svc:{p.service_name}" if p.service_name else ""
                lines.append(f"  🟢 **{p.product_name}** ({p.product_id}){ep_info}{svc_info}")
            
            # Show non-active only as counts by status
            if other_poas:
                status_counts = {}
                for p in other_poas:
                    status_counts[p.status.value] = status_counts.get(p.status.value, 0) + 1
                other_summary = ", ".join(f"{v} {k}" for k, v in sorted(status_counts.items()))
                lines.append(f"\n  _{other_summary}_")
            
            if len(active_poas) == 0:
                lines.append("  _(no active POAs)_")
            return "\n".join(lines)
        
        elif action == "status":
            total = 0
            counts = {}
            for m in all_managers:
                s = m.status_summary()
                total += s.get("total", 0)
                for k, v in s.items():
                    if k != "total":
                        counts[k] = counts.get(k, 0) + v
            lines = [f"📊 POA Status — {total} total"]
            for s in ["active", "proposed", "paused", "retired", "error"]:
                count = counts.get(s, 0)
                if count:
                    lines.append(f"  {s}: {count}")
            return "\n".join(lines)
        
        elif action == "audit":
            if not product_id:
                # Audit ALL active POAs across all workspaces
                all_active = []
                workspace_map = {}
                seen = set()
                for m_idx, m in enumerate(all_managers):
                    for config in m.list_active():
                        if config.product_id not in seen:
                            seen.add(config.product_id)
                            all_active.append(config)
                            workspace_map[config.product_id] = sg_dirs[m_idx]
                if not all_active:
                    return "No active POAs to audit."
                lines = ["# POA Full Audit Report", f"**Time:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", f"**Products:** {len(all_active)}", ""]
                green = yellow = red = 0
                for config in all_active:
                    ws = workspace_map[config.product_id]
                    try:
                        report = POARuntime.run_audit(config)
                        POARuntime.save_audit(report, ws / "poas")
                        icon = {"green": "🟢", "yellow": "🟡", "red": "🔴"}.get(report.overall_status, "⚪")
                        failed_detail = ""
                        if report.failed > 0:
                            failed_checks = [c for c in report.checks if not c.passed]
                            failed_detail = " — " + "; ".join(f"{c.name}: {c.message[:60]}" for c in failed_checks)
                        lines.append(f"{icon} **{config.product_name}** {report.passed}/{len(report.checks)} checks ({report.duration_ms:.0f}ms){failed_detail}")
                        if report.overall_status == "green": green += 1
                        elif report.overall_status == "yellow": yellow += 1
                        else: red += 1
                    except Exception as e:
                        lines.append(f"🔴 **{config.product_name}** — audit error: {e}")
                        red += 1
                lines.insert(3, f"**Summary:** 🟢{green} 🟡{yellow} 🔴{red}")
                return "\n".join(lines)
            # Single product audit — find across managers
            config = None
            found_dir = sg_dir
            for m_idx, m in enumerate(all_managers):
                config = m.get(product_id)
                if config:
                    found_dir = sg_dirs[m_idx]
                    break
            if not config:
                return f"Error: POA '{product_id}' not found"
            report = POARuntime.run_audit(config)
            POARuntime.save_audit(report, found_dir / "poas")
            return report.to_markdown()
        
        elif action == "kill":
            if not product_id:
                return "Error: product_id required for kill"
            config = mgr.get(product_id)
            if not config:
                return f"Error: POA '{product_id}' not found"
            if mgr.retire(product_id):
                return f"💀 POA '{config.product_name}' retired."
            return f"Error: failed to retire '{product_id}' (status: {config.status.value})"
        
        elif action == "pause":
            if not product_id:
                return "Error: product_id required for pause"
            config = mgr.get(product_id)
            if not config:
                return f"Error: POA '{product_id}' not found"
            if mgr.pause(product_id):
                return f"⏸️ POA '{config.product_name}' paused."
            return f"Error: failed to pause '{product_id}' (status: {config.status.value})"
        
        elif action == "resume":
            if not product_id:
                return "Error: product_id required for resume"
            config = mgr.get(product_id)
            if not config:
                return f"Error: POA '{product_id}' not found"
            if mgr.activate(product_id):
                return f"▶️ POA '{config.product_name}' resumed."
            return f"Error: failed to resume '{product_id}' (status: {config.status.value})"
        
        return f"Unknown action: {action}"

    # ── ATLAS (Board Manager) ────────────────────────────

    async def _tool_atlas_status(self, args: dict) -> str:
        """Get ATLAS board manager status."""
        if not self._atlas:
            return "ATLAS board manager is not initialized."
        try:
            status = self._atlas.get_status()
            lines = ["**ATLAS Board Manager**", ""]
            lines.append(f"Cycles: {status['cycle_count']}")
            lines.append(f"Last cycle: {status['last_cycle'] or 'never'}")
            lines.append(f"Running: {status['running']}")
            lines.append(f"Modules tracked: {status['modules']}")

            by_status = status.get("by_status", {})
            if by_status:
                parts = [f"{k}: {v}" for k, v in sorted(by_status.items())]
                lines.append(f"By status: {', '.join(parts)}")

            by_machine = status.get("by_machine", {})
            if by_machine:
                parts = [f"{k}: {v}" for k, v in sorted(by_machine.items())]
                lines.append(f"By machine: {', '.join(parts)}")

            lines.append(f"Open issues: {status['issues']}")

            hidden = status.get("hidden_modules", [])
            if hidden:
                lines.append(f"Hidden modules: {', '.join(hidden)}")

            if status.get("new_modules"):
                lines.append(f"New (last cycle): {', '.join(status['new_modules'])}")
            if status.get("gone_modules"):
                lines.append(f"Gone (last cycle): {', '.join(status['gone_modules'])}")

            return "\n".join(lines)
        except Exception as e:
            return f"ATLAS status error: {e}"

    async def _tool_atlas_topology(self, args: dict) -> str:
        """Get the enterprise topology map."""
        if not self._atlas:
            return "ATLAS board manager is not initialized."
        try:
            include_hidden = args.get("include_hidden", False)
            # Run a scan if no data yet
            if not self._atlas.graph.modules:
                await self._atlas.run_cycle()
            return self._atlas.get_topology(include_hidden=include_hidden)
        except Exception as e:
            return f"ATLAS topology error: {e}"

    async def _tool_atlas_module(self, args: dict) -> str:
        """Get detailed report for a specific module."""
        if not self._atlas:
            return "ATLAS board manager is not initialized."
        module_id = args.get("module_id", "")
        if not module_id:
            return "Error: module_id is required."
        try:
            # Run a scan if no data yet
            if not self._atlas.graph.modules:
                await self._atlas.run_cycle()
            return self._atlas.get_module_detail(module_id)
        except Exception as e:
            return f"ATLAS module error: {e}"

    async def _tool_atlas_report(self, args: dict) -> str:
        """Generate the full ATLAS board report."""
        if not self._atlas:
            return "ATLAS board manager is not initialized."
        try:
            include_hidden = args.get("include_hidden", False)
            # Run a fresh cycle for current data
            await self._atlas.run_cycle()
            return self._atlas.get_board_report(include_hidden=include_hidden)
        except Exception as e:
            return f"ATLAS report error: {e}"

    async def _tool_atlas_visibility(self, args: dict) -> str:
        """Manage ATLAS module visibility — hide/show/list."""
        if not self._atlas:
            return "ATLAS board manager is not initialized."
        try:
            action = args.get("action", "list")

            if action == "list":
                index = self._atlas.get_visibility_index()
                lines = ["**ATLAS Visibility Index**", ""]
                lines.append(f"Visible: {index['visible_count']} | Hidden: {index['hidden_count']}")
                lines.append("")
                for mod_id, info in index["modules"].items():
                    icon = "👁️" if info["visible"] else "🔒"
                    lines.append(f"  {icon} {mod_id} ({info['type']})")
                return "\n".join(lines)

            elif action in ("hide", "show"):
                module_id = args.get("module_id", "")
                if not module_id:
                    return "Error: module_id is required for hide/show."
                visible = action == "show"
                return self._atlas.set_visibility(module_id, visible)

            else:
                return f"Unknown action '{action}'. Use: list, hide, show."
        except Exception as e:
            return f"ATLAS visibility error: {e}"

    # ── Release Manager Tools ─────────────────────────────────────────

    async def _tool_release_scan(self, args: dict) -> str:
        """Scan all tracked repos for unreleased commits."""
        if not self._release_manager:
            return "Release manager not initialized."
        try:
            proposals = self._release_manager.scan_all()
            if not proposals:
                return "No unreleased work found across tracked repos."
            
            lines = [f"📦 **{len(proposals)} release proposal(s):**\n"]
            for p in proposals:
                lines.append(
                    f"**{p.product_id}** {p.current_version} → **{p.proposed_version}** "
                    f"({p.bump_type} bump, {len(p.commits)} commits)"
                )
                # Show top 5 commits
                for c in p.commits[:5]:
                    lines.append(f"  • {c['subject']} (`{c['hash']}`)")
                if len(p.commits) > 5:
                    lines.append(f"  ... and {len(p.commits) - 5} more")
                lines.append("")
            
            lines.append("Use `release_confirm <product_id>` to approve, `release_reject <product_id>` to dismiss.")
            return "\n".join(lines)
        except Exception as e:
            return f"Release scan error: {e}"

    async def _tool_release_status(self, args: dict) -> str:
        """Get release manager status."""
        if not self._release_manager:
            return "Release manager not initialized."
        try:
            status = self._release_manager.get_status()
            lines = [
                f"📦 **Release Manager**",
                f"Repos tracked: {status['repos_tracked']}",
                f"Pending proposals: {status['pending_proposals']}",
                f"Confirmed (ready to ship): {status['confirmed']}",
                f"Total shipped: {status['shipped_total']}",
            ]
            if status['proposals']:
                lines.append("\n**Proposals:**")
                for p in status['proposals']:
                    icon = {"pending": "⏳", "confirmed": "✅", "shipped": "📦", "rejected": "❌"}.get(p['status'], "?")
                    lines.append(
                        f"  {icon} **{p['product_id']}** {p['current']} → {p['proposed']} "
                        f"({p['bump']}, {p['commits']} commits) — {p['status']}"
                    )
            return "\n".join(lines)
        except Exception as e:
            return f"Release status error: {e}"

    async def _tool_release_confirm(self, args: dict) -> str:
        """Confirm a pending release proposal."""
        if not self._release_manager:
            return "Release manager not initialized."
        product_id = args.get("product_id", "")
        if not product_id:
            return "Error: product_id is required."
        try:
            proposal = self._release_manager.confirm(product_id)
            if not proposal:
                return f"No pending proposal found for '{product_id}'."
            return (
                f"✅ **Confirmed:** {product_id} {proposal.current_version} → "
                f"**{proposal.proposed_version}**\n"
                f"Ready to ship. Use `release_ship {product_id}` to publish."
            )
        except Exception as e:
            return f"Release confirm error: {e}"

    async def _tool_release_ship(self, args: dict) -> str:
        """Ship a confirmed release."""
        if not self._release_manager:
            return "Release manager not initialized."
        product_id = args.get("product_id", "")
        if not product_id:
            return "Error: product_id is required."
        try:
            import asyncio
            result = await self._release_manager.ship(product_id)
            if result.get("success"):
                lines = [
                    f"🚀 **SHIPPED: {product_id} {result['version']}**",
                    f"Tag created: {'✅' if result.get('tag_created') else '❌'}",
                ]
                pushed = result.get("pushed", {})
                for remote, ok in pushed.items():
                    lines.append(f"Pushed to {remote}: {'✅' if ok else '❌'}")
                if result.get("github_release"):
                    lines.append(f"GitHub release: ✅ {result.get('release_url', '')}")
                elif result.get("gh_error"):
                    lines.append(f"GitHub release: ❌ {result['gh_error']}")
                return "\n".join(lines)
            else:
                return f"❌ Ship failed: {result.get('error', 'unknown error')}"
        except Exception as e:
            return f"Release ship error: {e}"

    async def _tool_release_reject(self, args: dict) -> str:
        """Reject a pending release proposal."""
        if not self._release_manager:
            return "Release manager not initialized."
        product_id = args.get("product_id", "")
        if not product_id:
            return "Error: product_id is required."
        try:
            proposal = self._release_manager.reject(product_id)
            if not proposal:
                return f"No pending proposal found for '{product_id}'."
            return f"❌ **Rejected:** {product_id} {proposal.proposed_version} — proposal dismissed."
        except Exception as e:
            return f"Release reject error: {e}"

