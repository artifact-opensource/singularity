# Infrastructure

Singularity runs on a primary server (Dragonfly) with a secondary GPU forge (Victus) for training workloads.

---

## Dragonfly — Primary Server (192.168.1.13)

The main compute node running all Artifact Virtual services.

### Services

| Service | Port | Protocol | Description |
|---------|------|----------|-------------|
| Singularity Runtime | Discord + :8450 | WebSocket + HTTP | Core runtime |
| Copilot Proxy | :3000 | HTTP | LLM provider proxy |
| COMB Cloud | :8420 / :8700-8701 | HTTP | Memory persistence cloud |
| Mach6 Gateway (AVA) | :3006 / :3009 | HTTP | AVA's runtime gateway |
| Aria Gateway | :3007 / :3010 | HTTP | Aria's gateway |
| Artifact ERP | :3100 / :8750 | HTTP | Enterprise resource planning |
| GDI Backend | :8600 | HTTP | Global Defense Intelligence API |
| GDI Landing | :8601 | HTTP | GDI public landing page |
| HEKTOR Daemon | — | IPC | Enterprise knowledge search |
| Sentinel | — | IPC | Security monitoring (ExfilGuard + OpenAnt) |
| Ollama | :11434 | HTTP | Local LLM fallback |
| Cthulu Daemon | :9002 | HTTP | Infrastructure daemon |
| Singularity Landing | :8780 | HTTP | Public landing page |
| Symbiote | :8770 | HTTP | Symbiote service |
| Nginx | :80 / :443 | HTTP | Reverse proxy |
| Cloudflared | — | Tunnel | Cloudflare Argo Tunnel |

### Service Management

All services run as **systemd user services**:

```bash
systemctl --user status singularity      # Check status
systemctl --user restart singularity     # Restart
systemctl --user stop singularity        # Stop
journalctl --user -u singularity -f      # Follow logs
```

---

## Victus — GPU Forge (192.168.1.15)

Secondary machine for GPU-accelerated workloads.

| Component | Spec |
|-----------|------|
| OS | Windows 11 + WSL2 Ubuntu 24.04 |
| GPU | NVIDIA RTX 2050 (4GB VRAM) |
| Storage | 1TB NVMe |
| SSH | `victus` (Win) / `victus-wsl` (WSL2) |

**Workloads:**
- GLADIUS model training
- MT5 bridge operations
- GPU compute tasks

---

## Public URLs

| URL | Product | Backend |
|-----|---------|---------|
| singularity.artifactvirtual.com | Singularity Landing | :8780 |
| erp.artifactvirtual.com | Artifact ERP | :8750 |
| gdi.artifactvirtual.com | GDI Landing | :8601 |
| comb.artifactvirtual.com | COMB Cloud | :8420 |
| mach6.artifactvirtual.com | Mach6 (AVA) | :3006 |
| symbiote.artifactvirtual.com | Symbiote | :8770 |
| gladius-three.vercel.app | GLADIUS | Vercel |
| artifactvirtual.com | Main Website | External |

All public URLs are proxied through **Cloudflare Argo Tunnel** → **Nginx** → **backend service**.

---

## Networking

```
Internet
    │
    ▼
Cloudflare (DNS + CDN + WAF)
    │
    ▼
Cloudflare Argo Tunnel (encrypted)
    │
    ▼
Nginx Reverse Proxy (Dragonfly)
    │
    ├── /singularity → :8780
    ├── /erp         → :8750
    ├── /gdi         → :8601
    ├── /comb        → :8420
    └── ...
```

---

## Monitoring

- **POA agents** monitor all public endpoints every 4 hours
- **IMMUNE subsystem** watches internal service health
- **Sentinel** monitors network traffic for anomalies
- **ATLAS** tracks enterprise-wide topology and module health

---

*Next: [Security →](security.md)*
