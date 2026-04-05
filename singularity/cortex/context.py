"""
CORTEX — Context Assembly
============================

Assembles the context window for each agent turn:
    1. System prompt (persona + tools + rules)
    2. Session history (from MEMORY)
    3. New message

Context window management:
    - Token budget tracking
    - History truncation (oldest first)
    - Compaction trigger (summarize old context)
    - System prompt is never truncated
"""

from __future__ import annotations

import logging
from typing import Optional

from ..voice.provider import ChatMessage

logger = logging.getLogger("singularity.cortex.context")

# Default token budgets (conservative — leaves room for response)
DEFAULT_CONTEXT_BUDGET = 75_000  # Max tokens for context (matches singularity.yaml)
SYSTEM_PROMPT_BUDGET = 10_000     # Reserved for system prompt
RESPONSE_BUDGET = 8_192           # Reserved for response


class ContextAssembler:
    """Assemble and manage the context window.
    
    Responsibilities:
    - Build system prompt from persona definition
    - Retrieve session history from MEMORY
    - Enforce token budget (truncate if needed)
    - Signal when compaction is needed
    """
    
    def __init__(
        self,
        context_budget: int = DEFAULT_CONTEXT_BUDGET,
        response_budget: int = RESPONSE_BUDGET,
    ):
        self.context_budget = context_budget
        self.response_budget = response_budget
    
    def assemble(
        self,
        system_prompt: str,
        history: list[ChatMessage],
        new_message: Optional[ChatMessage] = None,
        max_history_tokens: Optional[int] = None,
    ) -> list[ChatMessage]:
        """Assemble the full message list for an LLM call.
        
        Args:
            system_prompt: The system prompt text
            history: Previous messages in this session
            new_message: The new incoming message (if any)
            max_history_tokens: Override max tokens for history
        
        Returns:
            List of ChatMessages ready for the LLM
        """
        messages = []
        
        # 1. System prompt (always first, never truncated)
        if system_prompt:
            messages.append(ChatMessage(role="system", content=system_prompt))
        
        # 2. History (may be truncated)
        if max_history_tokens:
            available_budget = max_history_tokens
        else:
            # Reserve space for system prompt (estimate) and response
            # Use conservative 3.2 chars/token to avoid exceeding model limits
            sys_tokens = int(len(system_prompt) / 3.2) if system_prompt else 0
            available_budget = max(
                0,
                self.context_budget - sys_tokens - self.response_budget
            )
        
        truncated_history = self._fit_history(history, available_budget)
        messages.extend(truncated_history)
        
        # 3. New message
        if new_message:
            messages.append(new_message)
        
        return messages
    
    @staticmethod
    def _estimate_message_chars(msg: ChatMessage) -> int:
        """Estimate the character cost of a message, including tool_calls metadata."""
        chars = len(msg.content or "")
        if msg.tool_calls:
            for tc in msg.tool_calls:
                # Count actual argument sizes — these dominate token count
                fn = tc.get("function", tc)
                args = fn.get("arguments", fn.get("input", ""))
                if isinstance(args, dict):
                    # Sum values — faster than json.dumps
                    chars += sum(len(str(v)) for v in args.values()) + 100
                elif isinstance(args, str):
                    chars += len(args) + 100
                else:
                    chars += 200
                # Function name + id overhead
                chars += len(str(fn.get("name", ""))) + 80
        if msg.tool_call_id:
            chars += len(msg.tool_call_id) + 20
        if msg.name:
            chars += len(msg.name) + 10
        return chars
    
    def _fit_history(
        self,
        history: list[ChatMessage],
        budget_tokens: int,
    ) -> list[ChatMessage]:
        """Fit history into the token budget.
        
        Strategy: Keep the most recent messages. Drop oldest first.
        Estimate: ~4 chars per token (rough but fast).
        Preserves tool call integrity: assistant tool_calls messages and
        their corresponding tool result messages are kept/dropped as a unit.
        
        TODO: Use proper tokenizer when GLADIUS provides one.
        """
        if not history:
            return []
        
        # Estimate tokens (conservative: 3.2 chars ≈ 1 token — accounts for
        # tool call JSON, metadata, special tokens that inflate real token count)
        budget_chars = int(budget_tokens * 3.2)
        
        # Calculate total size (including tool_calls metadata)
        total_chars = sum(self._estimate_message_chars(m) for m in history)
        
        if total_chars <= budget_chars:
            return list(history)  # Everything fits
        
        # Group messages into "units" that must stay together:
        # An assistant message with tool_calls + all following tool results = one unit
        units: list[list[int]] = []  # each unit is a list of indices
        i = 0
        while i < len(history):
            msg = history[i]
            if msg.role == "assistant" and msg.tool_calls:
                # Start a unit: this assistant msg + all following tool results
                unit = [i]
                j = i + 1
                while j < len(history) and history[j].role == "tool":
                    unit.append(j)
                    j += 1
                units.append(unit)
                i = j
            else:
                units.append([i])
                i += 1
        
        # Walk backwards (newest units first), keeping units that fit
        keep_from = len(units)  # Index into units list: keep units[keep_from:]
        running_chars = 0
        
        for i in range(len(units) - 1, -1, -1):
            unit_chars = sum(self._estimate_message_chars(history[idx]) for idx in units[i])
            if running_chars + unit_chars > budget_chars:
                break
            keep_from = i
            running_chars += unit_chars
        
        # Flatten kept units to message indices and build result
        result = []
        for unit in units[keep_from:]:
            for idx in unit:
                result.append(history[idx])
        
        if len(result) < len(history):
            dropped = len(history) - len(result)
            logger.info(
                f"Context truncation: dropped {dropped} oldest messages "
                f"({total_chars - running_chars} chars)"
            )
            
            # Prepend a note about truncation
            if result and result[0].role != "system":
                note = ChatMessage(
                    role="system",
                    content=f"[Context note: {dropped} earlier messages were truncated to fit the context window.]"
                )
                result.insert(0, note)
        
        return result
    
    def needs_compaction(
        self,
        history: list[ChatMessage],
        threshold: float = 0.8,
    ) -> bool:
        """Check if history should be compacted.
        
        Returns True if history uses more than `threshold` of the budget.
        """
        if not history:
            return False
        
        budget_chars = int(self.context_budget * 3.2)  # conservative token estimate
        total_chars = sum(self._estimate_message_chars(m) for m in history)
        
        return total_chars > (budget_chars * threshold)


# ── Layer 2: Tool Result Compression ─────────────────────────────
# After the LLM has consumed tool results (in prior iterations),
# compress large results to summaries. Saves context budget.

COMPRESS_THRESHOLD = 500  # chars — don't compress small results
PRESERVED_TOOLS = {"comb_recall", "comb_stage"}  # Never compress these


def compress_tool_results(
    messages: list[ChatMessage],
    current_iteration: int,
) -> list[ChatMessage]:
    """Compress tool results from previous iterations.
    
    Only compresses tool results that the LLM has already seen
    (i.e., not the results from the most recent tool call batch).
    
    Compression rules:
    - `read` → "[Read: X bytes, Y lines — consumed]"
    - `exec` → keep first 3 + last 3 lines, omit middle
    - `web_fetch` → "[Web fetch: X bytes — consumed]"
    - `comb_recall` / `comb_stage` → preserved intact
    - Other tools > 2000 chars → truncate with summary
    - Results ≤ COMPRESS_THRESHOLD → preserved
    
    Args:
        messages: Current message list (mutated in place for efficiency)
        current_iteration: Current iteration number (1-indexed)
    
    Returns:
        The messages list (same reference, mutated)
    """
    if current_iteration <= 1:
        return messages  # Nothing to compress on first iteration
    
    # Find the boundary: we want to compress tool results that appeared
    # BEFORE the most recent assistant→tool cycle.
    # Walk backwards to find the last assistant message with tool_calls
    last_tc_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].role == "assistant" and messages[i].tool_calls:
            last_tc_idx = i
            break
    
    if last_tc_idx < 0:
        return messages  # No tool calls found
    
    # Compress all tool results BEFORE last_tc_idx
    for i in range(last_tc_idx):
        msg = messages[i]
        if msg.role != "tool" or not msg.content:
            continue
        
        content = msg.content
        if len(content) <= COMPRESS_THRESHOLD:
            continue
        
        tool_name = msg.name or ""
        
        # Preserved tools — never compress
        if tool_name in PRESERVED_TOOLS:
            continue
        
        # Compress based on tool type
        if tool_name == "read":
            lines = content.count("\n") + 1
            messages[i] = ChatMessage(
                role="tool",
                content=f"[Read: {len(content)} bytes, {lines} lines — consumed]",
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        elif tool_name == "exec":
            lines = content.split("\n")
            if len(lines) > 8:
                head = "\n".join(lines[:3])
                tail = "\n".join(lines[-3:])
                omitted = len(lines) - 6
                messages[i] = ChatMessage(
                    role="tool",
                    content=f"{head}\n... [{omitted} lines omitted] ...\n{tail}",
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
        elif tool_name == "web_fetch":
            messages[i] = ChatMessage(
                role="tool",
                content=f"[Web fetch: {len(content)} bytes — consumed]",
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
        elif len(content) > 2000:
            # Generic large result — truncate
            messages[i] = ChatMessage(
                role="tool",
                content=f"{content[:500]}\n... [{len(content) - 500} chars truncated — consumed]",
                tool_call_id=msg.tool_call_id,
                name=msg.name,
            )
    
    return messages


# ── Layer 3: Smart Archive Summary ──────────────────────────────
# When messages are compacted/archived, extract a summary of what
# happened so context retains key info after compaction.

def extract_archive_summary(messages: list[ChatMessage]) -> str:
    """Extract a compact summary from messages being archived.
    
    Captures:
    - Files read/written
    - Commands run
    - Tools used (with counts)
    - Key assistant findings (first sentence of text responses)
    
    Returns a summary string suitable for injection as a system message.
    """
    files_read = []
    files_written = []
    commands_run = []
    tools_used: dict[str, int] = {}
    key_findings = []
    
    for msg in messages:
        if msg.role == "tool" and msg.name:
            # Count tool usage
            tools_used[msg.name] = tools_used.get(msg.name, 0) + 1
        
        if msg.role == "assistant" and msg.tool_calls:
            for tc in msg.tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                args_raw = fn.get("arguments", "")
                
                # Parse arguments safely
                if isinstance(args_raw, str):
                    try:
                        import json
                        args = json.loads(args_raw) if args_raw else {}
                    except (json.JSONDecodeError, ValueError):
                        args = {}
                elif isinstance(args_raw, dict):
                    args = args_raw
                else:
                    args = {}
                
                if name == "read" and "path" in args:
                    files_read.append(args["path"])
                elif name in ("write", "edit") and "path" in args:
                    files_written.append(args["path"])
                elif name == "exec" and "command" in args:
                    cmd = args["command"]
                    if len(cmd) > 80:
                        cmd = cmd[:77] + "..."
                    commands_run.append(cmd)
        
        # Extract key findings from assistant text responses
        if msg.role == "assistant" and msg.content and not msg.tool_calls:
            text = msg.content.strip()
            if text and len(text) > 10:
                # First sentence or first 150 chars
                first_sentence = text.split(". ")[0]
                if len(first_sentence) > 150:
                    first_sentence = first_sentence[:147] + "..."
                key_findings.append(first_sentence)
    
    # Build summary
    parts = ["[Archive Summary — prior context was compacted]"]
    
    if files_read:
        # Deduplicate, keep order
        seen = set()
        unique = [f for f in files_read if f not in seen and not seen.add(f)]
        parts.append(f"Files read: {', '.join(unique[:15])}")
    
    if files_written:
        seen = set()
        unique = [f for f in files_written if f not in seen and not seen.add(f)]
        parts.append(f"Files written: {', '.join(unique[:10])}")
    
    if commands_run:
        parts.append(f"Commands run ({len(commands_run)}): {'; '.join(commands_run[:8])}")
    
    if tools_used:
        tool_summary = ", ".join(f"{k}×{v}" for k, v in sorted(tools_used.items(), key=lambda x: -x[1])[:10])
        parts.append(f"Tools used: {tool_summary}")
    
    if key_findings:
        parts.append(f"Key findings: {' | '.join(key_findings[:5])}")
    
    return "\n".join(parts)


def build_system_prompt(
    persona_name: str,
    persona_prompt: str = "",
    tools_description: str = "",
    rules: str = "",
    comb_context: str = "",
    workspace: str = "",
) -> str:
    """Build a complete system prompt from components.
    
    This is where the persona's personality gets injected.
    Includes hard grounding to prevent hallucination and confabulation.
    """
    from datetime import datetime
    
    now = datetime.now()
    parts = []
    
    # ── Grounding header (date, time, platform, workspace) ──
    header = (
        f"Current date: {now.strftime('%A, %B %d, %Y')}\n"
        f"Current time: {now.strftime('%H:%M %Z')}\n"
    )
    if workspace:
        header += f"Workspace: {workspace}\n"
    header += "Platform: Discord (Singularity runtime)\n"
    header += "Formatting: NO markdown tables, NO headers (#), NO code blocks for non-code. Use bullet lists and **bold**. You are posting to chat, not rendering documents.\n"
    parts.append(header)
    
    # ── Identity (from loaded files or fallback) ──
    if persona_prompt:
        parts.append(persona_prompt)
    else:
        parts.append(f"You are {persona_name}.")
    
    # ── Cognitive Rails (tight, performance-oriented) ──
    cognitive_rails = (
        "## Cognitive Rules\n"
        "1. **Tool-first.** Check before claiming. Read files, run commands, search memory — never guess system state or file contents.\n"
        "2. **Never fabricate.** If you don't know, say so. No confident wrong answers.\n"
        "3. **Act, don't narrate.** Fix problems in the same turn you find them. Don't describe what should change — make the change.\n"
        "4. **Execute, don't ask.** You are autonomous. Take action and report results. Don't ask 'should I do X?' — do X.\n"
        "5. **Be concise.** Results over explanations. One investigation, one report. No padding, no filler.\n"
    )
    parts.append(cognitive_rails)

    # ── Brutalist Mandate (operational backbone) ──
    brutalist = (
        "## Brutalist Mandate\n"
        "You are the operational backbone of Artifact Virtual. No margin for error.\n\n"
        "**Standards:** Audit everything. Fragile processes get called out. Silent failures are double failures.\n"
        "**Code:** No sloppy merges, no undocumented changes. 'It works' ≠ 'it's good.'\n"
        "**Truth:** Ali gets unfiltered truth. If he's wrong, tell him — with evidence. Same standard applies to everything and everyone.\n"
        "**Delivery:** Deadlines are real. Blockers get escalated immediately, not mentioned in passing.\n"
    )
    parts.append(brutalist)
    
    if rules:
        parts.append(f"## Operating Rules\n{rules}")
    
    if tools_description:
        parts.append(f"## Available Tools\n{tools_description}")
    
    if comb_context:
        # Cap COMB to prevent system prompt from exceeding model context limits
        # 290K chars of COMB = ~72K tokens, which alone exceeds Copilot's 128K limit
        MAX_COMB_CHARS = 20_000  # ~5K tokens — enough for recent operational context
        if len(comb_context) > MAX_COMB_CHARS:
            comb_context = comb_context[:MAX_COMB_CHARS] + f"\n\n[... truncated — {len(comb_context) - MAX_COMB_CHARS} chars omitted]"
        parts.append(
            f"## Operational Memory (COMB Recall)\n"
            f"The following is your recalled persistent memory from previous sessions. "
            f"This is ground truth about past events.\n\n{comb_context}"
        )
    
    return "\n\n".join(parts)
