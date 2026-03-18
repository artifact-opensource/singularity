"""
VOICE — Copilot Proxy Provider
=================================

GitHub Copilot token exchange → OpenAI-compatible streaming API.

Flow:
    1. Resolve GitHub PAT (env vars, hosts.json, gh CLI)
    2. Exchange PAT → Copilot session token (cached, ~30 min TTL)
    3. Use session token against OpenAI-compatible Copilot API
    4. Stream SSE response → yield StreamChunks

This is a direct Python port of Mach6's github-copilot.ts + openai.ts,
adapted for the Singularity provider abstraction.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import AsyncIterator, Optional

import aiohttp

from .provider import ChatProvider, ChatMessage, ChatResponse, StreamChunk

logger = logging.getLogger("singularity.voice.proxy")

COPILOT_TOKEN_URL = "https://api.github.com/copilot_internal/v2/token"
DEFAULT_BASE_URL = "https://api.individual.githubcopilot.com"
TOKEN_CACHE_PATH = Path.home() / ".mach6" / "credentials" / "github-copilot.token.json"

# Also check Mach6's cache (shared machine, same token)
MACH6_TOKEN_CACHE = Path.home() / ".mach6" / "credentials" / "github-copilot.token.json"

# Copilot headers that identify us as a VS Code Copilot client
COPILOT_HEADERS = {
    "Editor-Version": "vscode/1.96.2",
    "User-Agent": "GitHubCopilotChat/0.26.7",
    "Copilot-Integration-Id": "vscode-chat",
    "Openai-Intent": "conversation-panel",
}


class CopilotProxyProvider(ChatProvider):
    """GitHub Copilot as an OpenAI-compatible LLM provider.
    
    Two modes:
    1. Proxy mode (default): Uses a running Mach6 gateway's Copilot proxy at localhost:3000
    2. Direct mode: Does its own PAT → Copilot token exchange (requires OAuth token, not classic PAT)
    
    Proxy mode is preferred when running alongside Mach6 on the same machine.
    """
    
    def __init__(self, model: str = "claude-opus-4.6-fast", endpoint: str = None, **kwargs):
        super().__init__(name="copilot-proxy", model=model, **kwargs)
        self._cached_token: Optional[dict] = None  # {token, expires_at, updated_at}
        self._session: Optional[aiohttp.ClientSession] = None
        # If endpoint provided, use proxy mode (Mach6 gateway handles auth)
        self._proxy_endpoint: Optional[str] = endpoint
        self._base_url: str = DEFAULT_BASE_URL
    
    async def initialize(self) -> None:
        """Create HTTP session."""
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300)
            )
    
    async def shutdown(self) -> None:
        """Close HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    # ── Token Management ──────────────────────────────────────────
    
    def _resolve_github_token(self) -> str:
        """Resolve a GitHub PAT from various sources."""
        # 1. Copilot-specific env var
        token = os.environ.get("COPILOT_GITHUB_TOKEN", "").strip()
        if token:
            return token
        
        # 2. Copilot CLI token
        cli_path = Path.home() / ".copilot-cli-access-token"
        if cli_path.exists():
            token = cli_path.read_text().strip()
            if token:
                return token
        
        # 3. General GitHub env vars
        token = os.environ.get("GH_TOKEN", "") or os.environ.get("GITHUB_TOKEN", "")
        if token.strip():
            return token.strip()
        
        # 4. hosts.json (Copilot VS Code extension)
        hosts_path = Path.home() / ".config" / "github-copilot" / "hosts.json"
        if hosts_path.exists():
            try:
                hosts = json.loads(hosts_path.read_text())
                for key in hosts:
                    oauth = hosts[key].get("oauth_token")
                    if oauth:
                        return oauth
            except Exception as e:
                logger.debug(f"Suppressed: {e}")
        
        # 5. gh CLI
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.debug(f"Suppressed: {e}")
        
        raise RuntimeError(
            "No GitHub token found for Copilot. "
            "Set GITHUB_TOKEN, GH_TOKEN, or COPILOT_GITHUB_TOKEN, "
            "or run: gh auth login"
        )
    
    def _load_cached_token(self) -> Optional[dict]:
        """Load cached copilot token from disk."""
        for cache_path in [TOKEN_CACHE_PATH, MACH6_TOKEN_CACHE]:
            try:
                if cache_path.exists():
                    data = json.loads(cache_path.read_text())
                    token = data.get("token")
                    # Handle both camelCase (Mach6) and snake_case field names
                    expires_at = data.get("expires_at") or data.get("expiresAt")
                    if token and expires_at:
                        return {"token": token, "expires_at": expires_at}
            except Exception as e:
                logger.debug(f"Suppressed: {e}")
        return None
    
    def _save_cached_token(self, token_data: dict) -> None:
        """Save copilot token to disk cache."""
        try:
            TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_CACHE_PATH.write_text(json.dumps(token_data, indent=2))
        except Exception as e:
            logger.debug(f"Suppressed: {e}")
    
    def _is_token_usable(self, token_data: dict) -> bool:
        """Check if token has >5 min remaining."""
        expires_at = token_data.get("expires_at", 0)
        # Normalize to ms
        if expires_at < 10_000_000_000:
            expires_at *= 1000
        return (expires_at - time.time() * 1000) > 5 * 60 * 1000
    
    def _derive_base_url(self, token: str) -> str:
        """Extract base URL from copilot token (proxy-ep field)."""
        match = re.search(r"(?:^|;)\s*proxy-ep=([^;\s]+)", token, re.IGNORECASE)
        if match:
            ep = match.group(1).strip()
            host = re.sub(r"^https?://", "", ep)
            host = re.sub(r"^proxy\.", "api.", host, flags=re.IGNORECASE)
            return f"https://{host}"
        return DEFAULT_BASE_URL
    
    async def _resolve_copilot_token(self) -> tuple[str, str]:
        """Get a valid copilot session token. Returns (token, base_url)."""
        # Check memory cache
        if self._cached_token and self._is_token_usable(self._cached_token):
            t = self._cached_token["token"]
            return t, self._derive_base_url(t)
        
        # Check disk cache
        disk = self._load_cached_token()
        if disk and self._is_token_usable(disk):
            self._cached_token = disk
            return disk["token"], self._derive_base_url(disk["token"])
        
        # Exchange GitHub PAT for copilot session token
        gh_token = self._resolve_github_token()
        
        await self.initialize()
        async with self._session.get(
            COPILOT_TOKEN_URL,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {gh_token}",
            },
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Copilot token exchange failed: HTTP {resp.status}: {text}")
            
            data = await resp.json()
        
        token = data["token"]
        expires_at = data.get("expires_at", 0)
        if expires_at < 10_000_000_000:
            expires_at *= 1000
        
        entry = {
            "token": token,
            "expires_at": expires_at,
            "updated_at": time.time() * 1000,
        }
        self._cached_token = entry
        self._save_cached_token(entry)
        
        return token, self._derive_base_url(token)
    
    # ── Chat Streaming ────────────────────────────────────────────
    
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream a chat completion via Copilot's OpenAI-compatible API."""
        
        # Proxy mode: use Mach6 gateway which handles its own Copilot auth
        if self._proxy_endpoint:
            async for chunk in self._stream_via_proxy(
                messages, tools, temperature, max_tokens, **kwargs
            ):
                yield chunk
            return
        
        # Direct mode: do our own token exchange
        attempts = 0
        while attempts < 2:
            try:
                token, base_url = await self._resolve_copilot_token()
                async for chunk in self._stream_openai(
                    messages, tools, token, base_url,
                    temperature, max_tokens, **kwargs
                ):
                    yield chunk
                self.record_success()
                return
            except Exception as e:
                if attempts == 0 and "401" in str(e):
                    logger.warning("Copilot token expired mid-stream, refreshing...")
                    self._cached_token = None
                    attempts += 1
                    continue
                self.record_failure(e)
                raise
    
    def _build_request_body(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict]],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        """Build the OpenAI-compatible request body (shared by proxy + direct)."""
        body: dict = {
            "model": self.model,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [m.to_dict() for m in messages],
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if tools:
            body["tools"] = tools
        return body
    
    @staticmethod
    def _parse_sse_chunk(parsed: dict) -> list[StreamChunk]:
        """Parse a single SSE JSON object into StreamChunks.
        
        Returns a list (usually 0-2 chunks) to avoid repeated yield logic.
        Shared by both proxy and direct streaming paths.
        """
        chunks: list[StreamChunk] = []
        
        # Usage chunk
        usage = parsed.get("usage")
        if usage and usage.get("total_tokens"):
            chunks.append(StreamChunk(
                usage={
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                }
            ))
        
        choices = parsed.get("choices")
        if not choices:
            return chunks
        
        choice = choices[0]
        delta = choice.get("delta")
        if not delta:
            # Check finish_reason even without delta
            finish = choice.get("finish_reason")
            if finish:
                chunks.append(StreamChunk(finish_reason=finish))
            return chunks
        
        # Text content
        content = delta.get("content")
        if content:
            chunks.append(StreamChunk(delta=content))
        
        # Tool calls
        tc_list = delta.get("tool_calls")
        if tc_list:
            for tc in tc_list:
                fn = tc.get("function", {})
                chunks.append(StreamChunk(tool_call_delta={
                    "index": tc.get("index", 0),
                    "id": tc.get("id", ""),
                    "function": {
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", ""),
                    },
                }))
        
        # Finish reason
        finish = choice.get("finish_reason")
        if finish:
            chunks.append(StreamChunk(finish_reason=finish))
        
        return chunks
    
    async def _stream_sse_response(self, resp: aiohttp.ClientResponse) -> AsyncIterator[StreamChunk]:
        """Parse an SSE response stream into StreamChunks.
        
        Shared by both proxy and direct streaming paths.
        Handles buffering, line splitting, JSON parsing, and chunk emission.
        """
        buffer = ""
        async for raw_bytes in resp.content.iter_any():
            buffer += raw_bytes.decode("utf-8", errors="replace")
            
            # Split on newlines, keep incomplete tail
            lines = buffer.split("\n")
            buffer = lines[-1]  # Keep the last (possibly incomplete) segment
            
            for line in lines[:-1]:
                if not line.startswith("data: "):
                    continue
                data = line[6:].strip()
                
                if data == "[DONE]":
                    return
                
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError as e:
                    logger.debug(f"Suppressed json.JSONDecodeError: {e}")
                    continue
                
                for chunk in self._parse_sse_chunk(parsed):
                    yield chunk
    
    async def _stream_via_proxy(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict]],
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream via the Mach6 Copilot proxy (localhost:3000)."""
        await self.initialize()
        
        body = self._build_request_body(messages, tools, temperature, max_tokens)
        endpoint = f"{self._proxy_endpoint.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json", **COPILOT_HEADERS}
        
        chunk_count = 0
        try:
            async with self._session.post(endpoint, json=body, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Proxy API error {resp.status}: {text}")
                
                async for chunk in self._stream_sse_response(resp):
                    chunk_count += 1
                    yield chunk
            
            if chunk_count == 0:
                logger.warning(f"Proxy returned 200 but 0 chunks — possible silent failure. Messages: {len(messages)}, model: {body.get('model')}")
                raise RuntimeError(f"Proxy returned 0 chunks for model {body.get('model')} — triggering fallback")
            
            self.record_success()
        except Exception as e:
            self.record_failure(e)
            raise
    
    async def _stream_openai(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict]],
        token: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Raw OpenAI SSE streaming."""
        await self.initialize()
        
        body = self._build_request_body(messages, tools, temperature, max_tokens)
        
        # Endpoint (Copilot doesn't use /v1 prefix)
        if "githubcopilot.com" in base_url or "localhost" in base_url:
            endpoint = f"{base_url}/chat/completions"
        else:
            endpoint = f"{base_url}/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            **COPILOT_HEADERS,
        }
        
        async with self._session.post(endpoint, json=body, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"OpenAI API error {resp.status}: {text}")
            
            async for chunk in self._stream_sse_response(resp):
                yield chunk
    
    # ── Health Check ──────────────────────────────────────────────
    
    async def health(self) -> bool:
        """Check if we can reach the LLM backend."""
        try:
            if self._proxy_endpoint:
                # Proxy mode: check if Mach6 gateway is responding
                await self.initialize()
                async with self._session.get(
                    f"{self._proxy_endpoint.rstrip('/')}/models",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    return resp.status == 200
            else:
                # Direct mode: check if we have a valid copilot token
                await self._resolve_copilot_token()
                return True
        except Exception:
            return False
