# WSL, proxies, and intranet OpenAI-compatible models

When DeerFlow runs inside **WSL2** on Windows and the LLM is served on a **LAN address** (e.g. `10.131.x.x`), two issues often appear:

1. **HTTP(S) proxy** — If `HTTP_PROXY` points at v2rayN on Windows, tools must **bypass the proxy** for private ranges or traffic is sent to the wrong place.
2. **No route to `10.x` from WSL** — Even with `networkingMode=mirrored` in `.wslconfig`, WSL may still **time out** to some lab/VLAN hosts while **Windows** can reach them.

The reliable pattern is: run a small **HTTP forwarder on Windows** that listens on `127.0.0.1` (or `0.0.0.0`) and proxies to the intranet API. WSL then uses **`http://127.0.0.1:<port>/v1`** as `base_url` in `config.yaml`.

## Windows: forwarder and optional firewall

From the **DeerFlow repo root** on Windows (PowerShell):

```powershell
# One-time: startup shortcut + optional checks (run as Administrator if you need the firewall rule it prints)
powershell -ExecutionPolicy Bypass -File .\scripts\setup-windows-model-forwarder.ps1

# Start forwarder now (default: 55001 -> http://10.131.12.157:50001)
powershell -ExecutionPolicy Bypass -File .\scripts\start-win-forwarder.ps1
```

Upstream URL and port can be changed with `-TargetBase` and `-ListenPort` on both scripts.

If WSL cannot connect to `127.0.0.1:55001`, add an inbound firewall rule (elevated PowerShell):

```powershell
New-NetFirewallRule -DisplayName "DeerFlow model forwarder TCP 55001" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 55001
```

## `config.yaml`

Point the OpenAI-compatible model at the forwarder:

```yaml
base_url: http://127.0.0.1:55001/v1
```

See comments next to `Qwen3.5-27B` in the repo `config.yaml` for the exact upstream example.

## `.env` and WSL shell (NO_PROXY)

If `HTTP_PROXY` / `HTTPS_PROXY` are set for GitHub or web tools, ensure intranet hosts are excluded, for example:

```env
NO_PROXY=localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
```

The repo `.env` already includes a similar line; keep it when using a proxy.

For a permanent WSL setup, `scripts/wsl-v2ray-env.sh` (documented in its header) sets proxy detection and `NO_PROXY`. Avoid a GitHub `http` section with an **empty** `proxy =` in `~/.gitconfig` — that can stall `git push`.

## Verify end-to-end

**1. HTTP from WSL**

```bash
curl -sS --connect-timeout 8 "http://127.0.0.1:55001/v1/models" \
  -H "Authorization: Bearer <your-api-key-from-config>"
```

**2. Same code path as DeerFlow (LangChain + `config.yaml`)**

From `backend/`:

```bash
cd backend && uv run python ../scripts/test_model_connection.py Qwen3.5-27B
```

A successful run prints `OK` after a short model reply.

## Scripts reference

| Script | Role |
|--------|------|
| `scripts/windows_openai_forward.py` | HTTP forwarder implementation |
| `scripts/start-win-forwarder.ps1` | Start forwarder (hidden `py` process) |
| `scripts/setup-windows-model-forwarder.ps1` | Startup shortcut + firewall instructions |
| `scripts/test_model_connection.py` | Smoke-test configured model |
| `scripts/wsl-v2ray-env.sh` | Optional WSL proxy + NO_PROXY helper |
