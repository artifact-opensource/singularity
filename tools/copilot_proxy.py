"""
Copilot Proxy v2 — Stealth Edition
====================================
OpenAI-compatible proxy for GitHub Copilot API.
Persistent HTTP/2 connection, VS Code session fingerprinting,
automatic retry with backoff on stream failures.

Usage:
    python3 copilot_proxy.py          # Start on port 3000
    python3 copilot_proxy.py auth     # Authenticate with GitHub
"""

import asyncio
import hashlib
import json
import os
import platform
import sys
import time
import uuid
from pathlib import Path

import httpx
from aiohttp import web
from aiohttp.client_exceptions import ClientConnectionResetError

COPILOT_API = "https://api.githubcopilot.com"
GITHUB_API = "https://api.github.com"
TOKEN_FILE = Path.home() / ".copilot-proxy" / "token.json"
COPILOT_TOKEN_FILE = Path.home() / ".copilot-proxy" / "copilot_token.json"

# GitHub OAuth App (VS Code Copilot client ID)
COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"

# Stable machine fingerprint (persists across restarts like a real IDE)
MACHINE_ID_FILE = Path.home() / ".copilot-proxy" / "machine_id"

MAX_RETRIES = 2
RETRY_DELAYS = [1.0, 3.0]  # seconds between retries


def _get_machine_id() -> str:
    """Get or create a stable machine ID (SHA256 hex, like VS Code)."""
    if MACHINE_ID_FILE.exists():
        return MACHINE_ID_FILE.read_text().strip()
    # Generate from hostname + platform — stable across restarts
    seed = f"{platform.node()}-{platform.machine()}-copilot-proxy"
    mid = hashlib.sha256(seed.encode()).hexdigest()
    MACHINE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    MACHINE_ID_FILE.write_text(mid)
    MACHINE_ID_FILE.chmod(0o600)
    return mid


class CopilotAuth:
    """Handle GitHub → Copilot token exchange."""

    def __init__(self):
        self._github_token: str | None = None
        self._copilot_token: str | None = None
        self._copilot_token_expires: float = 0
        self._load_tokens()

    def _load_tokens(self):
        if TOKEN_FILE.exists():
            data = json.loads(TOKEN_FILE.read_text())
            self._github_token = data.get("github_token")
        if COPILOT_TOKEN_FILE.exists():
            data = json.loads(COPILOT_TOKEN_FILE.read_text())
            self._copilot_token = data.get("token")
            self._copilot_token_expires = data.get("expires_at", 0)

    def _save_github_token(self, token: str):
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(json.dumps({"github_token": token}))
        TOKEN_FILE.chmod(0o600)
        self._github_token = token

    def _save_copilot_token(self, token: str, expires_at: int):
        COPILOT_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        COPILOT_TOKEN_FILE.write_text(json.dumps({
            "token": token,
            "expires_at": expires_at,
        }))
        COPILOT_TOKEN_FILE.chmod(0o600)
        self._copilot_token = token
        self._copilot_token_expires = expires_at

    async def device_auth(self):
        """Run GitHub device authorization flow."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://github.com/login/device/code",
                json={
                    "client_id": COPILOT_CLIENT_ID,
                    "scope": "copilot",
                },
                headers={"Accept": "application/json"},
            )
            data = resp.json()

            device_code = data["device_code"]
            user_code = data["user_code"]
            verification_uri = data["verification_uri"]
            interval = data.get("interval", 5)

            print(f"\n{'='*50}")
            print(f"  Go to: {verification_uri}")
            print(f"  Enter code: {user_code}")
            print(f"{'='*50}\n")
            print("Waiting for authorization...")

            while True:
                await asyncio.sleep(interval)
                resp = await client.post(
                    "https://github.com/login/oauth/access_token",
                    json={
                        "client_id": COPILOT_CLIENT_ID,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Accept": "application/json"},
                )
                result = resp.json()

                if "access_token" in result:
                    self._save_github_token(result["access_token"])
                    print("✅ Authenticated successfully!")
                    return result["access_token"]

                error = result.get("error")
                if error == "authorization_pending":
                    continue
                elif error == "slow_down":
                    interval = result.get("interval", interval + 5)
                    continue
                elif error == "expired_token":
                    print("❌ Device code expired. Try again.")
                    return None
                elif error == "access_denied":
                    print("❌ Authorization denied.")
                    return None
                else:
                    print(f"❌ Unexpected error: {error}")
                    return None

    async def get_copilot_token(self) -> str | None:
        """Get a valid Copilot API token, refreshing if needed."""
        if self._copilot_token and time.time() < (self._copilot_token_expires - 300):
            return self._copilot_token

        if not self._github_token:
            print("No GitHub token. Run: python3 copilot_proxy.py auth")
            return None

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{GITHUB_API}/copilot_internal/v2/token",
                headers={
                    "Authorization": f"token {self._github_token}",
                    "Accept": "application/json",
                    "Editor-Version": "vscode/1.100.0",
                    "Editor-Plugin-Version": "copilot-chat/0.25.0",
                    "User-Agent": "GitHubCopilotChat/0.25.0",
                },
            )

            if resp.status_code != 200:
                print(f"Failed to get Copilot token: {resp.status_code} {resp.text}")
                return None

            data = resp.json()
            token = data.get("token")
            expires_at = data.get("expires_at", int(time.time()) + 1800)

            if token:
                self._save_copilot_token(token, expires_at)
                return token

        return None


class CopilotProxy:
    """OpenAI-compatible proxy with persistent connection and VS Code fingerprinting."""

    def __init__(self, port: int = 3000):
        self.port = port
        self.auth = CopilotAuth()
        self.app = web.Application()
        self._setup_routes()

        # Stable session identity (persists for proxy lifetime, like a real IDE session)
        self._session_id = str(uuid.uuid4())
        self._machine_id = _get_machine_id()

        # Persistent HTTP/2 client — ONE connection, reused across all requests
        # This is how real VS Code behaves: single multiplexed connection
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

        # Stats
        self._req_count = 0
        self._retry_count = 0
        self._error_count = 0

        self.app.on_startup.append(self._start_client)
        self.app.on_cleanup.append(self._stop_client)

    async def _start_client(self, app):
        """Create persistent HTTP/2 client on startup."""
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(300.0, connect=30.0),
            limits=httpx.Limits(
                max_connections=5,
                max_keepalive_connections=2,
                keepalive_expiry=120,
            ),
        )
        print(f"[PROXY:{self.port}] Persistent HTTP/2 client ready (session={self._session_id[:8]})", file=sys.stderr)

    async def _stop_client(self, app):
        """Clean shutdown of persistent client."""
        if self._client:
            await self._client.aclose()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get the persistent client, recreating if closed."""
        if self._client is None or self._client.is_closed:
            async with self._client_lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        http2=True,
                        timeout=httpx.Timeout(300.0, connect=30.0),
                        limits=httpx.Limits(
                            max_connections=5,
                            max_keepalive_connections=2,
                            keepalive_expiry=120,
                        ),
                    )
                    print(f"[PROXY:{self.port}] Client reconnected", file=sys.stderr)
        return self._client

    def _build_headers(self, token: str) -> dict:
        """Build request headers matching real VS Code Copilot Chat fingerprint."""
        self._req_count += 1
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-Id": str(uuid.uuid4()),
            "VScode-SessionId": self._session_id,
            "VScode-MachineId": self._machine_id,
            "X-GitHub-Api-Version": "2023-07-07",
            "Copilot-Integration-Id": "vscode-chat",
            "Editor-Version": "vscode/1.100.0",
            "Editor-Plugin-Version": "copilot-chat/0.25.0",
            "Openai-Organization": "github-copilot",
            "Openai-Intent": "conversation-panel",
            "User-Agent": "GitHubCopilotChat/0.25.0",
        }

    def _setup_routes(self):
        self.app.router.add_post("/v1/chat/completions", self.chat_completions)
        self.app.router.add_post("/chat/completions", self.chat_completions)
        self.app.router.add_get("/v1/models", self.list_models)
        self.app.router.add_get("/models", self.list_models)
        self.app.router.add_get("/health", self.health)
        self.app.router.add_get("/", self.health)

    async def _stream_with_retry(self, body: dict, headers: dict, request: web.Request) -> web.Response:
        """Stream response with automatic retry on failure."""
        model = body.get("model", "unknown")
        msg_count = len(body.get("messages", []))

        for attempt in range(1 + MAX_RETRIES):
            client = await self._get_client()

            # Fresh request ID per attempt (but same session)
            if attempt > 0:
                headers["X-Request-Id"] = str(uuid.uuid4())
                self._retry_count += 1
                delay = RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)]
                print(f"[PROXY:{self.port}] RETRY {attempt}/{MAX_RETRIES} after {delay}s (model={model} msgs={msg_count})", file=sys.stderr)
                await asyncio.sleep(delay)

            response = web.StreamResponse(
                status=200,
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )

            try:
                async with client.stream(
                    "POST",
                    f"{COPILOT_API}/chat/completions",
                    json=body,
                    headers=headers,
                ) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        error_text = error_body.decode()[:500]
                        print(f"[PROXY:{self.port}] UPSTREAM ERROR {resp.status_code}: {error_text}", file=sys.stderr)

                        # 429 = rate limited, retry
                        if resp.status_code == 429 and attempt < MAX_RETRIES:
                            continue

                        # Other errors: return immediately
                        await response.prepare(request)
                        await response.write(
                            f"data: {json.dumps({'error': error_text})}\n\n".encode()
                        )
                        return response

                    await response.prepare(request)
                    line_count = 0
                    try:
                        async for line in resp.aiter_lines():
                            line_count += 1
                            await response.write(f"{line}\n".encode())
                    except (httpx.ReadTimeout, httpx.ReadError, httpx.RemoteProtocolError) as e:
                        # Stream was interrupted by upstream
                        print(f"[PROXY:{self.port}] STREAM CUT at line {line_count}: {type(e).__name__} (attempt {attempt+1})", file=sys.stderr)
                        self._error_count += 1

                        if line_count > 0:
                            # Partial response already sent — can't retry transparently
                            # Send error marker so client knows it was truncated
                            try:
                                await response.write(
                                    f"\ndata: {json.dumps({'error': {'message': f'Stream interrupted after {line_count} chunks', 'type': 'stream_error'}})}\n\n".encode()
                                )
                            except Exception:
                                pass
                            return response

                        # Zero lines received — retry is safe (nothing sent to client yet)
                        if attempt < MAX_RETRIES:
                            continue
                        return response
                    except (ConnectionResetError, ConnectionError, BrokenPipeError, ClientConnectionResetError) as e:
                        print(f"[PROXY:{self.port}] Client disconnected after {line_count} lines: {type(e).__name__}", file=sys.stderr)
                        return response

                    if line_count == 0:
                        print(f"[PROXY:{self.port}] WARNING: 0 lines from upstream (model={model} msgs={msg_count})", file=sys.stderr)

                return response

            except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout,
                    httpx.ConnectError, httpx.RemoteProtocolError) as e:
                # Connection-level failure before streaming started
                print(f"[PROXY:{self.port}] CONNECTION ERROR: {type(e).__name__} (attempt {attempt+1})", file=sys.stderr)
                self._error_count += 1

                if attempt < MAX_RETRIES:
                    # Force client recreation on connection errors
                    try:
                        await self._client.aclose()
                    except Exception:
                        pass
                    self._client = None
                    continue

                # All retries exhausted
                await response.prepare(request)
                await response.write(
                    f"data: {json.dumps({'error': {'message': f'Upstream unreachable after {MAX_RETRIES+1} attempts: {type(e).__name__}', 'type': 'connection_error'}})}\n\n".encode()
                )
                return response

        # Should not reach here, but safety net
        return web.json_response({"error": "Max retries exhausted"}, status=502)

    async def chat_completions(self, request: web.Request) -> web.Response:
        """Proxy chat completions to Copilot API."""
        token = await self.auth.get_copilot_token()
        if not token:
            return web.json_response(
                {"error": {"message": "No valid Copilot token. Run auth first.", "type": "auth_error"}},
                status=401,
            )

        body = await request.json()
        stream = body.get("stream", False)
        msg_count = len(body.get("messages", []))
        model = body.get("model", "unknown")
        has_tools = bool(body.get("tools"))

        total_chars = sum(len(m.get("content", "") or "") for m in body.get("messages", []))
        print(f"[PROXY:{self.port}] REQ model={model} msgs={msg_count} chars={total_chars} tools={has_tools} stream={stream}", file=sys.stderr)

        # Safeguard: Copilot API rejects conversations ending with assistant messages
        msgs = body.get("messages", [])
        while len(msgs) > 1 and msgs[-1].get("role") == "assistant":
            msgs.pop()
            print(f"[PROXY:{self.port}] Dropped trailing assistant message (prefill guard)", file=sys.stderr)
        body["messages"] = msgs

        headers = self._build_headers(token)

        if stream:
            return await self._stream_with_retry(body, headers, request)
        else:
            # Non-streaming with retry
            for attempt in range(1 + MAX_RETRIES):
                try:
                    client = await self._get_client()
                    if attempt > 0:
                        headers["X-Request-Id"] = str(uuid.uuid4())
                        await asyncio.sleep(RETRY_DELAYS[min(attempt - 1, len(RETRY_DELAYS) - 1)])

                    resp = await client.post(
                        f"{COPILOT_API}/chat/completions",
                        json=body,
                        headers=headers,
                    )

                    if resp.status_code == 429 and attempt < MAX_RETRIES:
                        print(f"[PROXY:{self.port}] 429 RATE LIMITED, retry {attempt+1}", file=sys.stderr)
                        continue

                    if resp.status_code >= 400:
                        print(f"[PROXY:{self.port}] ERROR {resp.status_code} model={model} msgs={msg_count}", file=sys.stderr)

                    return web.Response(
                        body=resp.content,
                        status=resp.status_code,
                        content_type="application/json",
                    )
                except (httpx.ReadTimeout, httpx.WriteTimeout, httpx.ConnectTimeout, httpx.ConnectError) as e:
                    print(f"[PROXY:{self.port}] NON-STREAM ERROR: {type(e).__name__} (attempt {attempt+1})", file=sys.stderr)
                    self._error_count += 1
                    if attempt >= MAX_RETRIES:
                        return web.json_response(
                            {"error": {"message": f"Upstream unreachable: {type(e).__name__}", "type": "connection_error"}},
                            status=502,
                        )
                    # Recreate client
                    try:
                        await self._client.aclose()
                    except Exception:
                        pass
                    self._client = None

    async def list_models(self, request: web.Request) -> web.Response:
        """Return available models."""
        token = await self.auth.get_copilot_token()
        if not token:
            return web.json_response({"error": "No valid Copilot token"}, status=401)

        client = await self._get_client()
        resp = await client.get(
            f"{COPILOT_API}/models",
            headers={
                "Authorization": f"Bearer {token}",
                "Copilot-Integration-Id": "vscode-chat",
                "VScode-SessionId": self._session_id,
                "VScode-MachineId": self._machine_id,
            },
        )
        return web.Response(
            body=resp.content,
            status=resp.status_code,
            content_type="application/json",
        )

    async def health(self, request: web.Request) -> web.Response:
        has_github = self.auth._github_token is not None
        has_copilot = (
            self.auth._copilot_token is not None
            and time.time() < self.auth._copilot_token_expires
        )
        client_alive = self._client is not None and not self._client.is_closed
        return web.json_response({
            "status": "ok",
            "version": "v2-stealth",
            "github_auth": has_github,
            "copilot_token_valid": has_copilot,
            "port": self.port,
            "http2": True,
            "persistent_connection": client_alive,
            "session_id": self._session_id[:8],
            "stats": {
                "requests": self._req_count,
                "retries": self._retry_count,
                "errors": self._error_count,
            },
        })

    def run(self):
        print(f"🔌 Copilot Proxy v2 (Stealth) on http://localhost:{self.port}")
        print(f"   HTTP/2 persistent connection, VS Code fingerprinting, auto-retry")
        print(f"   Session: {self._session_id[:8]}  Machine: {self._machine_id[:12]}...")
        if not self.auth._github_token:
            print(f"   ⚠️  No GitHub token. Run: python3 {__file__} auth")
        web.run_app(self.app, host="127.0.0.1", port=self.port, print=None)


async def do_auth():
    auth = CopilotAuth()
    await auth.device_auth()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        asyncio.run(do_auth())
    else:
        port = int(os.environ.get("PORT", "3000"))
        proxy = CopilotProxy(port=port)
        proxy.run()


if __name__ == "__main__":
    main()
