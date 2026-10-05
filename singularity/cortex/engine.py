"""
CORTEX — Engine
==================

The bridge between messages and the agent loop.

Responsibilities:
    - Receive inbound messages from the NERVE router
    - Manage session history (store/retrieve via MEMORY)
    - Assemble context (system prompt + history + new message)
    - Spawn an AgentLoop per turn
    - **BLINK**: seamless continuation when budget exhausts
    - Store results back to session
    - Load persona identity files on first use

This is the stateful layer. AgentLoop is stateless.
BLINK makes the iteration wall invisible.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from .agent import CortexEngine, AgentConfig, TurnResult
from .blink import BlinkController, BlinkConfig, BlinkPhase
from .context import ContextAssembler, build_system_prompt, extract_archive_summary
from ..voice.provider import ChatMessage
from ..voice.chain import ProviderChain
from ..sinew.executor import ToolExecutor
from ..memory.sessions import SessionStore, Message

logger = logging.getLogger("singularity.cortex.engine")


@dataclass
class CortexConfig:
    """Engine-level configuration."""
    persona_name: str = "singularity"
    persona_prompt: str = ""
    identity_files: list[str] = None  # Paths to identity files to load
    rules: str = ""
    context_budget: int = 180_000
    target_tokens: int = 0  # If >0, compaction fires at target_tokens/context_budget
    agent: Optional[AgentConfig] = None
    blink: Optional[BlinkConfig] = None
    
    def __post_init__(self):
        if self.identity_files is None:
            self.identity_files = []
        if self.agent is None:
            from .agent import AgentConfig
            self.agent = AgentConfig()
        if self.blink is None:
            from .blink import BlinkConfig
            self.blink = BlinkConfig()


class CortexEngine:
    """The thinking engine. Bridges messages → LLM → responses.
    
    One CortexEngine per runtime. It manages:
    - System prompt (loaded once from identity files)
    - Session history (via SessionManager) 
    - Context assembly (per turn)
    - AgentLoop spawning (one per turn)
    - **BLINK** — seamless continuation across budget boundaries
    
    When an AgentLoop exhausts its iteration budget, BLINK kicks in:
    1. Records the blink (depth tracking)
    2. Injects a resume message into the session
    3. Spawns a FRESH AgentLoop with full budget
    4. The new loop picks up from session history — seamless
    5. The user never sees "[Budget exhausted]"
    
    Max blink depth prevents infinite loops (default: 5).
    Total theoretical capacity: 5 × expanded_cap = 500 iterations per turn.
    """
    
    def __init__(
        self,
        voice: ProviderChain,
        tools: ToolExecutor,
        sessions: SessionStore,
        config: CortexConfig,
        bus: Any = None,
        workspace: str = "",
        comb: Any = None,
    ):
        self.voice = voice
        self.tools = tools
        self.sessions = sessions
        self.config = config
        self.bus = bus
        self.workspace = workspace
        self.comb = comb
        self.vdb = comb._vdb if comb and hasattr(comb, '_vdb') else None
        
        self._system_prompt: str = ""
        self._prompt_loaded = False
        self._prompt_lock = asyncio.Lock()
        self._session_locks: dict[str, asyncio.Lock] = {}  # Per-session concurrency guard
        self._session_turn_counts: dict[str, int] = {}     # Turn counter per session for flush_at
        self._context = ContextAssembler(
            context_budget=config.context_budget,
        )
    
    async def boot(self) -> None:
        """Load identity and prepare for processing."""
        async with self._prompt_lock:
            await self._load_system_prompt()
        logger.info("CortexEngine ready (BLINK enabled: %s)", self.config.blink.enabled)
    
    async def process(
        self,
        session_id: str,
        message: str,
        source: Any = None,
        sender_name: str = "",
    ) -> TurnResult:
        """Process an inbound message through the full agent loop.
        
        If BLINK is enabled, this method may spawn multiple sequential
        agent loops to maintain seamless continuity. The user's experience
        is one continuous conversation — the iteration boundary is invisible.
        
        Args:
            session_id: Conversation session ID (maps to channel/DM)
            message: The user's message text
            source: ChannelSource metadata (for context)
            sender_name: Display name of the sender
        
        Returns:
            TurnResult with the response and metadata
        """
        if not self._prompt_loaded:
            async with self._prompt_lock:
                if not self._prompt_loaded:  # double-check after acquiring lock
                    await self._load_system_prompt()
        
        # Per-session lock: prevents two concurrent messages to the same session
        # from corrupting history. Different sessions run fully concurrently.
        if session_id not in self._session_locks:
            self._session_locks[session_id] = asyncio.Lock()
        
        async with self._session_locks[session_id]:
            return await self._process_inner(session_id, message, source, sender_name)
    
    async def _process_inner(
        self,
        session_id: str,
        message: str,
        source: Any = None,
        sender_name: str = "",
    ) -> TurnResult:
        """Inner process — runs under per-session lock."""
        # 1. Store the inbound message in session
        if not message or not message.strip():
            logger.warning(f"Empty message received for session {session_id[:12]}...")
            return TurnResult(
                response="",
                finish_reason="error",
                error="Empty message received",
            )
        
        user_msg = Message(role="user", content=message)
        await self.sessions.add_message(session_id, user_msg)
        
        # 2. Create blink controller for this turn
        blink = BlinkController(
            config=self.config.blink,
            bus=self.bus,
            session_id=session_id,
        )
        
        # Set current sender on tool executor for @mention enforcement
        if source and hasattr(source, 'sender_id') and self.tools:
            self.tools.set_current_sender(source.sender_id)
        
        # 3. The blink loop — may run multiple agent cycles
        final_result = None
        accumulated_response = ""
        
        try:
            while blink.should_continue():
                # Retrieve session history fresh each cycle
                # (previous cycle's tool calls + results are in there)
                history_msgs = await self.sessions.get_messages(session_id)
                
                # Convert to ChatMessages for the LLM
                # Use direct attribute access instead of keyword construction
                chat_history = []
                for m in history_msgs:
                    cm = ChatMessage.__new__(ChatMessage)
                    cm.role = m.role
                    cm.content = m.content or ""
                    cm.tool_calls = m.tool_calls
                    cm.tool_call_id = m.tool_call_id
                    cm.name = m.name
                    chat_history.append(cm)
                
                # If this is a blink resume, inject the resume context
                if blink.state.depth > 0:
                    resume_msg = ChatMessage(
                        role="user",
                        content=blink.get_resume_message(),
                    )
                    chat_history.append(resume_msg)
                    blink.record_resume()
                
                # Assemble context (system prompt + history)
                messages = self._context.assemble(
                    system_prompt=self._system_prompt,
                    history=chat_history[:-1] if blink.state.depth == 0 else chat_history,
                    new_message=chat_history[-1] if blink.state.depth == 0 else None,
                )
                
                # ── Layer 1: Context Monitor — compaction check ──
                history_for_check = chat_history[:-1] if blink.state.depth == 0 else chat_history
                # Use target_tokens-derived threshold when configured, else default 0.75
                if self.config.target_tokens > 0:
                    compaction_threshold = self.config.target_tokens / self.config.context_budget
                else:
                    compaction_threshold = 0.75
                if self._context.needs_compaction(history_for_check, threshold=compaction_threshold):
                    logger.warning(
                        f"Context at >75%% capacity for session {session_id[:12]}... "
                        f"— auto-staging to COMB and compacting"
                    )
                    # Auto-stage critical context to COMB before compaction
                    await self._auto_stage_comb(session_id, history_for_check)
                    
                    # Extract summary and compact
                    summary = extract_archive_summary(history_for_check)
                    
                    # Keep only recent messages (last 30% of history)
                    keep_count = max(10, len(history_for_check) // 3)
                    kept_msgs = history_for_check[-keep_count:]
                    
                    # Fix: skip leading orphan tool results at compaction boundary
                    # A tool message without a preceding assistant+tool_calls is invalid
                    while kept_msgs and kept_msgs[0].role == "tool":
                        kept_msgs = kept_msgs[1:]
                    
                    # Inject summary as system message at the start
                    summary_msg = Message(role="system", content=summary)
                    compacted = [summary_msg] + [
                        Message(
                            role=m.role,
                            content=m.content,
                            tool_calls=m.tool_calls,
                            tool_call_id=m.tool_call_id,
                            name=m.name,
                        )
                        for m in kept_msgs
                    ]
                    
                    # Replace in session store
                    await self.sessions.replace_messages(session_id, compacted)
                    
                    # Re-assemble with compacted history
                    chat_history_compact = []
                    for m in compacted:
                        cm = ChatMessage.__new__(ChatMessage)
                        cm.role = m.role
                        cm.content = m.content or ""
                        cm.tool_calls = m.tool_calls
                        cm.tool_call_id = m.tool_call_id
                        cm.name = m.name
                        chat_history_compact.append(cm)
                    
                    messages = self._context.assemble(
                        system_prompt=self._system_prompt,
                        history=chat_history_compact,
                        new_message=chat_history[-1] if blink.state.depth == 0 else None,
                    )
                    
                    if self.bus:
                        await self.bus.emit_nowait("cortex.context.compacted", {
                            "session_id": session_id,
                            "dropped": len(history_for_check) - keep_count,
                            "kept": keep_count,
                        }, source="cortex")
                
                # ── Conversational fast-path: cap iterations for chat messages ──
                # When the user sends a short conversational message (greeting,
                # question, chat), cap iterations to force a quick response.
                # Full budget preserved for real work requests.
                agent_config = self.config.agent
                if blink.state.depth == 0:  # Only on first cycle, not blink resumes
                    msg_text = (message or "").strip()
                    msg_len = len(msg_text)
                    # Short messages (< 100 chars) with no task indicators
                    # get a tight iteration cap to prevent exploration binges
                    _TASK_KEYWORDS = {
                        'fix', 'build', 'create', 'deploy', 'audit', 'check',
                        'investigate', 'analyze', 'write', 'implement', 'debug',
                        'update', 'install', 'configure', 'search', 'find',
                        'read', 'show', 'list', 'run', 'execute', 'restart',
                        'commit', 'push', 'pull', 'delete', 'remove', 'add',
                        'monitor', 'scan', 'test', 'review', 'dispatch',
                    }
                    msg_lower = msg_text.lower()
                    has_task = any(kw in msg_lower for kw in _TASK_KEYWORDS)
                    if msg_len < 100 and not has_task:
                        from dataclasses import replace
                        agent_config = replace(
                            agent_config,
                            max_iterations=6,
                            expansion_threshold=99,  # Disable auto-expand
                        )
                        logger.info(
                            f"Conversational fast-path: capping to 6 iterations "
                            f"for message ({msg_len} chars): {msg_text[:50]!r}"
                        )

                # Spawn a fresh AgentLoop with blink awareness
                loop = AgentLoop(
                    voice=self.voice,
                    tools=self.tools,
                    config=agent_config,
                    bus=self.bus,
                    blink=blink,
                )
                
                # Run the loop
                result = await loop.run(messages)
                
                # Accumulate response text
                if result.response:
                    accumulated_response += result.response
                
                # Check if we need to blink
                if blink.needs_blink(result.finish_reason):
                    # Record the blink
                    blink.record_blink(result.iterations, result.tool_calls_total)
                    
                    # Store any partial tool call history in session
                    # (The agent loop's messages already include tool calls/results,
                    #  but the final response was empty — store a checkpoint note)
                    checkpoint_msg = Message(
                        role="assistant",
                        content=f"[blink #{blink.state.depth} — continuing seamlessly]",
                    )
                    await self.sessions.add_message(session_id, checkpoint_msg)
                    
                    # Brief cooldown to prevent tight-looping
                    await asyncio.sleep(self.config.blink.cooldown_seconds)
                    
                    logger.info(
                        f"BLINK #{blink.state.depth} for session {session_id[:12]}... "
                        f"— spawning fresh agent loop"
                    )
                    
                    # Loop continues → fresh AgentLoop with full budget
                    continue
                
                # Normal completion — done
                blink.record_complete(result.iterations, result.tool_calls_total)
                final_result = result
                break
        
        except Exception as e:
            logger.error(
                f"Engine error in blink loop for session {session_id[:12]}...: {e}",
                exc_info=True,
            )
            if self.bus:
                await self.bus.emit_nowait("cortex.engine.error", {
                    "session_id": session_id,
                    "error": str(e),
                    "blink_depth": blink.state.depth,
                    "total_iterations": blink.state.total_iterations,
                }, source="cortex")
            final_result = TurnResult(
                response=accumulated_response or "",
                iterations=blink.state.total_iterations,
                tool_calls_total=blink.state.total_tool_calls,
                finish_reason="error",
                error=str(e),
            )
        
        # If we exhausted blink depth without a final result
        if final_result is None:
            logger.warning(
                f"Blink depth exhausted for session {session_id[:12]}... "
                f"after {blink.state.total_iterations} total iterations"
            )
            final_result = TurnResult(
                response=accumulated_response or "[Session paused — maximum depth reached]",
                iterations=blink.state.total_iterations,
                tool_calls_total=blink.state.total_tool_calls,
                finish_reason="blink_capped",
            )
        else:
            # Use accumulated response if the final cycle had empty response
            if not final_result.response and accumulated_response:
                final_result.response = accumulated_response
            # Update totals to include all blink cycles
            final_result.iterations = blink.state.total_iterations
            final_result.tool_calls_total = blink.state.total_tool_calls
        
        # 4. Store tool messages + assistant response in session
        # Persist tool call messages (assistant+tool_calls) and tool results (role=tool)
        # so that session history survives restarts and compaction has accurate size data
        if final_result.tool_messages:
            for tm in final_result.tool_messages:
                await self.sessions.add_message(session_id, Message(
                    role=tm.role,
                    content=tm.content or "",
                    tool_calls=tm.tool_calls,
                    tool_call_id=tm.tool_call_id,
                    name=tm.name,
                ))

        if final_result.response:
            assistant_msg = Message(
                role="assistant",
                content=final_result.response,
            )
            await self.sessions.add_message(session_id, assistant_msg)

        # 5. Periodic COMB flush — fire every flush_at turns if comb is available
        flush_at = getattr(self.config, 'flush_at', 0)
        if flush_at > 0 and self.comb:
            self._session_turn_counts[session_id] = self._session_turn_counts.get(session_id, 0) + 1
            if self._session_turn_counts[session_id] % flush_at == 0:
                try:
                    await self._auto_stage_comb(session_id, chat_history)
                    logger.info(
                        f"COMB periodic flush: session={session_id[:12]}... "
                        f"turn={self._session_turn_counts[session_id]}"
                    )
                except Exception as e:
                    logger.warning(f"COMB periodic flush failed: {e}")
        
        blink_info = ""
        if blink.state.depth > 0:
            blink_info = f" blinks={blink.state.depth}"
        
        logger.info(
            f"Turn complete: session={session_id[:12]}... "
            f"iterations={final_result.iterations} tools={final_result.tool_calls_total} "
            f"tokens={final_result.total_tokens}{blink_info} "
            f"latency={final_result.latency_ms:.0f}ms "
            f"provider={final_result.provider}"
        )
        
        return final_result
    
    async def _auto_stage_comb(
        self,
        session_id: str,
        history: list,
    ) -> None:
        """Auto-stage critical context to COMB before compaction.
        
        Extracts key information from the session history and stages it
        so context survives even if the session is compacted or restarted.
        """
        try:
            summary_parts = [f"[Auto-staged on compaction — session {session_id[:12]}...]"]
            
            # Extract last few assistant text responses as key context
            assistant_texts = []
            for msg in reversed(history):
                if msg.role == "assistant" and hasattr(msg, 'content') and msg.content and not getattr(msg, 'tool_calls', None):
                    text = msg.content.strip()
                    if text and len(text) > 20:
                        # First 200 chars of each
                        assistant_texts.append(text[:200])
                        if len(assistant_texts) >= 3:
                            break
            
            if assistant_texts:
                summary_parts.append("Recent findings: " + " | ".join(reversed(assistant_texts)))
            
            stage_content = "\n".join(summary_parts)
            
            if self.comb:
                await self.comb.stage(stage_content)
                logger.info(f"COMB auto-staged {len(stage_content)} chars on compaction")
            else:
                logger.debug("No COMB instance — skipping auto-stage")
                
        except Exception as e:
            logger.warning(f"COMB auto-stage failed: {e}")
    
    async def _load_system_prompt(self) -> None:
        """Load system prompt from identity files + config."""
        persona_prompt = self.config.persona_prompt
        
        # Load identity files if specified
        identity_content = []
        for fpath in self.config.identity_files:
            full_path = fpath
            if not os.path.isabs(fpath) and self.workspace:
                full_path = os.path.join(self.workspace, fpath)
            
            try:
                with open(full_path, "r") as f:
                    content = f.read()
                identity_content.append(content)
                logger.debug(f"Loaded identity file: {fpath}")
            except FileNotFoundError:
                logger.warning(f"Identity file not found: {fpath}")
            except Exception as e:
                logger.warning(f"Error loading identity file {fpath}: {e}")
        
        if identity_content:
            persona_prompt = "\n\n---\n\n".join(
                [persona_prompt] + identity_content
                if persona_prompt else identity_content
            )
        
        # Load COMB context (use shared instance if available)
        comb_context = ""
        try:
            if self.comb:
                comb_context = await self.comb.recall()
            else:
                from ..memory.comb import CombMemory
                comb = CombMemory(store_path=os.path.join(self.workspace, "singularity", ".core", "memory", "comb"))
                await comb.initialize()
                comb_context = await comb.recall()
            if comb_context:
                logger.debug(f"COMB recall: {len(comb_context)} chars")
        except Exception as e:
            logger.debug(f"COMB recall skipped: {e}")
        
        self._system_prompt = build_system_prompt(
            persona_name=self.config.persona_name,
            persona_prompt=persona_prompt,
            rules=self.config.rules,
            comb_context=comb_context,
            workspace=self.workspace,
        )
        
        self._prompt_loaded = True
        logger.info(
            f"System prompt loaded: {len(self._system_prompt)} chars "
            f"({len(self.config.identity_files)} identity files)"
        )
