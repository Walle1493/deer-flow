#!/usr/bin/env python3
"""Replace WSL_V2RAYN_PROXY block in ~/.bashrc: RFC1918 NO_PROXY + smart proxy host."""
from pathlib import Path

START = "# >>> WSL_V2RAYN_PROXY"
END = "# <<< WSL_V2RAYN_PROXY"

NEW_BLOCK = r"""# >>> WSL_V2RAYN_PROXY
# v2rayN: HTTP 10809 / SOCKS 10808. Intranet (10/172.16/192.168) must bypass proxy (NO_PROXY).
# Proxy host: try 127.0.0.1 first (WSL mirrored networking); else default gateway (v2ray "allow LAN").
_whost=""
if (exec 3<>/dev/tcp/127.0.0.1/10809) 2>/dev/null; then
  _whost="127.0.0.1"
elif command -v ip >/dev/null 2>&1; then
  _gw="$(ip route show default 2>/dev/null | awk '{print $3}')"
  if [ -n "$_gw" ] && (exec 3<>/dev/tcp/"$_gw"/10809) 2>/dev/null; then
    _whost="$_gw"
  fi
  unset _gw
fi
if [ -n "$_whost" ]; then
  export HTTP_PROXY="http://${_whost}:10809"
  export HTTPS_PROXY="http://${_whost}:10809"
  export http_proxy="$HTTP_PROXY"
  export https_proxy="$HTTPS_PROXY"
  if (exec 3<>/dev/tcp/"$_whost"/10808) 2>/dev/null; then
    export ALL_PROXY="socks5h://${_whost}:10808"
    export all_proxy="$ALL_PROXY"
  fi
  export NO_PROXY="localhost,127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
  export no_proxy="$NO_PROXY"
fi
unset _whost
# <<< WSL_V2RAYN_PROXY"""


def main() -> None:
    p = Path.home() / ".bashrc"
    t = p.read_text(encoding="utf-8", errors="replace")
    i = t.find(START)
    j = t.find(END)
    if i == -1 or j == -1 or j < i:
        raise SystemExit("WSL_V2RAYN_PROXY markers not found in ~/.bashrc")
    j2 = j + len(END)
    # include trailing newline after END if single \n
    if t[j2 : j2 + 1] == "\n":
        j2 += 1
    out = t[:i] + NEW_BLOCK + "\n" + t[j2:]
    p.write_text(out, encoding="utf-8")
    print("patch-wsl-bashrc-v2ray-block: replaced block in", p)


if __name__ == "__main__":
    main()
