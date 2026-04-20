#!/usr/bin/env bash
# WSL2 + v2rayN on Windows: export HTTP(S)_PROXY when local HTTP port 10809 is open,
# and set NO_PROXY so RFC1918 (e.g. 10.131.12.x) stays direct. GitHub is slow without
# a proxy from WSL because WSL does not use Windows "system proxy" by default.
#
# Permanent use (pick one path to this repo):
#   echo '. "/mnt/d/yuantong/code/deer-flow/scripts/wsl-v2ray-env.sh"' >> ~/.bashrc
#   echo '. "/mnt/d/yuantong/code/deer-flow/scripts/wsl-v2ray-env.sh"' >> ~/.profile
#
# One-time: register Git to use v2ray HTTP proxy only for GitHub (recommended vs global http.proxy):
#   bash /path/to/wsl-v2ray-env.sh --install-git-proxy
#
# Remove GitHub-only proxy entries:
#   bash /path/to/wsl-v2ray-env.sh --uninstall-git-proxy

_wsl_v2ray_is_sourced() {
    [ -n "${BASH_VERSION:-}" ] && [ "${BASH_SOURCE[0]}" != "${0}" ]
}
if ! _wsl_v2ray_is_sourced; then
    set -euo pipefail
fi

_wsl_v2ray_detect_hosts() {
    local http_host="" socks_host=""
    if (exec 3<>/dev/tcp/127.0.0.1/10809) 2>/dev/null; then
        http_host="127.0.0.1"
    fi
    if (exec 3<>/dev/tcp/127.0.0.1/10808) 2>/dev/null; then
        socks_host="127.0.0.1"
    fi
    if { [ -z "$http_host" ] || [ -z "$socks_host" ]; } && command -v ip >/dev/null 2>&1; then
        local gw
        gw="$(ip route show default 2>/dev/null | awk '{print $3}')"
        if [ -n "$gw" ]; then
            if [ -z "$http_host" ] && (exec 3<>/dev/tcp/"$gw"/10809) 2>/dev/null; then
                http_host="$gw"
            fi
            if [ -z "$socks_host" ] && (exec 3<>/dev/tcp/"$gw"/10808) 2>/dev/null; then
                socks_host="$gw"
            fi
        fi
    fi
    printf '%s %s\n' "$http_host" "$socks_host"
}

_wsl_v2ray_export_env() {
    local bypass="localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,10.131.12.157"
    export NO_PROXY="${NO_PROXY:-$bypass}"
    export no_proxy="${no_proxy:-$NO_PROXY}"

    # Do not override explicit user settings unless unreachable (same idea as serve.sh).
    if [ -n "${HTTP_PROXY:-}" ]; then
        local hp="${HTTP_PROXY#http://}"
        hp="${hp#https://}"
        local host="${hp%%:*}"
        local port="${hp##*:}"
        if [ -n "$host" ] && [ -n "$port" ] && (exec 3<>/dev/tcp/"$host"/"$port") 2>/dev/null; then
            return 0
        fi
    fi

    read -r http_host socks_host < <(_wsl_v2ray_detect_hosts)

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
}

_wsl_v2ray_install_git_proxy() {
    read -r http_host _ < <(_wsl_v2ray_detect_hosts)
    if [ -z "$http_host" ]; then
        echo "wsl-v2ray-env: cannot reach 10809 on 127.0.0.1 or default gateway — start v2rayN HTTP proxy first." >&2
        return 1
    fi
    local url="http://${http_host}:10809"
    # Match both spellings; an empty [http "https://github.com/"] proxy = breaks push in WSL.
    git config --global http.https://github.com.proxy "$url"
    git config --global http.https://github.com/.proxy "$url"
    git config --global http.https://gist.github.com.proxy "$url"
    git config --global http.https://api.github.com.proxy "$url"
    echo "wsl-v2ray-env: git proxy for GitHub set to $url"
}

_wsl_v2ray_uninstall_git_proxy() {
    git config --global --unset http.https://github.com.proxy 2>/dev/null || true
    git config --global --unset http.https://github.com/.proxy 2>/dev/null || true
    git config --global --unset http.https://gist.github.com.proxy 2>/dev/null || true
    git config --global --unset http.https://api.github.com.proxy 2>/dev/null || true
    echo "wsl-v2ray-env: removed GitHub-specific git proxy entries."
}

case "${1:-}" in
    --install-git-proxy)
        _wsl_v2ray_install_git_proxy
        ;;
    --uninstall-git-proxy)
        _wsl_v2ray_uninstall_git_proxy
        ;;
    "")
        if _wsl_v2ray_is_sourced; then
            _wsl_v2ray_export_env
        else
            echo "Usage: source this file from ~/.bashrc, or:" >&2
            echo "  $0 --install-git-proxy" >&2
            echo "  $0 --uninstall-git-proxy" >&2
            exit 1
        fi
        ;;
    *)
        echo "Unknown option: $1" >&2
        exit 1
        ;;
esac
