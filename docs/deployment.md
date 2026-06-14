# Deployment

> Production deployment — systemd, hardening, multi-machine topology.

## Prerequisites

- Python 3.11+
- systemd (for service management)
- Discord bot token (for Discord adapter)
- LLM provider (Copilot proxy, Ollama, or HuggingFace)

## Single-Machine Deployment

### 1. Clone & Install

```bash
git clone https://github.com/Artifact-Virtual/singularity.git
cd singularity
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env with your tokens and endpoints
```

### 3. Create systemd Service

Create `~/.config/systemd/user/singularity.service`:

```ini
[Unit]
Description=Singularity [AE] — Autonomous Enterprise Runtime
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/deploy/workspace/singularity
ExecStart=/home/deploy/workspace/singularity/.venv/bin/python -m singularity
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1
StandardOutput=journal
StandardError=journal
MemorySwapMax=0

[Install]
WantedBy=default.target
```

### 4. Enable & Start

```bash
systemctl --user daemon-reload
systemctl --user enable singularity
systemctl --user start singularity

# Enable lingering so service runs without active login
loginctl enable-linger $(whoami)
```

### 5. Verify

```bash
systemctl --user status singularity
curl http://localhost:8450/health
```

---

## Production Hardening

### Reverse Proxy (Nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name singularity.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8450;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }

    location / {
        root /var/www/singularity;
        index index.html;
    }
}
```

### Cloudflare Tunnel (Zero-Trust)

If using Cloudflare Tunnel (recommended for zero-trust):

```bash
# Config in /etc/cloudflared/config.yml
tunnel: <TUNNEL_ID>
credentials-file: /root/.cloudflared/<TUNNEL_ID>.json

ingress:
  - hostname: singularity.yourdomain.com
    service: http://localhost:8780
  - hostname: erp.yourdomain.com
    service: http://localhost:8750
  - service: http_status:404
```

### Resource Limits

Recommended system resources:
- **RAM:** 4GB minimum, 8GB recommended
- **CPU:** 2 cores minimum
- **Disk:** 10GB for codebase + logs + VDB

systemd memory limits:
```ini
MemoryMax=4G
MemorySwapMax=0
```

### Log Management

Singularity logs to systemd journal:

```bash
# View logs
journalctl --user -u singularity -f

# View last 100 lines
journalctl --user -u singularity -n 100 --no-pager

# Export logs
journalctl --user -u singularity --since "2026-03-01" > singularity.log
```

---

## Multi-Machine Topology

Singularity supports distributed deployment via ATLAS topology tracking.

### Primary (Dragonfly — 192.168.1.13)

Runs all core services:
- Singularity runtime (Discord + :8450)
- Copilot Proxy (:3000)
- COMB Cloud (:8420 / :8700-8701)
- Nginx reverse proxy
- Cloudflared tunnel
- Sentinel security
- HEKTOR daemon
- Ollama (:11434)

### Secondary (Victus — 192.168.1.15)

GPU compute node:
- Win11 + WSL2 Ubuntu 24.04
- RTX 2050 4GB VRAM
- Training workloads (GLADIUS)
- MT5 bridge
- SSH accessible from primary

### Adding Machines

ATLAS auto-discovers modules via SSH probing and service detection. To add a new machine:

1. Ensure SSH access from the primary
2. Add to ATLAS config
3. ATLAS will probe and register services automatically

---

## Companion Services

These services run alongside Singularity:

| Service | Port | systemd Unit | Purpose |
|---------|------|-------------|---------|
| Copilot Proxy | 3000 | `copilot-proxy` | LLM gateway |
| COMB Cloud | 8420 | `comb-cloud` | Persistence cloud |
| Mach6 Gateway | 3006/3009 | `mach6-gateway` | AVA runtime |
| Artifact ERP | 3100/8750 | `artifact-erp` | Enterprise resource planning |
| GDI Backend | 8600/8601 | `gdi-backend` | Global Defense Intelligence |
| HEKTOR | — | `hektor` | Enterprise knowledge search |
| Sentinel | — | `sentinel` | Security monitoring |
| Ollama | 11434 | `ollama` | Local LLM inference |
| Cthulu Daemon | 9002 | `cthulu-daemon` | Trading operations |

---

## Upgrades

```bash
cd /path/to/singularity
git pull origin main
pip install -e .
systemctl --user restart singularity
```

NEXUS hot-swap allows live function replacement without restart for most changes.

---

## Backup

Critical data to back up:
- `.singularity/` — VDB, sessions, COMB data
- `config/singularity.yaml` — runtime config
- `.env` — credentials (encrypt at rest)
- `executives/` — C-Suite reports and history

```bash
tar czf singularity-backup-$(date +%Y%m%d).tar.gz \
  .singularity/ config/ .env executives/
```

---

*See [Configuration](configuration.md) for tuning, [Infrastructure](infrastructure.md) for service details.*
