# ── OpenRouter Provider ──────────────────────────────────────────
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import aiohttp

from .provider import ChatProvider, ChatMessage, StreamChunk

logger = logging.getLogger("singularity.voice.openrouter")

class OpenRouterProvider(ChatProvider):
    """OpenRouter LLM provider.
    
    Uses the OpenAI-compatible /chat/completions endpoint.
    """
    
    def __init__(self, model: str, api_key: str, base_url: str = "https://openrouter.ai/api/v1", **kwargs):
        super().__init__(name="openrouter", model=model, **kwargs)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self) -> None:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300)
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
        await self.initialize()
        
        body = {
            "model": self.model,
            "stream": True,
            "messages": [m.to_dict() for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            
        try:
            async with self._session.post(
                f"{self.base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise RuntimeError(f"OpenRouter error {resp.status}: {text}")
                
                async for line in resp.content:
                    line = line.decode("utf-8").strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            choice = data["choices"][0]
                            delta = choice.get("delta", {})
                            
                            if "content" in delta:
                                yield StreamChunk(delta=delta["content"])
                            
                            if "tool_calls" in delta:
                                for tc in delta["tool_calls"]:
                                    yield StreamChunk(tool_call_delta=tc)
                                    
                            if choice.get("finish_reason"):
                                yield StreamChunk(finish_reason=choice["finish_reason"])
                        except Exception as e:
                            logger.debug(f"SSE parse error: {e}")
                            continue
            self.record_success()
        except Exception as e:
            self.record_failure(e)
            raise
            
    async def health(self) -> bool:
        try:
            await self.initialize()
            async with self._session.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}) as resp:
                return resp.status == 200
        except Exception:
            return False
