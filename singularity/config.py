"""
SPINE — Configuration System
==============================

Hot-reloadable YAML/JSON configuration with validation.

Features:
    - Pydantic-validated models
    - YAML or JSON config files
    - Hot-reload via file watcher (inotify on Linux)
    - Event bus integration (publishes config.loaded, config.reloaded)
    - Environment variable overrides
    - Persona definitions for C-Suite and channel routing

Config hierarchy:
    1. Default values (in Pydantic models)
    2. Config file (singularity.yaml)
    3. Environment variables (SINGULARITY_*)
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger("singularity.config")

# ── Default paths ──────────────────────────────────────────────────
DEFAULT_CONFIG_DIR = Path(os.environ.get(
    "SINGULARITY_HOME", 
    str(Path(__file__).parent.parent / "config")
))
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "singularity.yaml"


# ── Configuration Models ──────────────────────────────────────────

class ProxyConfig(BaseModel):
    """LLM proxy configuration (copilot_proxy)."""
    base_url: str = "http://localhost:3000/v1"
    api_key: str = "n/a"
    timeout: float = 120.0


class OllamaConfig(BaseModel):
    """Local Ollama fallback configuration."""
    enabled: bool = False
    base_url: str = "http://localhost:11434"
    models: list[str] = Field(default_factory=lambda: ["qwen35-opus"])
    timeout: float = 120.0


class OllamaCloudConfig(BaseModel):
    """Ollama Cloud hosted API configuration."""
    enabled: bool = False
    model: str = "deepseek-v3.2"
    api_key: str = ""  # Falls back to OLLAMA_CLOUD_API_KEY env var
    base_url: str = "https://ollama.com/v1"
    timeout: float = 120.0


class VoiceConfig(BaseModel):
    """LLM provider configuration."""
    primary_model: str = "claude-opus-4.6"
    fallback_models: list[str] = Field(default_factory=lambda: ["gemini-2.0-flash", "gpt-4.1-mini"])
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    ollama_cloud: OllamaCloudConfig = Field(default_factory=OllamaCloudConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    temperature: float = 0.5
    max_tokens: int = 4096


class DiscordConfig(BaseModel):
    """Discord connection configuration."""
    token: str = ""
    guild_ids: list[str] = Field(default_factory=list)
    bot_user_id: str = ""
    dm_policy: str = "allowlist"
    dm_allowlist: list[str] = Field(default_factory=list)
    authorized_users: list[str] = Field(default_factory=list)
    # Day 21: sibling_bot_ids kept for Discord adapter (filters random bots,
    # lets known siblings through to the router's @mention check)
    sister_bot_ids: list[str] = Field(default_factory=list)
    status_message: str = "⚡ Singularity Online"
    max_message_length: int = 2000
    reconnect_delay: float = 5.0
    max_reconnect_delay: float = 300.0


class MemoryConfig(BaseModel):
    """MEMORY configuration."""
    comb_store_path: str = ""  # Path to COMB store directory
    session_db: str = ""       # Path to sessions.db
    max_context_tokens: int = 100_000
    target_tokens: int = 60_000
    compaction_enabled: bool = True
    recall_on_boot: bool = True


class ToolsConfig(BaseModel):
    """SINEW tools configuration."""
    workspace: str = str(Path.home() / "workspace" / "enterprise")
    exec_timeout: int = 30
    exec_max_output: int = 50_000
    allowed_paths: list[str] = Field(default_factory=lambda: ["/home/adam"])
    blocked_commands: list[str] = Field(default_factory=lambda: [
        "rm -rf /", "mkfs", "dd if=", ":(){ :|:& };:",
    ])


class PulseConfig(BaseModel):
    """PULSE iteration budget configuration."""
    default_cap: int = 20
    expanded_cap: int = 100
    expand_threshold: int = 18
    revert_window: int = 3
    revert_threshold: int = 10


class BlinkConfig(BaseModel):
    """BLINK seamless continuation configuration."""
    enabled: bool = True
    max_depth: int = 10         # Max consecutive blinks per conversation turn
    prepare_at: int = 3         # Inject preparation message at N remaining iterations
    flush_at: int = 1           # Force flush at N remaining
    cooldown_seconds: float = 1.0  # Delay between blink and resume


class ImmuneConfig(BaseModel):
    """IMMUNE health system configuration."""
    check_interval: float = 30.0
    max_restart_attempts: int = 5
    restart_window: int = 300
    alert_channels: list[str] = Field(default_factory=list)
    poa_scripts_dir: str = ""


class PersonaConfig(BaseModel):
    """An agent persona (for C-Suite or channel routing)."""
    name: str
    channel_ids: list[str] = Field(default_factory=list)
    system_prompt_files: list[str] = Field(default_factory=list)
    system_prompt_inline: str = ""
    model: str = ""
    base_url: str = ""
    authorized_users: Optional[list[str]] = None
    workspace: str = ""
    tools_enabled: bool = True
    max_iterations: int = 0  # 0 = use default
    # Executive role metadata (used by deployer for channel topics + webhooks)
    emoji: str = ""          # e.g. "🔧" — auto-filled from role defaults if empty
    title: str = ""          # e.g. "Chief Technology Officer" — auto-filled if empty
    domain: str = ""         # e.g. "Engineering, infrastructure..." — auto-filled if empty


class CSuiteConfig(BaseModel):
    """C-Suite executive agent configuration."""
    enabled: bool = True
    executive_model: str = "claude-sonnet-4"  # Lighter model for exec agents (vs Opus coordinator)
    personas: list[PersonaConfig] = Field(default_factory=list)
    report_dir: str = str(Path.home() / "workspace" / "enterprise" / "executives")


class CompactionConfig(BaseModel):
    """Session compaction configuration."""
    enabled: bool = True
    summary_model: str = ""  # empty = use primary


class SingularityConfig(BaseModel):
    """Root configuration for Singularity runtime."""
    model_config = {"extra": "allow"}
    
    # Subsystem configs
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    discord: DiscordConfig = Field(default_factory=DiscordConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    tools: ToolsConfig = Field(default_factory=ToolsConfig)
    pulse: PulseConfig = Field(default_factory=PulseConfig)
    blink: BlinkConfig = Field(default_factory=BlinkConfig)
    immune: ImmuneConfig = Field(default_factory=ImmuneConfig)
    csuite: CSuiteConfig = Field(default_factory=CSuiteConfig)
    compaction: CompactionConfig = Field(default_factory=CompactionConfig)
    
    # Persona routing
    personas: list[PersonaConfig] = Field(default_factory=list)
    
    # Identity
    identity_files: list[str] = Field(default_factory=lambda: [
        "AGENTS.md",
    ])
    
    # Runtime
    log_level: str = "INFO"
    pid_file: str = ""
    
    def get_persona(self, name: str) -> PersonaConfig | None:
        """Find a persona by name."""
        for p in self.personas:
            if p.name.lower() == name.lower():
                return p
        for p in self.csuite.personas:
            if p.name.lower() == name.lower():
                return p
        return None
    
    def route_channel(self, channel_id: str) -> PersonaConfig | None:
        """Find the persona assigned to a channel."""
        for p in self.personas:
            if channel_id in p.channel_ids:
                return p
        for p in self.csuite.personas:
            if channel_id in p.channel_ids:
                return p
        return None


# ── Config Loading ──────────────────────────────────────────────────

def load_config(path: Path | str | None = None) -> SingularityConfig:
    """Load configuration from YAML or JSON file.
    
    Falls back to defaults if file doesn't exist.
    Supports environment variable overrides:
        SINGULARITY_DISCORD_TOKEN → discord.token
        SINGULARITY_LOG_LEVEL → log_level
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_FILE
    
    data: dict[str, Any] = {}
    
    if config_path.exists():
        raw = config_path.read_text(encoding="utf-8")
        
        if config_path.suffix in (".yaml", ".yml"):
            try:
                import yaml
                data = yaml.safe_load(raw) or {}
            except ImportError:
                logger.warning("PyYAML not installed, trying JSON fallback")
                data = json.loads(raw)
        else:
            data = json.loads(raw)
        
        logger.info("Config loaded from %s", config_path)
    else:
        logger.warning("Config file not found at %s, using defaults", config_path)
    
    # Environment variable overrides
    env_overrides = {
        "SINGULARITY_DISCORD_TOKEN": ("discord", "token"),
        "SINGULARITY_LOG_LEVEL": ("log_level",),
        "SINGULARITY_WORKSPACE": ("tools", "workspace"),
    }
    
    for env_key, path_parts in env_overrides.items():
        value = os.environ.get(env_key)
        if value:
            _set_nested(data, path_parts, value)
            logger.debug("Override from env: %s", env_key)
    
    return SingularityConfig(**data)


def _set_nested(data: dict, path: tuple[str, ...], value: Any) -> None:
    """Set a nested dictionary value by path tuple."""
    for key in path[:-1]:
        data = data.setdefault(key, {})
    data[path[-1]] = value
