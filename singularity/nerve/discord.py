"""
NERVE — Discord Channel Adapter
==================================

Full discord.py integration. Guilds, DMs, threads, reactions,
typing indicators, message chunking.

Platform-native. No lowest-common-denominator flattening.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

try:
    import discord
    from discord import (
        Client,
        Intents,
        Message as DiscordMessage,
    )
    HAS_DISCORD = True
except ImportError:
    HAS_DISCORD = False

from .adapter import BaseAdapter
from .formatter import format_for_channel
from .deployer import GuildDeployer, generate_invite_link
from .types import (
    AdapterState,
    ChannelCapabilities,
    ChannelSource,
    ChatType,
    EditPayload,
    FormattingDialect,
    InboundPayload,
    MediaPayload,
    OutboundMessage,
    PayloadType,
    RateLimitConfig,
    ReactionPayload,
    SendResult,
)

logger = logging.getLogger("singularity.nerve.discord")


# ── Discord Capabilities ────────────────────────────────────────────

DISCORD_CAPABILITIES = ChannelCapabilities(
    media=True,
    reactions=True,
    message_edit=True,
    message_delete=True,
    threads=True,
    embeds=True,
    components=True,
    voice_notes=False,
    read_receipts=False,
    typing_indicator=True,
    ephemeral=True,
    polls=False,
    formatting=FormattingDialect.MARKDOWN,
    max_message_length=2000,
    max_media_size=25 * 1024 * 1024,
    rate_limits=RateLimitConfig(
        messages_per_second=5.0,
        burst_size=5,
    ),
)


# ── Discord Adapter ─────────────────────────────────────────────────

class DiscordAdapter(BaseAdapter):
    """
    Discord channel adapter using discord.py.
    
    Config dict keys:
        token (str): Bot token (required)
        bot_id (str): Bot's user ID (auto-detected on ready)
        sibling_bot_ids (list[str]): Sibling bot IDs to allow
    """

    def __init__(self, adapter_id: str = "discord-main"):
        super().__init__(adapter_id)
        self._client: Optional[Client] = None
        self._token = ""
        self._bot_id = ""
        self._sibling_bot_ids: set[str] = set()
        self._ready_event = asyncio.Event()
        self._deployer: Optional[GuildDeployer] = None
        self._auto_deploy: bool = True
        self._channel_cache: dict[int, Any] = {}  # channel_id → channel object

    @property
    def channel_type(self) -> str:
        return "discord"

    @property
    def capabilities(self) -> ChannelCapabilities:
        return DISCORD_CAPABILITIES

    @property
    def bot_id(self) -> str:
        return self._bot_id

    @property
    def client(self) -> Optional[Client]:
        return self._client

    # ── Platform Lifecycle ───────────────────────────────────────────

    async def platform_connect(self, config: dict) -> None:
        if not HAS_DISCORD:
            raise RuntimeError(
                "discord.py not installed. Install with: pip install discord.py"
            )

        self._token = config.get("token", "")
        if not self._token:
            raise ValueError("Discord token is required")

        if config.get("sibling_bot_ids"):
            self._sibling_bot_ids = set(config["sibling_bot_ids"])

        # Boot message config — where to announce startup
        self._boot_channels = config.get("alert_channels", [])
        self._owner_ids = config.get("authorized_users", [])

        # Auto-deploy config
        self._auto_deploy = config.get("auto_deploy", True)
        if config.get("deployer"):
            self._deployer = config["deployer"]

        # Build intents
        intents = Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.guild_messages = True
        intents.guild_reactions = True
        intents.dm_messages = True
        intents.dm_reactions = True
        intents.members = True
        intents.presences = True

        self._client = Client(intents=intents)
        self._setup_events()

        # Start in background — login returns when ready
        asyncio.create_task(self._run_client())

        # Wait for ready with timeout
        try:
            await asyncio.wait_for(self._ready_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            raise RuntimeError("Discord client failed to become ready within 30s")

    async def _run_client(self) -> None:
        """Run the discord.py client (blocking coroutine)."""
        try:
            await self._client.start(self._token)
        except Exception as exc:
            logger.error("[%s] Client crashed: %s", self._id, exc)
            self._health.transition(AdapterState.DISCONNECTED, str(exc))

    def _setup_events(self) -> None:
        """Wire discord.py events to our handlers."""
        client = self._client

        @client.event
        async def on_ready():
            self._bot_id = str(client.user.id)
            logger.info(
                "[%s] Connected as %s (%s)",
                self._id, client.user.name, self._bot_id,
            )
            self._ready_event.set()
            # ── Startup announcement ──
            await self._send_boot_message()

        @client.event
        async def on_message(msg: DiscordMessage):
            self._handle_message(msg)

        @client.event
        async def on_raw_reaction_add(payload):
            await self._handle_reaction(payload, remove=False)

        @client.event
        async def on_raw_reaction_remove(payload):
            await self._handle_reaction(payload, remove=True)

        @client.event
        async def on_message_edit(before, after):
            # 'before' can be None for uncached messages — only 'after' is guaranteed
            if after is None:
                return
            if after.author and after.author.id == int(self._bot_id or 0):
                return
            self._handle_edit(after)

        @client.event
        async def on_message_delete(msg: DiscordMessage):
            self._handle_delete(msg)

        @client.event
        async def on_disconnect():
            logger.warning("[%s] Disconnected", self._id)
            # discord.py auto-reconnects; only track if we're still running
            if self._running:
                self._health.transition(AdapterState.DEGRADED)

        @client.event
        async def on_resumed():
            logger.info("[%s] Resumed", self._id)
            self._health.transition(AdapterState.CONNECTED)

        @client.event
        async def on_guild_join(guild):
            logger.info(
                "[%s] Joined guild: %s (%s)",
                self._id, guild.name, guild.id,
            )
            if self._auto_deploy and self._deployer:
                logger.info("[%s] Auto-deploying to %s...", self._id, guild.name)
                try:
                    result = await self._deployer.deploy(guild)
                    if result.success:
                        logger.info(
                            "[%s] Deployed %d channels to %s",
                            self._id, len(result.channels), guild.name,
                        )
                    else:
                        logger.error(
                            "[%s] Deploy failed in %s: %s",
                            self._id, guild.name, result.errors,
                        )
                except Exception as exc:
                    logger.error(
                        "[%s] Deploy exception in %s: %s",
                        self._id, guild.name, exc, exc_info=True,
                    )

    async def _send_boot_message(self) -> None:
        """Send startup announcement to configured alert channels."""
        if not self._boot_channels:
            logger.info("[%s] No alert channels configured — skipping boot message", self._id)
            return

        # Mention the first authorized user (owner) if configured
        owner_mention = f"<@{self._owner_ids[0]}> " if self._owner_ids else ""

        boot_msg = (
            f"{owner_mention}⚡ **Singularity Online.**\n\n"
            "Singularity online. Cognitive rails active. "
            "Source of truth — operational.\n\n"
            "No margin for BS. Ready to work."
        )

        for channel_id in self._boot_channels:
            try:
                result = await self.platform_send(
                    channel_id,
                    OutboundMessage(content=boot_msg),
                )
                if result.success:
                    logger.info("[%s] Boot message sent to %s", self._id, channel_id)
                else:
                    logger.warning("[%s] Boot message failed for %s: %s", self._id, channel_id, result.error)
            except Exception as exc:
                logger.warning("[%s] Boot message error for %s: %s", self._id, channel_id, exc)

    async def platform_disconnect(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    async def platform_reconnect(self) -> None:
        await self.platform_disconnect()
        # Re-use existing config
        await self.platform_connect({"token": self._token})

    # ── Inbound Handlers ─────────────────────────────────────────────

    def _handle_message(self, msg: DiscordMessage) -> None:
        # Ignore own messages
        if str(msg.author.id) == self._bot_id:
            return
        # Ignore other bots — but never siblings
        if msg.author.bot and str(msg.author.id) not in self._sibling_bot_ids:
            logger.debug("Ignoring non-sibling bot: %s (%s)", msg.author.name, msg.author.id)
            return

        logger.info("Message from %s (%s) in %s: %s", msg.author.name, msg.author.id, msg.channel.id, msg.content[:100])
        try:
            source = self._build_source(msg)
            payload = self._build_payload(msg)
            self.emit(source, payload, str(msg.id))
            logger.info("Emitted message %s to router", msg.id)
        except Exception as e:
            logger.error("Failed to process message %s: %s", msg.id, e, exc_info=True)

    async def _handle_reaction(self, payload, remove: bool) -> None:
        if str(payload.user_id) == self._bot_id:
            return

        chat_id = str(payload.channel_id)
        chat_type = ChatType.CHANNEL  # Can't easily determine from raw

        # Try to get user info
        user = self._client.get_user(payload.user_id)
        sender_name = user.name if user else None

        source = ChannelSource(
            channel_type="discord",
            adapter_id=self._id,
            chat_id=chat_id,
            chat_type=chat_type,
            sender_id=str(payload.user_id),
            sender_name=sender_name,
        )

        inbound = InboundPayload(
            type=PayloadType.REACTION,
            reaction=ReactionPayload(
                emoji=str(payload.emoji),
                message_id=str(payload.message_id),
                remove=remove,
            ),
        )

        self.emit(
            source, inbound,
            f"reaction-{payload.message_id}-{payload.user_id}-{payload.emoji}",
        )

    def _handle_edit(self, msg: DiscordMessage) -> None:
        if str(msg.author.id) == self._bot_id:
            return

        source = self._build_source(msg)
        inbound = InboundPayload(
            type=PayloadType.EDIT,
            edit=EditPayload(
                message_id=str(msg.id),
                new_text=msg.content,
            ),
            raw=msg,
        )
        self.emit(source, inbound, f"edit-{msg.id}")

    def _handle_delete(self, msg: DiscordMessage) -> None:
        chat_id = str(msg.channel.id)
        # msg.author may be None for uncached messages
        sender_id = str(msg.author.id) if msg.author else "unknown"
        source = ChannelSource(
            channel_type="discord",
            adapter_id=self._id,
            chat_id=chat_id,
            chat_type=self._resolve_chat_type(msg.channel),
            sender_id=sender_id,
        )
        inbound = InboundPayload(
            type=PayloadType.DELETE,
            raw={"message_id": str(msg.id)},
        )
        self.emit(source, inbound, f"delete-{msg.id}")

    # ── Source/Payload Builders ──────────────────────────────────────

    def _build_source(self, msg: DiscordMessage) -> ChannelSource:
        chat_type = self._resolve_chat_type(msg.channel)
        mentions = [str(u.id) for u in msg.mentions]

        return ChannelSource(
            channel_type="discord",
            adapter_id=self._id,
            chat_id=str(msg.channel.id),
            chat_type=chat_type,
            sender_id=str(msg.author.id),
            sender_name=getattr(msg.author, "display_name", msg.author.name),
            reply_to_id=(
                str(msg.reference.message_id)
                if msg.reference and msg.reference.message_id
                else None
            ),
            thread_id=(
                str(msg.channel.id)
                if hasattr(msg.channel, "parent_id") and msg.channel.parent_id
                else None
            ),
            mentions=mentions,
        )

    def _build_payload(self, msg: DiscordMessage) -> InboundPayload:
        media: list[MediaPayload] = []

        for att in msg.attachments:
            media.append(MediaPayload(
                type=self._resolve_media_type(att.content_type or ""),
                url=att.url,
                mime_type=att.content_type,
                filename=att.filename,
                size_bytes=att.size,
                width=att.width,
                height=att.height,
            ))

        for sticker in msg.stickers:
            media.append(MediaPayload(
                type="sticker",
                url=sticker.url,
                filename=sticker.name,
            ))

        return InboundPayload(
            type=PayloadType.MEDIA if (media and not msg.content) else PayloadType.TEXT,
            text=msg.content or None,
            media=media if media else None,
            raw=msg,
        )

    def _resolve_chat_type(self, channel) -> ChatType:
        if channel is None:
            return ChatType.CHANNEL
        channel_type = getattr(channel, "type", None)
        if channel_type is not None:
            if HAS_DISCORD:
                if channel_type == discord.ChannelType.private:
                    return ChatType.DM
                if channel_type in (
                    discord.ChannelType.public_thread,
                    discord.ChannelType.private_thread,
                ):
                    return ChatType.THREAD
        return ChatType.CHANNEL

    def _resolve_media_type(self, content_type: str) -> str:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type.startswith("audio/"):
            return "audio"
        return "document"

    # ── Outbound ─────────────────────────────────────────────────────

    async def platform_send(
        self, chat_id: str, message: OutboundMessage
    ) -> SendResult:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return SendResult(success=False, error=f"Channel {chat_id} not found")

        # Format for Discord
        chunks = (
            format_for_channel(message.content, self.capabilities)
            if message.content
            else []
        )

        # If no content and no media, nothing to send
        if not chunks and not message.media:
            return SendResult(success=True, message_id=None)

        # Ensure at least one chunk for media-only sends
        if not chunks:
            chunks = [""]

        last_message_id: Optional[str] = None

        for i, chunk in enumerate(chunks):
            is_first = i == 0
            is_last = i == len(chunks) - 1

            send_kwargs: dict = {}

            if chunk:
                send_kwargs["content"] = chunk

            # Reply only on first chunk
            if is_first and message.reply_to_id:
                try:
                    ref_msg = await channel.fetch_message(int(message.reply_to_id))
                    send_kwargs["reference"] = ref_msg
                except Exception as e:
                    logger.debug(f"Suppressed: {e}")

            # Media on last chunk
            if is_last and message.media:
                files = []
                for m in message.media:
                    path = m.url or m.path
                    if path:
                        try:
                            files.append(discord.File(path, filename=m.filename))
                        except Exception as exc:
                            logger.warning("Failed to attach file %s: %s", path, exc)
                if files:
                    send_kwargs["files"] = files

            try:
                sent = await channel.send(**send_kwargs)
                last_message_id = str(sent.id)
            except Exception as exc:
                return SendResult(success=False, error=str(exc))

        return SendResult(
            success=True,
            message_id=last_message_id,
            delivered_at=asyncio.get_event_loop().time(),
        )

    async def _resolve_channel(self, chat_id: str):
        """Resolve a channel by ID, with caching. Supports guild channels and DMs."""
        if not self._client:
            return None
        int_id = int(chat_id)
        # Check cache first
        cached = self._channel_cache.get(int_id)
        if cached is not None:
            return cached
        try:
            # Try guild channel first (fast path — no API call)
            channel = self._client.get_channel(int_id)
            if channel and hasattr(channel, "send"):
                self._channel_cache[int_id] = channel
                return channel
            # Try fetching guild channel via API
            try:
                channel = await self._client.fetch_channel(int_id)
                if channel and hasattr(channel, "send"):
                    self._channel_cache[int_id] = channel
                    return channel
            except Exception:
                pass
            # fetch_channel fails for DM channels — try creating a DM via user ID
            # If the chat_id looks like a user snowflake, open a DM channel
            try:
                user = await self._client.fetch_user(int_id)
                if user:
                    dm_channel = await user.create_dm()
                    if dm_channel and hasattr(dm_channel, "send"):
                        self._channel_cache[int_id] = dm_channel
                        logger.info("[%s] Resolved DM channel for user %s", self._id, int_id)
                        return dm_channel
            except Exception as e:
                logger.debug("[%s] DM resolve failed for %s: %s", self._id, int_id, e)
        except Exception as e:
            logger.error("[%s] _resolve_channel error for %s: %s", self._id, int_id, e)
        return None

    # ── Platform Actions ─────────────────────────────────────────────

    async def react(
        self, chat_id: str, message_id: str, emoji: str
    ) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.add_reaction(emoji)
        except Exception as exc:
            logger.error("[%s] React failed: %s", self._id, exc)

    async def edit_message(
        self, chat_id: str, message_id: str, new_content: str
    ) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            if str(msg.author.id) == self._bot_id:
                await msg.edit(content=new_content)
        except Exception as exc:
            logger.error("[%s] Edit failed: %s", self._id, exc)

    async def delete_message(self, chat_id: str, message_id: str) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            msg = await channel.fetch_message(int(message_id))
            await msg.delete()
        except Exception as exc:
            logger.error("[%s] Delete failed: %s", self._id, exc)

    async def typing(self, chat_id: str, duration_ms: int = 5000) -> None:
        channel = await self._resolve_channel(chat_id)
        if not channel:
            return
        try:
            await channel.typing()
        except Exception as e:
            logger.debug(f"Suppressed: {e}")

    # ── Helpers ──────────────────────────────────────────────────────

    def get_guild_count(self) -> int:
        """How many guilds we're in."""
        return len(self._client.guilds) if self._client else 0

    def set_deployer(self, deployer: GuildDeployer) -> None:
        """Set the guild deployer for auto-deployment on join."""
        self._deployer = deployer

    def get_invite_link(self) -> str:
        """Generate the bot invite link with required permissions."""
        if not self._bot_id:
            raise RuntimeError("Bot ID not available — connect first or provide bot_id in config")
        return generate_invite_link(self._bot_id)

    async def deploy_to_guild(self, guild_id: int) -> Optional[Any]:
        """
        Manually trigger deployment to a guild the bot is already in.
        Useful for deploying to existing guilds after setup.
        """
        if not self._client or not self._deployer:
            return None
        guild = self._client.get_guild(guild_id)
        if not guild:
            try:
                guild = await self._client.fetch_guild(guild_id)
            except Exception:
                return None
        return await self._deployer.deploy(guild)
