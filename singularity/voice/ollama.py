"""
VOICE — Ollama Local Provider
================================

Local LLM fallback via Ollama (localhost:11434).

When the cloud is unreachable — missiles overhead, internet down,
API quotas exhausted — Ollama is the qorvex option.
Smaller models, but fully autonomous.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import aiohttp

from .provider import ChatProvider, ChatMessage, StreamChunk

logger = logging.getLogger("singularity.voice.ollama")

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaProvider(ChatProvider):
    """Local Ollama LLM provider.
    
    Uses the /api/chat endpoint with streaming.
    Tool calling support depends on the model.
    """
    
    def __init__(self, model: str = "llama3.2", base_url: str = DEFAULT_OLLAMA_URL, **kwargs):
        super().__init__(name="ollama", model=model, **kwargs)
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self) -> None:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300)  # Local models can be slow
            )
    
    async def shutdown(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
    
    async def chat_stream(
        self,
        messages: list[ChatMessage],
        tools: Optional[list[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        """Stream chat via Ollama /api/chat."""
        await self.initialize()
        
        # Convert messages, then fix tool_call arguments for Ollama.
        # to_dict() serializes arguments as JSON strings (OpenAI format),
        # but Ollama expects them as native dicts.
        raw_messages = [m.to_dict() for m in messages]
        for msg in raw_messages:
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    fn = tc.get("function", {})
                    args = fn.get("arguments")
                    if isinstance(args, str):
                        try:
                            fn["arguments"] = json.loads(args)
                        except (json.JSONDecodeError, TypeError):
                            fn["arguments"] = {}
        
        body: dict = {
            "model": self.model,
            "stream": True,
            "messages": raw_messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        
        if tools:
            body["tools"] = tools
        
        try:
            async with self._session.post(
                f"{self.base_url}/api/chat",
                json=body,
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"Ollama error {resp.status}: {text}")
                
                async for line in resp.content:
                    text = line.decode("utf-8", errors="replace").strip()
                    if not text:
                        continue
                    
                    try:
                        data = json.loads(text)
                    except json.JSONDecodeError as e:
                        logger.debug(f"Suppressed json.JSONDecodeError: {e}")
                        continue
                    
                    # Text content
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        yield StreamChunk(delta=content)
                    
                    # Tool calls (Ollama format)
                    tool_calls = msg.get("tool_calls", [])
                    for i, tc in enumerate(tool_calls):
                        fn = tc.get("function", {})
                        yield StreamChunk(tool_call_delta={
                            "index": i,
                            "id": f"ollama_tc_{i}",
                            "function": {
                                "name": fn.get("name", ""),
                                "arguments": json.dumps(fn.get("arguments", {})),
                            },
                        })
                    
                    # Done
                    if data.get("done"):
                        # Extract usage from final message
                        usage = {}
                        if "prompt_eval_count" in data:
                            usage["input_tokens"] = data["prompt_eval_count"]
                        if "eval_count" in data:
                            usage["output_tokens"] = data["eval_count"]
                        
                        finish = "tool_calls" if tool_calls else "stop"
                        yield StreamChunk(
                            finish_reason=finish,
                            usage=usage if usage else None,
                        )
                        self.record_success()
                        return
            
            # Stream ended without done=true — still a success if we got here
            self.record_success()
            
        except Exception as e:
            self.record_failure(e)
            raise
    
    async def health(self) -> bool:
        """Check if Ollama is running."""
        try:
            await self.initialize()
            async with self._session.get(
                f"{self.base_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
