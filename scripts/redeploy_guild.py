#!/usr/bin/env python3
"""
Redeploy SINGULARITY channels to a guild.

1. Deletes all channels under the SINGULARITY category
2. Deletes the SINGULARITY category itself  
3. Triggers a fresh deploy via the GuildDeployer

Usage:
    python3 scripts/redeploy_guild.py <guild_id> [--token TOKEN]
    
The token defaults to the one in config/singularity.yaml.
"""

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import discord
    from discord import Intents
except ImportError:
    print("❌ discord.py not installed")
    sys.exit(1)

from singularity.nerve.deployer import GuildDeployer, CATEGORY_NAME

# ── Config ────────────────────────────────────────────────────

SINGULARITY_ROOT = Path(__file__).parent.parent
CONFIG_PATH = SINGULARITY_ROOT / "config" / "singularity.yaml"

# C-Suite exec roles (same as runtime.py)
EXEC_ROLES = [
    ("cto", "🔧", "Chief Technology Officer", "Engineering, infrastructure, architecture"),
    ("coo", "📋", "Chief Operating Officer", "Operations, workflows, HR, compliance"),
    ("cfo", "💰", "Chief Financial Officer", "Finance, budgets, reporting, revenue"),
    ("ciso", "🛡️", "Chief Information Security Officer", "Security, GRC, risk management"),
]


def load_token_from_config() -> str:
    """Load bot token from singularity.yaml."""
    try:
        import yaml
        data = yaml.safe_load(CONFIG_PATH.read_text())
        return data.get("discord", {}).get("token", "")
    except ImportError:
        # Fallback: grep
        for line in CONFIG_PATH.read_text().splitlines():
            line = line.strip()
            if line.startswith("token:"):
                return line.split(":", 1)[1].strip().strip("'\"")
    return ""


async def redeploy(guild_id: int, token: str):
    """Delete existing SINGULARITY channels and redeploy fresh."""
    
    intents = Intents.default()
    intents.guilds = True
    intents.message_content = True
    
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f"\n  ✅ Bot ready: {client.user}")
        
        guild = client.get_guild(guild_id)
        if not guild:
            try:
                guild = await client.fetch_guild(guild_id)
            except Exception as e:
                print(f"  ❌ Guild {guild_id} not found: {e}")
                await client.close()
                return
        
        print(f"  📍 Guild: {guild.name} ({guild.id})")
        
        # ── Step 1: Find and delete existing SINGULARITY category ──
        category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        
        if category:
            print(f"\n  🗑️  Deleting existing {CATEGORY_NAME} category...")
            
            # Delete all channels under the category
            for channel in category.channels:
                print(f"    Deleting #{channel.name} ({channel.id})...")
                try:
                    await channel.delete(reason="Singularity redeploy — clean slate")
                    await asyncio.sleep(0.5)  # Rate limit
                except Exception as e:
                    print(f"    ⚠️  Failed to delete #{channel.name}: {e}")
            
            # Delete the category itself
            print(f"    Deleting category {CATEGORY_NAME} ({category.id})...")
            try:
                await category.delete(reason="Singularity redeploy — clean slate")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"    ⚠️  Failed to delete category: {e}")
            
            print(f"  ✅ Old deployment cleaned")
        else:
            print(f"\n  ℹ️  No existing {CATEGORY_NAME} category found")
        
        # ── Step 2: Deploy fresh ──
        print(f"\n  🚀 Deploying fresh {CATEGORY_NAME}...")
        
        deployer = GuildDeployer(
            exec_roles=EXEC_ROLES,
            private=True,
            sg_dir=SINGULARITY_ROOT / ".singularity",
            authorized_user_ids=[
                "OWNER_DISCORD_ID",    # Ali
                "1478396689642688634",   # AVA bot
            ],
        )
        
        result = await deployer.deploy(guild)
        
        if result.success:
            print(f"\n  ✅ Deployment successful!")
            print(f"  📁 Category: {result.category_id}")
            print(f"\n  Channels:")
            for name, ch_id in result.channels.items():
                print(f"    #{name}: {ch_id}")
            print(f"\n  Webhooks:")
            for name, url in result.webhooks.items():
                # Truncate webhook URL for display
                short = url[:60] + "..." if len(url) > 60 else url
                print(f"    {name}: {short}")
            
            # Save deployment result
            deploy_path = SINGULARITY_ROOT / ".singularity" / "deployments" / f"{guild_id}.json"
            print(f"\n  💾 Saved to: {deploy_path}")
            
            # Print config update needed
            print(f"\n  ── Update config/singularity.yaml with: ──")
            print(f"  immune:")
            print(f"    alert_channels:")
            bridge_id = result.channels.get("bridge", "???")
            print(f"    - '{bridge_id}'")
            
        else:
            print(f"\n  ❌ Deployment failed!")
            for err in result.errors:
                print(f"    • {err}")
        
        await client.close()
    
    await client.start(token)


def main():
    parser = argparse.ArgumentParser(description="Redeploy SINGULARITY channels")
    parser.add_argument("guild_id", type=int, help="Discord guild/server ID")
    parser.add_argument("--token", "-t", help="Bot token (default: from config)")
    
    args = parser.parse_args()
    
    token = args.token or load_token_from_config()
    if not token:
        print("❌ No bot token. Provide --token or ensure config/singularity.yaml has it.")
        sys.exit(1)
    
    print(f"\n  SINGULARITY — Guild Redeploy")
    print(f"  {'=' * 40}")
    print(f"  Guild: {args.guild_id}")
    print(f"  Action: Delete old → Deploy fresh")
    
    asyncio.run(redeploy(args.guild_id, token))


if __name__ == "__main__":
    main()
