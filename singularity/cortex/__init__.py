"""CORTEX — Brain subsystem (engine + agent loop + context assembly + blink)."""

from .agent import CortexEngine, AgentConfig, TurnResult
from .blink import BlinkController, BlinkConfig, BlinkState, BlinkPhase
from .context import ContextAssembler, build_system_prompt, compress_tool_results, extract_archive_summary
from .engine import CortexEngine, CortexConfig

__all__ = [
    "CortexEngine", "CortexConfig",
    "AgentLoop", "AgentConfig", "TurnResult",
    "BlinkController", "BlinkConfig", "BlinkState", "BlinkPhase",
    "ContextAssembler", "build_system_prompt", "compress_tool_results", "extract_archive_summary",
]
