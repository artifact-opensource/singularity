"""
CORTEX — The Agent Loop
==========================

The brain of Singularity. This is where thinking happens.

Loop:
    1. Assemble context (system prompt + session history + new message)
    2. Send to VOICE (LLM provider chain)  
    3. If response has tool calls → execute them (SINEW) → add results → goto 2
    4. If response is text → emit to NERVE → store in MEMORY → done
    5. Enforce iteration budget (PULSE) — never loop forever

Design decisions:
    - Agent loop is persona-agnostic. Persona is injected via system prompt.
    - Tool execution is parallel by default (like Mach6, not serial like Plug).
    - Each iteration emits events. The bus carries everything.
    - Context window management is the agent's responsibility.
    - The agent doesn't know about Discord or WhatsApp. It knows about
      messages, tools, and responses. NERVE handles the rest.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional, Dict, List
from os import urandom

from ..voice.provider import ChatMessage, ChatResponse
from ..voice.chain import ProviderChain
from ..sinew.executor import ToolExecutor
from ..sinew.definitions import TOOL_DEFINITIONS
from .blink import BlinkController
from .context import compress_tool_results

logger = logging.getLogger("singularity.cortex.engine")


class LoopState(Enum):
    THINK = auto()
    ACT = auto()
    OBSERVE = auto()
    COMPRESS = auto()
    COMPLETE = auto()
    ERROR = auto()


@dataclass
class AgentConfig:
    """Configuration for an agent loop instance."""
    persona_name: str = "singularity"
    system_prompt: str = ""
    max_iterations: int = 20
    expanded_iterations: int = 100  
    expansion_threshold: int = 18   
    temperature: float = 0.3        
    max_tokens: int = 8192
    parallel_tools: bool = True     


@dataclass
class TurnResult:
    """Result of a complete agent turn (message in → response out)."""
    response: str = ""
    iterations: int = 0
    tool_calls_total: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    provider: str = ""
    finish_reason: str = "stop"     # stop, budget_exceeded, error
    error: Optional[str] = None
    tool_messages: list = None      


class CortexEngine:
    """An asynchronous, state-driven agent execution engine.
    
    Decoupled from blocking loops, tracking state explicitly to allow for 
    granular instrumentation, resilient recovery checkpoints, and safe data budgeting.
    """
    
    def __init__(
        self,
        voice: ProviderChain,
        tools: ToolExecutor,
        config: AgentConfig,
        bus: Any = None,
        blink: BlinkController | None = None,
    ):
        self.voice = voice
        self.tools = tools
        self.config = config
        self.bus = bus
        self.blink = blink
        
        self.iteration = 0
        self.max_iterations = config.max_iterations
        self.expanded = False
        self.tool_calls_total = 0
        self.total_tokens = 0
        self.turn_id = urandom(4).hex()
        
        self.current_state = LoopState.THINK
        self.new_tool_messages: List[ChatMessage] = []

    async def run(self, messages: List[ChatMessage]) -> TurnResult:
        """Runs the event-driven state engine through the conversation execution pipeline."""
        t0 = time.perf_counter()
        
        # Isolate historical data states to block cross-turn state pollution
        local_history = list(messages)
        active_error: Optional[str] = None
        final_content: str = ""
        provider_name: str = "unknown"
        finish_reason: str = "stop"

        while self.current_state != LoopState.COMPLETE:
            try:
                # ── State Machine Router ─────────────────────────────────────
                if self.current_state == LoopState.THINK:
                    final_content, provider_name, finish_reason = await self._handle_think(local_history)
                    
                elif self.current_state == LoopState.ACT:
                    await self._handle_act(local_history)
                    
                elif self.current_state == LoopState.COMPRESS:
                    await self._handle_compress(local_history)
                    
                elif self.current_state == LoopState.ERROR:
                    raise RuntimeError(active_error or "Unknown failure encountered in cortex processing.")

            except Exception as ex:
                logger.error(f"[{self.turn_id}] Engine transition crash in state {self.current_state.name}: {ex}", exc_info=True)
                active_error = str(ex)
                finish_reason = "error"
                self.current_state = LoopState.COMPLETE

        latency = (time.perf_counter() - t0) * 1000
        
        if self.bus:
            event_name = "cortex.turn.complete" if finish_reason == "stop" else "cortex.turn.error"
            await self.bus.emit_nowait(event_name, {
                "turn_id": self.turn_id,
                "iterations": self.iteration,
                "latency_ms": round(latency),
                "error": active_error
            }, source="cortex")

        return TurnResult(
            response=final_content,
            iterations=self.iteration,
            tool_calls_total=self.tool_calls_total,
            total_tokens=self.total_tokens,
            latency_ms=latency,
            provider=provider_name,
            finish_reason=finish_reason,
            error=active_error,
            tool_messages=self.new_tool_messages
        )

    async def _handle_think(self, history: List[ChatMessage]) -> tuple[str, str, str]:
        """Manages the iteration tracking bounds and processes predictions via the LLM matrix."""
        self.iteration += 1
        if self.iteration > self.max_iterations:
            logger.warning(f"[{self.turn_id}] Maximum processing budget exhausted.")
            return "", "unknown", "budget_exceeded"

        # ── PULSE Check ──────────────────────────────────────────────────────
        if not self.expanded and self.iteration >= self.config.expansion_threshold:
            old_max = self.max_iterations
            self.max_iterations = self.config.expanded_iterations
            self.expanded = True
            if self.bus:
                await self.bus.emit_nowait("cortex.budget.expanded", {"turn_id": self.turn_id, "new_max": self.max_iterations}, source="cortex")
            if self.blink:
                self.blink.notify_cap_expanded(old_max, self.max_iterations)

        # ── BLINK Integrations ───────────────────────────────────────────────
        if self.blink:
            remaining = self.max_iterations - self.iteration
            if self.blink.should_prepare(remaining):
                history.append(ChatMessage(role="user", content=self.blink.get_prepare_message()))
            elif self.blink.should_checkpoint(self.iteration):
                history.append(ChatMessage(role="user", content=self.blink.get_checkpoint_message(self.iteration)))

        if self.bus:
            await self.bus.emit_nowait("cortex.iteration.start", {"turn_id": self.turn_id, "iteration": self.iteration}, source="cortex")

        # Route down into context reduction before invoking prediction blocks
        self.current_state = LoopState.COMPRESS
        return "", "unknown", "stop"

    async def _handle_compress(self, history: List[ChatMessage]) -> tuple[str, str, str]:
        """Performs precise look-ahead checks and structures massive contexts safely."""
        if self.iteration > 1:
            compress_tool_results(history, self.iteration)

        # Token safety evaluation block
        MAX_PROMPT_CHARS = 350_000
        current_weight = sum(len(m.content or "") for m in history)
        
        if current_weight > MAX_PROMPT_CHARS:
            logger.warning(f"[{self.turn_id}] Running dynamic schema compression window.")
            for idx, msg in enumerate(history):
                if msg.role == "tool" and msg.content and len(msg.content) > 1000:
                    history[idx] = self._truncate_safely(msg)

        # Fire LLM request directly
        response = await self.voice.chat(
            history,
            tools=TOOL_DEFINITIONS,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens
        )
        
        self.total_tokens += response.total_tokens

        if not response.has_tool_calls:
            self.current_state = LoopState.COMPLETE
            return response.content or "", response.provider_name, "stop"

        # Cache the current execution target intent
        self._active_calls = response.tool_calls
        asst_msg = ChatMessage(role="assistant", content=response.content or "", tool_calls=response.tool_calls)
        history.append(asst_msg)
        self.new_tool_messages.append(asst_msg)

        self.current_state = LoopState.ACT
        return "", response.provider_name, "stop"

    async def _handle_act(self, history: List[ChatMessage]):
        """Dispatches tasks down across decoupled parallel processing jobs securely."""
        calls = getattr(self, "_active_calls", [])
        if not calls:
            self.current_state = LoopState.THINK
            return

        if self.config.parallel_tools and len(calls) > 1:
            tasks = [self._execute_single_call(tc) for tc in calls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = [await self._execute_single_call(tc) for tc in calls]

        # Standardize feedback channels back into the sequence history state
        for tc, output in zip(calls, results):
            if isinstance(output, Exception):
                output_str = f"Execution system engine fault: {str(output)}"
            else:
                output_str = output

            tool_msg = ChatMessage(role="tool", content=output_str, tool_call_id=tc["id"], name=tc["function"]["name"])
            history.append(tool_msg)
            self.new_tool_messages.append(tool_msg)
            self.tool_calls_total += 1

        self._active_calls = []
        self.current_state = LoopState.THINK

    async def _execute_single_call(self, tool_call: dict) -> str:
        """Executes a standalone transaction unit inside the isolated SINEW manager system."""
        fn = tool_call.get("function", {})
        name = fn.get("name", "")
        args_raw = fn.get("arguments", {})

        if isinstance(args_raw, str):
            try:
                args = json.loads(args_raw) if args_raw.strip() else {}
            except json.JSONDecodeError:
                return f"Fault: Context structure validation failed on json arguments parameter: {args_raw[:100]}"
        else:
            args = args_raw

        if self.bus:
            await self.bus.emit_nowait("cortex.tool.executing", {"turn_id": self.turn_id, "tool": name}, source="cortex")

        try:
            res = await self.tools.execute(name, args)
        except Exception as tool_fault:
            logger.error(f"[{self.turn_id}] Tool target system exception thrown on execution payload: {tool_fault}")
            res = f"Execution exception generated during core task routing logic: {str(tool_fault)}"

        if self.bus:
            await self.bus.emit_nowait("cortex.tool.done", {"turn_id": self.turn_id, "tool": name}, source="cortex")
        return res

    def _truncate_safely(self, target: ChatMessage) -> ChatMessage:
        """Converts runaway text blocks into valid structural segments without breaking syntax schemas."""
        raw_data = target.content or ""
        try:
            # Check if it's structural JSON data
            parsed = json.loads(raw_data)
            if isinstance(parsed, dict):
                # Retain structural root keys to prevent hallucination vectors
                summarized = {k: (v if len(str(v)) < 200 else f"[Truncated Attribute Data: {len(str(v))} chars]") for k, v in parsed.items()}
                content = json.dumps(summarized)
            else:
                content = raw_data[:800] + "\n... [Context safety slice executed] ..."
        except Exception:
            content = raw_data[:800] + "\n... [Context safety slice executed] ..."

        return ChatMessage(role=target.role, content=content, tool_call_id=target.tool_call_id, name=target.name)