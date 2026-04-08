#!/usr/bin/env python3
"""
Simple HTTP forwarder / reverse proxy (single upstream).

Use case: Windows can reach an intranet endpoint (e.g. 10.x), but WSL cannot.
Run this on Windows, then point WSL/DeerFlow to the forwarder's URL (usually http://127.0.0.1:<port>).
"""

from __future__ import annotations

import argparse
import http.client
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


class ForwardHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:  # noqa: N802
        self._forward()

    def do_POST(self) -> None:  # noqa: N802
        self._forward()

    def do_PUT(self) -> None:  # noqa: N802
        self._forward()

    def do_PATCH(self) -> None:  # noqa: N802
        self._forward()

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward()

    def do_HEAD(self) -> None:  # noqa: N802
        self._forward()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._forward()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _forward(self) -> None:
        target_base = self.server.target_base  # type: ignore[attr-defined]
        upstream = urlsplit(target_base)
        if upstream.scheme not in ("http", "https"):
            self.send_error(500, "Invalid upstream scheme")
            return

        upstream_path = upstream.path.rstrip("/")
        req_path = self.path
        if req_path.startswith("/"):
            full_path = upstream_path + req_path
        else:
            full_path = upstream_path + "/" + req_path

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else None

        out_headers: dict[str, str] = {}
        for k, v in self.headers.items():
            lk = k.lower()
            if lk in HOP_BY_HOP_HEADERS or lk == "host":
                continue
            out_headers[k] = v
        out_headers["Host"] = upstream.netloc

        conn_cls = (
            http.client.HTTPSConnection if upstream.scheme == "https" else http.client.HTTPConnection
        )
        conn = conn_cls(upstream.hostname, upstream.port, timeout=300)
        try:
            conn.request(self.command, full_path, body=body, headers=out_headers)
            resp = conn.getresponse()

            self.send_response(resp.status, resp.reason)
            for k, v in resp.getheaders():
                if k.lower() in HOP_BY_HOP_HEADERS:
                    continue
                self.send_header(k, v)
            self.end_headers()

            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except Exception as e:
            self.send_error(502, f"Upstream error: {e}")
        finally:
            try:
                conn.close()
            except Exception:
                pass


class _ForwardServer(ThreadingHTTPServer):
    def __init__(self, server_address, RequestHandlerClass, target_base: str):
        super().__init__(server_address, RequestHandlerClass)
        self.target_base = target_base


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen-host", default="127.0.0.1")
    ap.add_argument("--listen-port", type=int, default=55145)
    ap.add_argument(
        "--target-base",
        required=True,
        help="Upstream base URL, e.g. http://10.131.12.157:10145",
    )
    args = ap.parse_args()

    with _ForwardServer((args.listen_host, args.listen_port), ForwardHandler, target_base=args.target_base) as httpd:
        sa = httpd.socket.getsockname()
        print(f"Forwarding on http://{sa[0]}:{sa[1]} -> {args.target_base}", flush=True)
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

