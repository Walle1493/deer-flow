#!/usr/bin/env bash
#
# start.sh - Start all DeerFlow development services
#
# Must be run from the repo root directory.

set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# ── Optional: Start Windows model forwarder (WSL2 mirrored networking) ────────
#
# If your model base_url points to http://127.0.0.1:55001/v1, DeerFlow expects a
# Windows-side forwarder that can reach the intranet model endpoint (10.x).
#
# Controls:
#   DEERFLOW_WIN_FORWARDER=1|0        (default: auto-detect from config.yaml)
#   DEERFLOW_WIN_FORWARDER_PORT=55001
#   DEERFLOW_WIN_FORWARDER_TARGET_BASE=http://10.131.12.157:50001
#
maybe_start_windows_forwarder() {
    # Only relevant inside WSL.
    if ! grep -qi microsoft /proc/version 2>/dev/null; then
        return 0
    fi

    local port="${DEERFLOW_WIN_FORWARDER_PORT:-55001}"
    local target_base="${DEERFLOW_WIN_FORWARDER_TARGET_BASE:-http://10.131.12.157:50001}"
    local ps_file="$REPO_ROOT/scripts/start-win-forwarder.ps1"

    local want="auto"
    if [ -n "${DEERFLOW_WIN_FORWARDER:-}" ]; then
        want="$DEERFLOW_WIN_FORWARDER"
    fi

    if [ "$want" = "auto" ]; then
        if grep -qE 'base_url:\s*http://127\.0\.0\.1:55001/v1' "$REPO_ROOT/config.yaml" 2>/dev/null; then
            want="1"
        else
            want="0"
        fi
    fi

    if [ "$want" != "1" ]; then
        return 0
    fi

    # Already listening? (fast path)
    if (exec 3<>/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then
        return 0
    fi

    if ! command -v powershell.exe >/dev/null 2>&1; then
        echo "⚠ Windows forwarder requested but powershell.exe not found in WSL PATH."
        return 0
    fi
    if [ ! -f "$ps_file" ]; then
        echo "⚠ Windows forwarder requested but $ps_file not found."
        return 0
    fi

    echo "Starting Windows model forwarder (localhost:$port -> $target_base)..."
    # Note: This does not require admin rights; firewall rule may.
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(wslpath -w "$ps_file")" -TargetBase "$target_base" -ListenPort "$port" >/dev/null 2>&1 || true

    # Wait briefly for it to come up.
    ./scripts/wait-for-port.sh "$port" 8 "Windows Forwarder" >/dev/null 2>&1 || {
        echo "⚠ Windows forwarder did not become ready on port $port."
        echo "  Try running manually on Windows:"
        echo "    powershell -ExecutionPolicy Bypass -File $(wslpath -w "$ps_file")"
    }
}

# ── Optional: Ensure proxy env for web tools ─────────────────────────────────
#
# Tavily/Jina/Feishu need outbound Internet. In WSL2 mirrored networking, Windows
# proxy ports are reachable at 127.0.0.1 (not the default gateway). In classic
# NAT mode, you may need to use the gateway IP. This function sets HTTP(S)_PROXY
# only if a proxy is detected; it won't override explicit user settings.
maybe_set_proxy_env() {
    # If user already set a proxy, keep it only if it's reachable.
    # (In mirrored networking, the correct proxy host is often 127.0.0.1, but older
    # configs may point to the default gateway and become unreachable.)
    if [ -n "${HTTP_PROXY:-}" ]; then
        # Parse http://host:port
        local hp="${HTTP_PROXY#http://}"
        hp="${hp#https://}"
        local host="${hp%%:*}"
        local port="${hp##*:}"
        if [ -n "$host" ] && [ -n "$port" ] && (exec 3<>/dev/tcp/"$host"/"$port") 2>/dev/null; then
            return 0
        fi
    fi

    local http_host=""
    local socks_host=""

    # Prefer localhost (mirrored networking / port-mapped proxy).
    if (exec 3<>/dev/tcp/127.0.0.1/10809) 2>/dev/null; then
        http_host="127.0.0.1"
    fi
    if (exec 3<>/dev/tcp/127.0.0.1/10808) 2>/dev/null; then
        socks_host="127.0.0.1"
    fi

    # Fallback: default gateway (classic WSL2 NAT).
    if [ -z "$http_host" ] || [ -z "$socks_host" ]; then
        if command -v ip >/dev/null 2>&1; then
            local gw
            gw="$(ip route show default 2>/dev/null | awk '{print $3}')"
            if [ -z "$http_host" ] && (exec 3<>/dev/tcp/"$gw"/10809) 2>/dev/null; then
                http_host="$gw"
            fi
            if [ -z "$socks_host" ] && (exec 3<>/dev/tcp/"$gw"/10808) 2>/dev/null; then
                socks_host="$gw"
            fi
        fi
    fi

    if [ -n "$http_host" ]; then
        export HTTP_PROXY="http://${http_host}:10809"
        export HTTPS_PROXY="http://${http_host}:10809"
        export http_proxy="$HTTP_PROXY"
        export https_proxy="$HTTPS_PROXY"
    fi
    if [ -n "$socks_host" ]; then
        export ALL_PROXY="socks5h://${socks_host}:10808"
        export all_proxy="$ALL_PROXY"
    fi

    # Keep intranet and localhost direct.
    export NO_PROXY="${NO_PROXY:-localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16}"
    export no_proxy="${no_proxy:-$NO_PROXY}"
}

# ── Load environment variables from .env ──────────────────────────────────────
if [ -f "$REPO_ROOT/.env" ]; then
    set -a
    source "$REPO_ROOT/.env"
    set +a
fi

# ── Argument parsing ─────────────────────────────────────────────────────────

DEV_MODE=true
for arg in "$@"; do
    case "$arg" in
        --dev)  DEV_MODE=true ;;
        --prod) DEV_MODE=false ;;
        *) echo "Unknown argument: $arg"; echo "Usage: $0 [--dev|--prod]"; exit 1 ;;
    esac
done

if $DEV_MODE; then
    FRONTEND_CMD="pnpm run dev"
else
    FRONTEND_CMD="env BETTER_AUTH_SECRET=$(python3 -c 'import secrets; print(secrets.token_hex(16))') pnpm run preview"
fi

# ── Stop existing services ────────────────────────────────────────────────────

echo "Stopping existing services if any..."
pkill -f "langgraph dev" 2>/dev/null || true
pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -f "next-server" 2>/dev/null || true
nginx -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" -s quit 2>/dev/null || true
sleep 1
pkill -9 nginx 2>/dev/null || true
killall -9 nginx 2>/dev/null || true
./scripts/cleanup-containers.sh deer-flow-sandbox 2>/dev/null || true
sleep 1

# ── Banner ────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "  Starting DeerFlow Development Server"
echo "=========================================="
echo ""
if $DEV_MODE; then
    echo "  Mode: DEV  (hot-reload enabled)"
    echo "  Tip:  run \`make start\` in production mode"
else
    echo "  Mode: PROD (hot-reload disabled)"
    echo "  Tip:  run \`make dev\` to start in development mode"
fi
echo ""
echo "Services starting up..."
echo "  → Backend: LangGraph + Gateway"
echo "  → Frontend: Next.js"
echo "  → Nginx: Reverse Proxy"
echo ""

# ── Config check ─────────────────────────────────────────────────────────────

if ! { \
        [ -n "$DEER_FLOW_CONFIG_PATH" ] && [ -f "$DEER_FLOW_CONFIG_PATH" ] || \
        [ -f backend/config.yaml ] || \
        [ -f config.yaml ]; \
    }; then
    echo "✗ No DeerFlow config file found."
    echo "  Checked these locations:"
    echo "    - $DEER_FLOW_CONFIG_PATH (when DEER_FLOW_CONFIG_PATH is set)"
    echo "    - backend/config.yaml"
    echo "    - ./config.yaml"
    echo ""
    echo "  Run 'make config' from the repo root to generate ./config.yaml, then set required model API keys in .env or your config file."
    exit 1
fi

# ── Auto-upgrade config ──────────────────────────────────────────────────

"$REPO_ROOT/scripts/config-upgrade.sh"

# ── Cleanup trap ─────────────────────────────────────────────────────────────

cleanup() {
    trap - INT TERM
    echo ""
    echo "Shutting down services..."
    pkill -f "langgraph dev" 2>/dev/null || true
    pkill -f "uvicorn app.gateway.app:app" 2>/dev/null || true
    pkill -f "next dev" 2>/dev/null || true
    pkill -f "next start" 2>/dev/null || true
    pkill -f "next-server" 2>/dev/null || true
    # Kill nginx using the captured PID first (most reliable),
    # then fall back to pkill/killall for any stray nginx workers.
    if [ -n "${NGINX_PID:-}" ] && kill -0 "$NGINX_PID" 2>/dev/null; then
        kill -TERM "$NGINX_PID" 2>/dev/null || true
        sleep 1
        kill -9 "$NGINX_PID" 2>/dev/null || true
    fi
    pkill -9 nginx 2>/dev/null || true
    killall -9 nginx 2>/dev/null || true
    echo "Cleaning up sandbox containers..."
    ./scripts/cleanup-containers.sh deer-flow-sandbox 2>/dev/null || true
    echo "✓ All services stopped"
    exit 0
}
trap cleanup INT TERM

# ── Start services ────────────────────────────────────────────────────────────

mkdir -p logs

maybe_start_windows_forwarder
maybe_set_proxy_env

if $DEV_MODE; then
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS="--reload --reload-include='*.yaml' --reload-include='.env' --reload-exclude='*.pyc' --reload-exclude='__pycache__' --reload-exclude='sandbox/' --reload-exclude='.deer-flow/'"
else
    LANGGRAPH_EXTRA_FLAGS="--no-reload"
    GATEWAY_EXTRA_FLAGS=""
fi

echo "Starting LangGraph server..."
# Read log_level from config.yaml, fallback to env var, then to "info"
CONFIG_LOG_LEVEL=$(grep -m1 '^log_level:' config.yaml 2>/dev/null | awk '{print $2}' | tr -d ' ')
LANGGRAPH_LOG_LEVEL="${LANGGRAPH_LOG_LEVEL:-${CONFIG_LOG_LEVEL:-info}}"
(cd backend && NO_COLOR=1 uv run langgraph dev --no-browser --allow-blocking --server-log-level $LANGGRAPH_LOG_LEVEL $LANGGRAPH_EXTRA_FLAGS > ../logs/langgraph.log 2>&1) &
./scripts/wait-for-port.sh 2024 60 "LangGraph" || {
    echo "  See logs/langgraph.log for details"
    tail -20 logs/langgraph.log
    if grep -qE "config_version|outdated|Environment variable .* not found|KeyError|ValidationError|config\.yaml" logs/langgraph.log 2>/dev/null; then
        echo ""
        echo "  Hint: This may be a configuration issue. Try running 'make config-upgrade' to update your config.yaml."
    fi
    cleanup
}
echo "✓ LangGraph server started on localhost:2024"

echo "Starting Gateway API..."
(cd backend && PYTHONUNBUFFERED=1 PYTHONPATH=. uv run uvicorn app.gateway.app:app --host 0.0.0.0 --port 8001 $GATEWAY_EXTRA_FLAGS > ../logs/gateway.log 2>&1) &
./scripts/wait-for-port.sh 8001 90 "Gateway API" || {
    echo "✗ Gateway API failed to start. Last log output:"
    tail -60 logs/gateway.log
    echo ""
    echo "Likely configuration errors:"
    grep -E "Failed to load configuration|Environment variable .* not found|config\.yaml.*not found" logs/gateway.log | tail -5 || true
    echo ""
    echo "  Hint: Try running 'make config-upgrade' to update your config.yaml with the latest fields."
    cleanup
}
echo "✓ Gateway API started on localhost:8001"

echo "Starting Frontend..."
(cd frontend && $FRONTEND_CMD > ../logs/frontend.log 2>&1) &
./scripts/wait-for-port.sh 3000 120 "Frontend" || {
    echo "  See logs/frontend.log for details"
    tail -20 logs/frontend.log
    cleanup
}
echo "✓ Frontend started on localhost:3000"

echo "Starting Nginx reverse proxy..."
nginx -g 'daemon off;' -c "$REPO_ROOT/docker/nginx/nginx.local.conf" -p "$REPO_ROOT" > logs/nginx.log 2>&1 &
NGINX_PID=$!
./scripts/wait-for-port.sh 2026 10 "Nginx" || {
    echo "  See logs/nginx.log for details"
    tail -10 logs/nginx.log
    cleanup
}
echo "✓ Nginx started on localhost:2026"

# ── Ready ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
if $DEV_MODE; then
    echo "  ✓ DeerFlow development server is running!"
else
    echo "  ✓ DeerFlow production server is running!"
fi
echo "=========================================="
echo ""
echo "  🌐 Application: http://localhost:2026"
echo "  📡 API Gateway: http://localhost:2026/api/*"
echo "  🤖 LangGraph:   http://localhost:2026/api/langgraph/*"
echo ""
echo "  📋 Logs:"
echo "     - LangGraph: logs/langgraph.log"
echo "     - Gateway:   logs/gateway.log"
echo "     - Frontend:  logs/frontend.log"
echo "     - Nginx:     logs/nginx.log"
echo ""
echo "Press Ctrl+C to stop all services"

wait
