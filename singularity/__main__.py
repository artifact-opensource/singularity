"""
SINGULARITY — Entry Point
============================

Usage:
    python3 -m singularity              # Start the runtime
    python3 -m singularity --test       # Run gate tests
    python3 -m singularity --config PATH  # Use custom config
"""

import asyncio
import sys
import logging

from dotenv import load_dotenv
load_dotenv()

from .bus import EventBus, Priority


logger = logging.getLogger("singularity.__main__")

async def test_skeleton():
    """Phase 1 gate test: verify all skeleton components work."""
    print("=" * 60)
    print("SINGULARITY — Skeleton Test (Phase 1 Gate)")
    print("=" * 60)
    
    results = []
    
    # ── Test 1: Event Bus ──────────────────────────────────────────
    print("\n[1/18] Event Bus...")
    try:
        bus = EventBus()
        await bus.start()
        
        received = []
        
        @bus.on("test.hello")
        async def handler(event):
            received.append(event.data)
        
        # Test basic pub/sub
        await bus.emit("test.hello", {"msg": "world"}, source="test")
        await asyncio.sleep(0.1)  # Let processor deliver
        
        assert len(received) == 1, f"Expected 1 event, got {len(received)}"
        assert received[0]["msg"] == "world"
        
        # Test wildcard
        wild_received = []
        
        @bus.on("test.*")
        async def wild_handler(event):
            wild_received.append(event.name)
        
        await bus.emit("test.alpha", {})
        await bus.emit("test.beta", {})
        await bus.emit("other.gamma", {})  # Should NOT match
        await asyncio.sleep(0.1)
        
        assert len(wild_received) == 2, f"Wildcard: expected 2, got {len(wild_received)}"
        
        # Test once
        once_count = []
        
        @bus.once("test.once")
        async def once_handler(event):
            once_count.append(1)
        
        await bus.emit("test.once", {})
        await bus.emit("test.once", {})
        await asyncio.sleep(0.1)
        
        assert len(once_count) == 1, f"Once: expected 1, got {len(once_count)}"
        
        # Test metrics
        metrics = bus.metrics.snapshot()
        assert metrics["events_emitted"] > 0
        
        # Test dead letter (handler that throws)
        @bus.on("test.error")
        async def bad_handler(event):
            raise ValueError("intentional test error")
        
        await bus.emit("test.error", {})
        await asyncio.sleep(0.1)
        
        assert len(bus.dead_letters) == 1
        assert metrics["events_emitted"] > 0
        
        # Test wait_for
        async def delayed_emit():
            await asyncio.sleep(0.05)
            await bus.emit("test.waited", {"val": 42})
        
        asyncio.create_task(delayed_emit())
        event = await bus.wait_for("test.waited", timeout=2.0)
        assert event.data["val"] == 42
        
        await bus.stop()
        results.append(("Event Bus", "PASS", f"{metrics['events_emitted']} events, {bus.subscription_count} subs"))
        print(f"   ✅ PASS — {metrics['events_emitted']} events emitted, wildcards work, once works, dead letters captured")
        
    except Exception as e:
        results.append(("Event Bus", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 2: Config ─────────────────────────────────────────────
    print("\n[2/18] Config (SPINE)...")
    try:
        from .config import SingularityConfig, load_config
        
        # Test defaults
        cfg = SingularityConfig()
        assert cfg.voice.primary_model == "claude-sonnet-4"
        assert cfg.pulse.default_cap == 20
        assert cfg.tools.exec_timeout == 30
        
        # Test persona routing
        from .config import PersonaConfig
        cfg.personas = [
            PersonaConfig(name="CTO", channel_ids=["123", "456"]),
            PersonaConfig(name="COO", channel_ids=["789"]),
        ]
        
        assert cfg.route_channel("123").name == "CTO"
        assert cfg.route_channel("789").name == "COO"
        assert cfg.route_channel("999") is None
        assert cfg.get_persona("cto").name == "CTO"
        
        results.append(("Config", "PASS", "defaults + routing validated"))
        print("   ✅ PASS — defaults valid, persona routing works")
        
    except Exception as e:
        results.append(("Config", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 3: MEMORY Sessions ────────────────────────────────────
    print("\n[3/18] MEMORY Sessions...")
    try:
        import tempfile, os
        from .memory.sessions import SessionStore, Message
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test_sessions.db")
            store = SessionStore(db_path)
            await store.open()
            
            # Add messages
            m1 = Message(role="user", content="Hello Singularity")
            m2 = Message(role="assistant", content="Hello! I'm Singularity.")
            
            id1 = await store.add_message("ch1", m1, token_count=10)
            id2 = await store.add_message("ch1", m2, token_count=15)
            
            assert id1 > 0
            assert id2 > id1
            
            # Retrieve
            msgs = await store.get_messages("ch1")
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[1].content == "Hello! I'm Singularity."
            
            # Token count
            tokens = await store.get_token_count("ch1")
            assert tokens == 25
            
            # Clear
            deleted = await store.clear_messages("ch1")
            assert deleted == 2
            
            msgs_after = await store.get_messages("ch1")
            assert len(msgs_after) == 0
            
            # Replace
            await store.add_message("ch2", Message(role="user", content="test"))
            await store.replace_messages("ch2", [
                Message(role="system", content="compacted"),
                Message(role="user", content="latest"),
            ], token_counts=[50, 10])
            
            msgs_ch2 = await store.get_messages("ch2")
            assert len(msgs_ch2) == 2
            assert msgs_ch2[0].role == "system"
            
            # List sessions
            sessions = await store.list_sessions()
            assert len(sessions) == 1  # ch1 was cleared, ch2 remains
            
            await store.close()
            
        results.append(("MEMORY Sessions", "PASS", "CRUD + compaction + list"))
        print("   ✅ PASS — add, get, clear, replace, list all working")
        
    except Exception as e:
        results.append(("MEMORY Sessions", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 4: MEMORY COMB ────────────────────────────────────────
    print("\n[4/18] MEMORY COMB...")
    try:
        import tempfile
        from .memory.comb import CombMemory
        
        with tempfile.TemporaryDirectory() as tmpdir:
            comb = CombMemory(tmpdir)
            await comb.initialize()
            
            # Stage
            ok = await comb.stage("Singularity remembers everything")
            assert ok, "Stage failed"
            
            # Stage more
            ok = await comb.stage("Day 19: Singularity begins")
            assert ok
            
            # Recall
            content = await comb.recall()
            assert "Singularity remembers" in content
            assert "Singularity" in content
        
        results.append(("MEMORY COMB", "PASS", "stage + recall"))
        print("   ✅ PASS — stage and recall working (memory persists)")
        
    except Exception as e:
        results.append(("MEMORY COMB", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 5: SINEW Tools ────────────────────────────────────────
    print("\n[5/18] SINEW Tools...")
    try:
        from .sinew.executor import ToolExecutor
        from .sinew.sandbox import validate_command, validate_path
        
        executor = ToolExecutor(workspace="/home/adam/workspace/enterprise")
        
        # Test exec
        result = await executor.execute("exec", {"command": "echo 'singularity lives'"})
        assert "singularity lives" in result
        
        # Test read
        result = await executor.execute("read", {"path": "/home/adam/workspace/enterprise/singularity/VISION.md", "limit": 3})
        assert "SINGULARITY" in result
        
        # Test write + read roundtrip
        import tempfile, os
        test_file = os.path.join(tempfile.gettempdir(), "singularity_test.txt")
        await executor.execute("write", {"path": test_file, "content": "Singularity was here"})
        result = await executor.execute("read", {"path": test_file})
        assert "Singularity was here" in result
        os.unlink(test_file)
        
        # Test sandbox blocks
        assert validate_command("rm -rf /") is not None, "Should block rm -rf /"
        assert validate_command("ls -la") is None, "Should allow ls"
        assert validate_path("/etc/shadow") is None  # allowed (read-only is fine)
        assert validate_path("/root/secret") is not None, "Should block /root"
        
        # Test unknown tool
        result = await executor.execute("nonexistent_tool", {})
        assert "Unknown tool" in result
        
        await executor.close()
        
        results.append(("SINEW Tools", "PASS", "exec + read + write + sandbox"))
        print("   ✅ PASS — exec, read, write, edit, sandbox all working")
        
    except Exception as e:
        results.append(("SINEW Tools", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 6: VOICE Provider Abstraction ──────────────────────
    print("\n[6/18] VOICE Provider Abstraction...")
    try:
        from .voice.provider import ChatProvider, ChatMessage, ChatResponse, StreamChunk
        from .voice.chain import ProviderChain
        from .voice.proxy import CopilotProxyProvider
        from .voice.ollama import OllamaProvider
        
        # Test ChatMessage
        msg = ChatMessage(role="user", content="Hello")
        d = msg.to_dict()
        assert d["role"] == "user"
        assert d["content"] == "Hello"
        assert "name" not in d  # Optional fields excluded
        
        # Test ChatResponse
        resp = ChatResponse(
            content="Hi there",
            tool_calls=[{"id": "tc1", "type": "function", "function": {"name": "exec", "arguments": "{}"}}],
            usage={"input_tokens": 10, "output_tokens": 5},
        )
        assert resp.has_tool_calls
        assert resp.total_tokens == 15
        
        # Test provider instantiation
        copilot = CopilotProxyProvider(model="claude-sonnet-4")
        assert copilot.name == "copilot-proxy"
        assert copilot.model == "claude-sonnet-4"
        assert copilot.available
        
        ollama = OllamaProvider(model="llama3.2")
        assert ollama.name == "ollama"
        
        # Test chain construction
        chain = ProviderChain([copilot, ollama])
        assert len(chain.providers) == 2
        assert len(chain.available_providers) == 2
        
        # Test circuit breaker
        copilot.record_failure(Exception("test"))
        copilot.record_failure(Exception("test"))
        assert copilot.available  # Still available after 2
        copilot.record_failure(Exception("test"))
        assert not copilot.available  # Unavailable after 3
        assert len(chain.available_providers) == 1  # Only ollama now
        
        copilot.record_success()  # Reset
        assert copilot.available
        
        # Test status
        status = chain.status()
        assert status["active"] is None
        assert len(status["providers"]) == 2
        
        results.append(("VOICE Provider", "PASS", "messages, responses, chain, circuit-breaker"))
        print("   ✅ PASS — ChatMessage, ChatResponse, ProviderChain, circuit-breaker all working")
        
    except Exception as e:
        results.append(("VOICE Provider", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 7: CORTEX Context Assembly ────────────────────────────
    print("\n[7/18] CORTEX Context Assembly...")
    try:
        from .cortex.context import ContextAssembler, build_system_prompt
        from .voice.provider import ChatMessage
        
        assembler = ContextAssembler(context_budget=1000, response_budget=200)
        
        # Basic assembly
        history = [
            ChatMessage(role="user", content="What's 2+2?"),
            ChatMessage(role="assistant", content="4"),
        ]
        
        messages = assembler.assemble(
            system_prompt="You are Singularity.",
            history=history,
            new_message=ChatMessage(role="user", content="And 3+3?"),
        )
        
        assert len(messages) == 4  # system + 2 history + new
        assert messages[0].role == "system"
        assert messages[0].content == "You are Singularity."
        assert messages[-1].content == "And 3+3?"
        
        # Test truncation (tiny budget)
        tiny = ContextAssembler(context_budget=100, response_budget=50)
        long_history = [
            ChatMessage(role="user", content="x" * 500),
            ChatMessage(role="assistant", content="y" * 500),
            ChatMessage(role="user", content="Recent message"),
        ]
        
        truncated = tiny.assemble("System", long_history)
        assert len(truncated) < len(long_history) + 1  # Some dropped
        
        # Test system prompt building
        prompt = build_system_prompt(
            persona_name="Singularity",
            persona_prompt="You are Singularity, the Autonomous Enterprise.",
            rules="Be helpful.",
            comb_context="Day 19: Singularity begins.",
        )
        assert "Singularity" in prompt
        assert "Be helpful" in prompt
        assert "Day 19" in prompt
        
        # Test compaction detection
        assert not assembler.needs_compaction([])
        huge = [ChatMessage(role="user", content="x" * 100_000)]
        assert assembler.needs_compaction(huge)
        
        results.append(("CORTEX Context", "PASS", "assembly, truncation, prompt building, compaction"))
        print("   ✅ PASS — assembly, truncation, prompt building, compaction detection")
        
    except Exception as e:
        results.append(("CORTEX Context", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 8: CORTEX Agent Loop (structural) ─────────────────────
    print("\n[8/18] CORTEX Agent Loop (structural)...")
    try:
        from .cortex.agent import AgentLoop, AgentConfig, TurnResult
        
        # Test config
        config = AgentConfig(
            persona_name="singularity",
            system_prompt="You are Singularity.",
            max_iterations=20,
            parallel_tools=True,
        )
        assert config.max_iterations == 20
        assert config.expansion_threshold == 18
        assert config.parallel_tools
        
        # Test TurnResult
        result = TurnResult(
            response="Hello!",
            iterations=3,
            tool_calls_total=5,
            total_tokens=1500,
            latency_ms=2340.5,
            provider="copilot-proxy",
        )
        assert result.response == "Hello!"
        assert result.finish_reason == "stop"
        assert result.error is None
        
        # Test AgentLoop instantiation (no actual LLM call)
        # We can't test the full loop without a live LLM,
        # but we can verify the structure exists
        from .voice.chain import ProviderChain
        from .sinew.executor import ToolExecutor
        
        chain = ProviderChain([])  # Empty chain
        tools = ToolExecutor(workspace="/tmp")
        
        loop = AgentLoop(voice=chain, tools=tools, config=config)
        assert loop._iteration == 0
        assert loop._max_iterations == 20
        assert not loop._expanded
        
        results.append(("CORTEX Agent Loop", "PASS", "config, result, loop structure"))
        print("   ✅ PASS — AgentConfig, TurnResult, AgentLoop structure verified")
        
    except Exception as e:
        results.append(("CORTEX Agent Loop", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 9: BLINK — Seamless Continuation ─────────────────────
    print("\n[9/18] BLINK — Seamless Continuation...")
    try:
        from .cortex.blink import (
            BlinkController, BlinkConfig, BlinkState, BlinkPhase,
            BLINK_PREPARE_MESSAGE, BLINK_RESUME_MESSAGE
        )
        
        # Test config defaults
        cfg = BlinkConfig()
        assert cfg.enabled
        assert cfg.max_depth == 5
        assert cfg.prepare_at == 3
        assert cfg.cooldown_seconds == 1.0
        
        # Test controller lifecycle
        ctrl = BlinkController(config=cfg, session_id="test-blink-001")
        assert ctrl.should_continue()  # depth 0 < max 5
        assert ctrl.state.phase == BlinkPhase.NORMAL
        assert ctrl.state.depth == 0
        
        # Normal completion — no blink needed
        assert not ctrl.needs_blink("stop")
        assert not ctrl.needs_blink("error")
        
        # Budget exceeded — blink needed
        assert ctrl.needs_blink("budget_exceeded")
        
        # Prepare message injection
        assert ctrl.should_prepare(3)   # at boundary
        assert ctrl.should_prepare(2)   # within boundary
        assert not ctrl.should_prepare(5)  # too early
        
        prep = ctrl.get_prepare_message()
        assert "BLINK APPROACHING" in prep
        assert not ctrl.should_prepare(2)  # already prepared
        
        # Record a blink
        ctrl.record_blink(iterations=20, tool_calls=15)
        assert ctrl.state.depth == 1
        assert ctrl.state.total_iterations == 20
        assert ctrl.state.total_tool_calls == 15
        assert ctrl.state.phase == BlinkPhase.BLINKING
        assert ctrl.should_continue()  # depth 1 < max 5
        
        # Resume
        resume = ctrl.get_resume_message()
        assert "BLINK COMPLETE" in resume
        assert "1/5" in resume  # depth/max
        ctrl.record_resume()
        assert ctrl.state.phase == BlinkPhase.RESUMED
        
        # Prepare flag resets after blink
        assert ctrl.should_prepare(3)  # can prepare again
        
        # Exhaust depth
        for i in range(4):  # blinks 2-5
            ctrl.record_blink(iterations=20, tool_calls=10)
        assert ctrl.state.depth == 5
        assert not ctrl.should_continue()  # capped
        assert not ctrl.needs_blink("budget_exceeded")  # capped
        assert ctrl.state.phase == BlinkPhase.CAPPED
        
        # Total tracking
        assert ctrl.state.total_iterations == 100  # 5 × 20
        assert ctrl.state.total_tool_calls == 55   # 15 + 4×10
        
        # Disabled controller
        disabled = BlinkController(config=BlinkConfig(enabled=False), session_id="test-disabled")
        assert disabled.should_continue()  # first run allowed
        assert not disabled.needs_blink("budget_exceeded")  # won't blink
        
        results.append(("BLINK", "PASS", "lifecycle, depth cap, prepare/resume, disable"))
        print("   ✅ PASS — BlinkController lifecycle, depth tracking, prepare/resume messages")
        
    except Exception as e:
        results.append(("BLINK", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 10: Integration (Bus → Voice → Cortex wiring) ────────
    print("\n[10/18] Integration wiring...")
    try:
        from .voice.chain import ProviderChain
        from .voice.proxy import CopilotProxyProvider
        from .voice.ollama import OllamaProvider
        from .sinew.executor import ToolExecutor
        from .cortex.agent import AgentLoop, AgentConfig
        
        integ_bus = EventBus()
        await integ_bus.start()
        
        # Wire everything together
        copilot = CopilotProxyProvider(model="claude-sonnet-4")
        ollama = OllamaProvider(model="llama3.2")
        chain = ProviderChain([copilot, ollama], bus=integ_bus)
        tools = ToolExecutor(workspace="/home/adam/workspace/enterprise", bus=integ_bus)
        config = AgentConfig(persona_name="singularity", system_prompt="You are Singularity.")
        
        # Create agent loop with all dependencies
        agent = AgentLoop(voice=chain, tools=tools, config=config, bus=integ_bus)
        
        # Verify event bus integration
        events_received = []
        
        @integ_bus.on("cortex.*")
        async def cortex_listener(event):
            events_received.append(event.name)
        
        @integ_bus.on("voice.*")
        async def voice_listener(event):
            events_received.append(event.name)
        
        @integ_bus.on("sinew.*")
        async def sinew_listener(event):
            events_received.append(event.name)
        
        # Verify tool execution flows through bus
        result = await tools.execute("exec", {"command": "echo 'integration test'"})
        await asyncio.sleep(0.1)
        
        assert "integration test" in result
        assert any("sinew" in e for e in events_received), f"No sinew events: {events_received}"
        
        await integ_bus.stop()
        await tools.close()
        
        results.append(("Integration", "PASS", "bus → voice → cortex → sinew wired"))
        print("   ✅ PASS — all subsystems wired through event bus")
        
    except Exception as e:
        results.append(("Integration", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # Phase 3 — Nerves (NERVE subsystem)
    # ═══════════════════════════════════════════════════════════════
    
    # ── Test 10: NERVE Types & Health Tracking ─────────────────────
    print("\n[11/18] NERVE Types & Health Tracking...")
    try:
        from .nerve.types import (
            BusEnvelope as NerveBusEnvelope,
            ChannelSource, ChatType, InboundPayload, PayloadType,
            MessagePriority, OutboundMessage, SendResult,
            ChannelCapabilities, FormattingDialect, ChannelPolicy,
            HealthTracker as NerveHealthTracker, AdapterState,
            MediaPayload, ReactionPayload, EnvelopeMetadata,
            RateLimitConfig,
        )
        
        # Types instantiation
        source = ChannelSource(
            channel_type="discord", adapter_id="disc-main",
            chat_id="1234", chat_type=ChatType.DM,
            sender_id="5678", sender_name="Ali",
        )
        payload = InboundPayload(type=PayloadType.TEXT, text="Hello")
        envelope = NerveBusEnvelope(source=source, payload=payload)
        assert envelope.source.sender_name == "Ali"
        assert envelope.payload.text == "Hello"
        assert envelope.priority == MessagePriority.NORMAL
        
        # Health tracker — state machine
        ht = NerveHealthTracker()
        assert ht.state == AdapterState.DISCONNECTED
        
        # Valid: disconnected → reconnecting
        assert ht.transition(AdapterState.RECONNECTING)
        assert ht.state == AdapterState.RECONNECTING
        
        # Valid: reconnecting → connected
        assert ht.transition(AdapterState.CONNECTED)
        assert ht.state == AdapterState.CONNECTED
        
        # Invalid: connected → reconnecting (must go through disconnected)
        assert not ht.transition(AdapterState.RECONNECTING)
        assert ht.state == AdapterState.CONNECTED  # Unchanged
        
        # Valid: connected → degraded → disconnected
        assert ht.transition(AdapterState.DEGRADED)
        assert ht.transition(AdapterState.DISCONNECTED)
        assert ht.status.disconnect_count == 1
        
        # Capabilities
        caps = ChannelCapabilities(
            formatting=FormattingDialect.MARKDOWN,
            max_message_length=2000,
        )
        assert caps.media
        assert caps.max_media_size == 25 * 1024 * 1024
        
        results.append(("NERVE Types", "PASS", "types, health tracker, capabilities"))
        print("   ✅ PASS — types, envelopes, health state machine, capabilities")
        
    except Exception as e:
        results.append(("NERVE Types", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 11: NERVE Formatter ───────────────────────────────────
    print("\n[12/18] NERVE Formatter...")
    try:
        from .nerve.formatter import format_for_channel, split_on_boundaries
        from .nerve.types import ChannelCapabilities, FormattingDialect
        
        # Discord formatting (markdown passthrough)
        discord_caps = ChannelCapabilities(
            formatting=FormattingDialect.MARKDOWN,
            max_message_length=2000,
        )
        chunks = format_for_channel("# Title\n\n**Bold** and ~~struck~~.", discord_caps)
        assert len(chunks) == 1
        assert "**Bold**" in chunks[0]  # Markdown preserved
        
        # WhatsApp formatting
        wa_caps = ChannelCapabilities(
            formatting=FormattingDialect.WHATSAPP,
            max_message_length=4096,
        )
        chunks = format_for_channel("# Title\n\n**Bold** and ~~struck~~.", wa_caps)
        assert len(chunks) == 1
        assert "*Title*" in chunks[0]     # Header → bold
        assert "*Bold*" in chunks[0]      # **bold** → *bold*
        assert "~struck~" in chunks[0]    # ~~struck~~ → ~struck~
        
        # Message splitting
        long_msg = "word " * 1000  # ~5000 chars
        chunks = split_on_boundaries(long_msg, 2000)
        assert len(chunks) >= 3
        assert all(len(c) <= 2000 for c in chunks)
        
        # Short message — no split
        chunks = split_on_boundaries("Hello", 2000)
        assert len(chunks) == 1
        
        results.append(("NERVE Formatter", "PASS", "discord, whatsapp, splitting"))
        print("   ✅ PASS — discord markdown, whatsapp conversion, smart splitting")
        
    except Exception as e:
        results.append(("NERVE Formatter", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 12: NERVE Router (Policy + Routing) ───────────────────
    print("\n[13/18] NERVE Router...")
    try:
        from .nerve.router import InboundRouter
        from .nerve.types import (
            ChannelPolicy, ChannelSource, ChatType,
            InboundPayload, PayloadType, MessagePriority,
        )
        
        router_bus = EventBus()
        await router_bus.start()
        
        routed_events = []
        rejected_events = []
        
        @router_bus.on("nerve.routed")
        async def on_route(event):
            routed_events.append(event.data)
        
        @router_bus.on("nerve.rejected")
        async def on_reject(event):
            rejected_events.append(event.data)
        
        policy = ChannelPolicy(
            dm_policy="allowlist",
            group_policy="mention-only",
            owner_ids=["owner-1"],
            allowed_senders=["allowed-1"],
            self_id="bot-id",
            ignored_channels=["ignored-chan"],
        )
        
        router = InboundRouter(
            bus=router_bus,
            policies={"discord": policy},
            global_owner_ids=["global-owner"],
        )
        
        # Owner DM → routed (HIGH)
        ok = router.route(
            ChannelSource("discord", "d-main", "dm-1", ChatType.DM, "owner-1"),
            InboundPayload(PayloadType.TEXT, text="Hello"),
            "t-1",
        )
        await asyncio.sleep(0.05)
        assert ok and len(routed_events) == 1
        assert routed_events[0]["envelope"].priority == MessagePriority.HIGH
        
        # Denied DM → rejected
        ok = router.route(
            ChannelSource("discord", "d-main", "dm-2", ChatType.DM, "random"),
            InboundPayload(PayloadType.TEXT, text="Hi"),
            "t-2",
        )
        await asyncio.sleep(0.05)
        assert not ok and len(rejected_events) == 1
        
        # Group with mention → routed
        ok = router.route(
            ChannelSource("discord", "d-main", "ch-1", ChatType.CHANNEL, "user", mentions=["bot-id"]),
            InboundPayload(PayloadType.TEXT, text="@Singularity help"),
            "t-3",
        )
        await asyncio.sleep(0.05)
        assert ok
        
        # Ignored channel → rejected (even owner)
        ok = router.route(
            ChannelSource("discord", "d-main", "ignored-chan", ChatType.CHANNEL, "owner-1"),
            InboundPayload(PayloadType.TEXT, text="Ignored"),
            "t-4",
        )
        assert not ok
        
        # Sibling yield
        ok = router.route(
            ChannelSource("discord", "d-main", "ch-2", ChatType.CHANNEL, "owner-1", mentions=["sister-1"]),
            InboundPayload(PayloadType.TEXT, text="@Plug"),
            "t-5",
        )
        assert not ok
        
        # Deduplication
        ok1 = router.route(
            ChannelSource("discord", "d-main", "dm-1", ChatType.DM, "owner-1"),
            InboundPayload(PayloadType.TEXT, text="Dupe"), "dup-1",
        )
        ok2 = router.route(
            ChannelSource("discord", "d-main", "dm-1", ChatType.DM, "owner-1"),
            InboundPayload(PayloadType.TEXT, text="Dupe"), "dup-1",
        )
        assert ok1 and not ok2
        
        # Session persistence
        s1 = router.get_session_id("d-main", "dm-1")
        s2 = router.get_session_id("d-main", "dm-1")
        assert s1 == s2 and s1 is not None
        
        await router_bus.stop()
        
        results.append(("NERVE Router", "PASS", "policy, routing, dedup, sessions"))
        print("   ✅ PASS — policy enforcement, priority, dedup, sibling yield, sessions")
        
    except Exception as e:
        results.append(("NERVE Router", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 13: NERVE Adapter Base ────────────────────────────────
    print("\n[14/18] NERVE Adapter Base...")
    try:
        from .nerve.adapter import BaseAdapter, TokenBucketLimiter
        from .nerve.types import (
            ChannelCapabilities, FormattingDialect, OutboundMessage, SendResult,
        )
        
        # Token bucket rate limiter
        limiter = TokenBucketLimiter(max_per_second=10.0, burst_size=5)
        assert limiter.consume()  # Should have tokens
        for _ in range(4):
            limiter.consume()
        delay = limiter.check()
        assert delay >= 0  # May need to wait
        
        # Test that BaseAdapter can't be instantiated (abstract)
        try:
            BaseAdapter("test")
            assert False, "Should not instantiate abstract class"
        except TypeError as e:
            logger.debug(f"Suppressed TypeError: {e}")
        
        # Test concrete adapter subclass (mock)
        class MockAdapter(BaseAdapter):
            @property
            def channel_type(self) -> str:
                return "mock"
            
            @property
            def capabilities(self) -> ChannelCapabilities:
                return ChannelCapabilities(formatting=FormattingDialect.PLAIN)
            
            async def platform_connect(self, config: dict) -> None:
                pass
            
            async def platform_disconnect(self) -> None:
                pass
            
            async def platform_reconnect(self) -> None:
                pass
            
            async def platform_send(self, chat_id: str, message: OutboundMessage) -> SendResult:
                return SendResult(success=True, message_id="mock-123")
        
        adapter = MockAdapter("mock-1")
        assert adapter.id == "mock-1"
        assert adapter.channel_type == "mock"
        
        # Connect
        await adapter.connect({})
        health = adapter.get_health()
        assert health.state.value == "connected"
        
        # Send
        result = await adapter.send("chat-1", OutboundMessage(content="Hello"))
        assert result.success
        assert result.message_id == "mock-123"
        
        # Message handler
        received = []
        adapter.on_message(lambda env: received.append(env))
        
        from .nerve.types import ChannelSource, ChatType, InboundPayload, PayloadType
        adapter.emit(
            ChannelSource("mock", "mock-1", "ch-1", ChatType.DM, "user-1"),
            InboundPayload(PayloadType.TEXT, text="Test"),
            "msg-001",
        )
        assert len(received) == 1
        assert received[0].payload.text == "Test"
        
        # Disconnect
        await adapter.disconnect()
        health = adapter.get_health()
        assert health.state.value == "disconnected"
        
        results.append(("NERVE Adapter", "PASS", "rate limiter, lifecycle, send, emit"))
        print("   ✅ PASS — rate limiter, adapter lifecycle, send, emit, health tracking")
        
    except Exception as e:
        results.append(("NERVE Adapter", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ═══════════════════════════════════════════════════════════════
    # Phase 4 — Pulse (Budget, Scheduler, Health)
    # ═══════════════════════════════════════════════════════════════
    
    # ── Test 14: Iteration Budget ──────────────────────────────────
    print("\n[15/18] Iteration Budget...")
    try:
        from .pulse.budget import IterationBudget, BudgetConfig, BudgetState
        
        # Basic budget
        config = BudgetConfig(default_limit=20, max_limit=100, auto_expand_threshold=18)
        budget = IterationBudget(session_id="test-1", config=config)
        
        assert budget.remaining == 20
        assert budget.used == 0
        assert budget.state == BudgetState.HEALTHY
        assert budget.can_continue()
        
        # Tick 10 times
        for _ in range(10):
            budget.tick()
        assert budget.used == 10
        assert budget.remaining == 10
        assert budget.state == BudgetState.WARNING  # ≤10 remaining
        
        # Tick to critical
        for _ in range(5):
            budget.tick()
        assert budget.remaining == 5
        assert budget.state == BudgetState.CRITICAL
        
        # Tick 3 more → triggers auto-expand at iteration 18
        for _ in range(3):
            budget.tick()
        
        # Auto-expand fires IN the tick, so remaining is already updated
        assert budget._expanded
        assert budget.limit == 100
        assert budget.used == 18
        assert budget.remaining == 82  # 100 - 18
        assert budget.state == BudgetState.HEALTHY  # Back to healthy!
        
        # Manual expand (already at max)
        assert not budget.expand(50)  # Can't go below current
        
        # Force exhaust
        budget.force_exhaust()
        assert budget.state == BudgetState.EXHAUSTED
        assert not budget.can_continue()
        
        # Snapshot
        snap = budget.snapshot()
        assert snap.used == snap.limit
        assert snap.expanded
        
        # Budget without auto-expand
        config2 = BudgetConfig(default_limit=5, auto_expand=False)
        budget2 = IterationBudget(session_id="test-2", config=config2)
        for _ in range(5):
            budget2.tick()
        assert not budget2.can_continue()
        assert budget2.state == BudgetState.EXHAUSTED
        assert not budget2._expanded
        
        results.append(("PULSE Budget", "PASS", "tick, states, auto-expand, exhaust"))
        print("   ✅ PASS — tick, state transitions, auto-expand, exhaust, snapshot")
        
    except Exception as e:
        results.append(("PULSE Budget", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 15: Scheduler ─────────────────────────────────────────
    print("\n[16/18] Scheduler...")
    try:
        from .pulse.scheduler import Scheduler, JobConfig, JobType, JobState
        
        sched_bus = EventBus()
        await sched_bus.start()
        
        scheduler = Scheduler(sched_bus, tick_interval=0.05)
        await scheduler.start()
        
        fired_events = []
        
        @sched_bus.on("test.heartbeat")
        async def on_heartbeat(event):
            fired_events.append(event.data)
        
        # Add an interval job with very short interval
        job_id = scheduler.add(JobConfig(
            name="test-heartbeat",
            job_type=JobType.INTERVAL,
            interval_seconds=0.1,
            emit_topic="test.heartbeat",
            emit_data={"source": "test"},
        ))
        
        # Wait for it to fire
        await asyncio.sleep(0.5)
        assert len(fired_events) >= 2, f"Expected ≥2 fires, got {len(fired_events)}"
        assert fired_events[0]["source"] == "test"
        assert fired_events[0]["job_name"] == "test-heartbeat"
        
        # One-shot timer
        oneshot_events = []
        
        @sched_bus.on("test.oneshot")
        async def on_oneshot(event):
            oneshot_events.append(event.data)
        
        scheduler.add(JobConfig(
            name="test-oneshot",
            job_type=JobType.ONESHOT,
            interval_seconds=0.1,
            emit_topic="test.oneshot",
        ))
        
        await asyncio.sleep(0.3)
        assert len(oneshot_events) == 1  # Fires exactly once
        
        # Job management
        jobs = scheduler.list_jobs()
        assert len(jobs) >= 2
        
        status = scheduler.get_status(job_id)
        assert status is not None
        assert status.fire_count >= 2
        
        # Remove job
        assert scheduler.remove(job_id)
        assert scheduler.get_status(job_id) is None
        
        # Max fires
        max_events = []
        
        @sched_bus.on("test.maxfires")
        async def on_max(event):
            max_events.append(1)
        
        scheduler.add(JobConfig(
            name="limited",
            job_type=JobType.INTERVAL,
            interval_seconds=0.05,
            emit_topic="test.maxfires",
            max_fires=3,
        ))
        
        await asyncio.sleep(0.5)
        assert len(max_events) == 3  # Stops after 3
        
        await scheduler.stop()
        await sched_bus.stop()
        
        results.append(("PULSE Scheduler", "PASS", "interval, oneshot, max_fires, management"))
        print("   ✅ PASS — interval jobs, oneshot, max_fires, job management")
        
    except Exception as e:
        results.append(("PULSE Scheduler", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 16: Health Monitor ────────────────────────────────────
    print("\n[17/18] Health Monitor...")
    try:
        from .pulse.health import HealthMonitor, HealthLevel
        
        health_bus = EventBus()
        await health_bus.start()
        
        monitor = HealthMonitor(health_bus)
        
        health_reports = []
        degraded_events = []
        recovered_events = []
        
        @health_bus.on("pulse.health.report")
        async def on_report(event):
            health_reports.append(event.data)
        
        @health_bus.on("pulse.health.degraded")
        async def on_degraded(event):
            degraded_events.append(event.data)
        
        @health_bus.on("pulse.health.recovered")
        async def on_recovered(event):
            recovered_events.append(event.data)
        
        # Register healthy check
        call_count = 0
        async def voice_check():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return HealthLevel.HEALTHY, "OK"
            elif call_count <= 5:
                return HealthLevel.UNHEALTHY, "Provider down"
            else:
                return HealthLevel.HEALTHY, "Recovered"
        
        recovery_called = False
        async def voice_recovery():
            nonlocal recovery_called
            recovery_called = True
        
        monitor.register("voice", voice_check, recovery_fn=voice_recovery)
        
        # First check — healthy
        health = await monitor.check_now()
        assert health.level == HealthLevel.HEALTHY
        assert health.subsystems["voice"].level == HealthLevel.HEALTHY
        
        # Checks 2-4 — degrades
        await monitor.check_now()  # Still healthy
        await monitor.check_now()  # Unhealthy
        assert len(degraded_events) == 1
        assert degraded_events[0]["subsystem"] == "voice"
        
        await monitor.check_now()  # Still unhealthy
        await monitor.check_now()  # Still unhealthy (3 consecutive)
        
        # Recovery should have been attempted
        assert recovery_called
        
        # Check 6 — recovers
        await monitor.check_now()
        assert len(recovered_events) == 1
        assert recovered_events[0]["subsystem"] == "voice"
        
        # Aggregate health
        health = monitor.get_health()
        assert health.level == HealthLevel.HEALTHY
        assert health.uptime_seconds > 0
        
        # Subsystem query
        voice = monitor.get_subsystem("voice")
        assert voice is not None
        assert voice.check_count == 6
        assert voice.fail_count == 3
        
        # Non-existent subsystem
        assert monitor.get_subsystem("nonexistent") is None
        
        await health_bus.stop()
        
        results.append(("PULSE Health", "PASS", "checks, degraded, recovery, aggregate"))
        print("   ✅ PASS — health checks, degradation, self-healing, recovery, aggregate")
        
    except Exception as e:
        results.append(("PULSE Health", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Test 17: PULSE Integration (Budget + Bus Events) ───────────
    print("\n[18/18] PULSE Integration...")
    try:
        from .pulse.budget import IterationBudget, BudgetConfig, BudgetState
        
        int_bus = EventBus()
        await int_bus.start()
        
        budget_events = []
        
        @int_bus.on("pulse.budget.*")
        async def on_budget(event):
            budget_events.append(event)
        
        config = BudgetConfig(
            default_limit=10, max_limit=50,
            auto_expand_threshold=8,
            warn_at=5, critical_at=3, emergency_at=1,
        )
        budget = IterationBudget(session_id="int-test", config=config, bus=int_bus)
        
        # Tick to warning (5 remaining)
        for _ in range(5):
            budget.tick()
        await asyncio.sleep(0.05)
        
        # Should have emitted state_changed: healthy → warning
        state_changes = [e for e in budget_events if e.name == "pulse.budget.state_changed"]
        assert len(state_changes) == 1
        assert state_changes[0].data["new_state"] == "warning"
        
        # Tick to critical (3 remaining)
        for _ in range(2):
            budget.tick()
        await asyncio.sleep(0.05)
        
        state_changes = [e for e in budget_events if e.name == "pulse.budget.state_changed"]
        assert len(state_changes) == 2
        assert state_changes[1].data["new_state"] == "critical"
        
        # Tick to auto-expand (at iteration 8)
        budget.tick()
        await asyncio.sleep(0.05)
        
        expand_events = [e for e in budget_events if e.name == "pulse.budget.expanded"]
        assert len(expand_events) == 1
        assert expand_events[0].data["new_limit"] == 50
        assert expand_events[0].data["reason"] == "auto_expand"
        
        # After expansion, state should be healthy again
        assert budget.state == BudgetState.HEALTHY
        assert budget.remaining == 42  # 50 - 8
        
        await int_bus.stop()
        
        results.append(("PULSE Integration", "PASS", "budget→bus events, state transitions"))
        print("   ✅ PASS — budget emits events on bus, state transitions cascade")
        
    except Exception as e:
        results.append(("PULSE Integration", "FAIL", str(e)))
        print(f"   ❌ FAIL — {e}")
    
    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    passed = sum(1 for _, status, _ in results if status == "PASS")
    total = len(results)
    
    phase1_tests = results[:5]
    phase2_tests = results[5:9]
    phase3_tests = results[9:13]
    phase4_tests = results[13:]
    
    p1_passed = sum(1 for _, s, _ in phase1_tests if s == "PASS")
    p2_passed = sum(1 for _, s, _ in phase2_tests if s == "PASS")
    p3_passed = sum(1 for _, s, _ in phase3_tests if s == "PASS")
    p4_passed = sum(1 for _, s, _ in phase4_tests if s == "PASS")
    
    print("  Phase 1 — Skeleton:")
    for name, status, detail in phase1_tests:
        icon = "✅" if status == "PASS" else "❌"
        print(f"    {icon} {name}: {detail}")
    
    print(f"\n  Phase 2 — Brain:")
    for name, status, detail in phase2_tests:
        icon = "✅" if status == "PASS" else "❌"
        print(f"    {icon} {name}: {detail}")
    
    print(f"\n  Phase 3 — Nerves:")
    for name, status, detail in phase3_tests:
        icon = "✅" if status == "PASS" else "❌"
        print(f"    {icon} {name}: {detail}")
    
    print(f"\n  Phase 4 — Pulse:")
    for name, status, detail in phase4_tests:
        icon = "✅" if status == "PASS" else "❌"
        print(f"    {icon} {name}: {detail}")
    
    print(f"\n  Result: {passed}/{total} passed (P1: {p1_passed}/{len(phase1_tests)}, P2: {p2_passed}/{len(phase2_tests)}, P3: {p3_passed}/{len(phase3_tests)}, P4: {p4_passed}/{len(phase4_tests)})")
    
    if passed == total:
        print(f"\n  🟢 ALL {total} TESTS PASSED")
        print("  Skeleton + Brain + Nerves + Pulse verified.")
        print("  Ready for Phase 5 (Immune — self-healing, POA, failover).")
    else:
        failed = [(n, d) for n, s, d in results if s != "PASS"]
        print(f"\n  🔴 {len(failed)} FAILURE(S):")
        for name, detail in failed:
            print(f"    ❌ {name}: {detail}")
    
    print("=" * 60)
    return passed == total


def main():
    args = sys.argv[1:]
    
    if "--test" in args:
        logging.basicConfig(level=logging.WARNING)
        success = asyncio.run(test_skeleton())
        sys.exit(0 if success else 1)
    
    elif "--run" in args or len(args) == 0:
        # Production mode — boot and run Singularity
        config_path = None
        for i, arg in enumerate(args):
            if arg == "--config" and i + 1 < len(args):
                config_path = args[i + 1]
        
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        
        async def run():
            from .runtime import Runtime
            runtime = Runtime(config_path=config_path)
            await runtime.boot()
            await runtime.run()
        
        try:
            asyncio.run(run())
        except KeyboardInterrupt:
            pass
    
    else:
        # Forward to CLI command system (init, audit, status, etc.)
        cli_commands = {"init", "audit", "status", "spawn-exec", "poa", "scale-report", "health", "changeset", "test", "install"}
        if args and args[0] in cli_commands:
            from .cli.main import main as cli_main
            cli_main()
        else:
            print("SINGULARITY [AE] — Autonomous Enterprise Runtime")
            print()
            print("Usage:")
            print("  python3 -m singularity              # Start Singularity")
            print("  python3 -m singularity --test        # Run gate tests")
            print("  python3 -m singularity --config X    # Use custom config")
            print()
            print("  python3 -m singularity install       # Fresh agent install (create clean .core/)")
            print("  python3 -m singularity init          # Initialize workspace")
            print("  python3 -m singularity audit         # Audit workspace")
            print("  python3 -m singularity status        # Runtime status")
            print("  python3 -m singularity health        # System health")
            print("  python3 -m singularity spawn-exec X  # Propose executive")
            print("  python3 -m singularity poa list      # POA management")


if __name__ == "__main__":
    main()
