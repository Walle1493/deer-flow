import argparse
import json
import os
import sys
from typing import Any
from urllib.parse import urlparse

try:
    import requests
except ImportError:  # pragma: no cover
    import subprocess

    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"], check=True)
    import requests


def _session() -> "requests.Session":
    """
    Use a dedicated Session and ignore *_PROXY env vars by default.

    In many WSL setups, http_proxy/https_proxy is configured for browsing,
    but intranet endpoints (10.x) or Windows-forwarded localhost endpoints
    should not go through that proxy.
    """
    s = requests.Session()
    s.trust_env = False
    return s


def _get_base_url(cli_base_url: str | None) -> str:
    base = (cli_base_url or os.getenv("QWEN3_TTS_BASE_URL") or "").strip()
    if not base:
        raise ValueError(
            "Missing TTS base url. Set QWEN3_TTS_BASE_URL (e.g. http://<host>:10145) "
            "or pass --base-url."
        )
    return base.rstrip("/")


def _post_tts(base_url: str, text: str, timeout_sec: int) -> dict[str, Any]:
    url = f"{base_url}/api/v1/tts"
    resp = _session().post(
        url,
        headers={"Content-Type": "application/json"},
        json={"text": text},
        timeout=timeout_sec,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"TTS HTTP {resp.status_code}: {resp.text}")
    try:
        data = resp.json()
    except Exception as e:
        raise RuntimeError(f"Invalid JSON response: {e}. Raw: {resp.text[:5000]}") from e
    return data


def _rewrite_audio_url_if_needed(audio_url: str, base_url: str) -> str:
    """
    If base_url points to a local Windows forwarder (127.0.0.1/localhost),
    rewrite audio_url to be fetched via the forwarder too.

    This is required when WSL cannot route to the upstream intranet IP (10.x),
    but can reach the Windows localhost forwarder.
    """
    a = urlparse(audio_url)
    b = urlparse(base_url)
    if a.scheme not in ("http", "https") or not a.netloc:
        raise ValueError(f"Invalid audio_url: {audio_url}")
    if b.scheme not in ("http", "https") or not b.netloc:
        return audio_url

    if b.hostname in ("127.0.0.1", "localhost"):
        if a.hostname and a.hostname != b.hostname:
            return f"{b.scheme}://{b.netloc}{a.path}" + (f"?{a.query}" if a.query else "")
    return audio_url


def _download_audio(audio_url: str, base_url: str, timeout_sec: int) -> bytes:
    audio_url = _rewrite_audio_url_if_needed(audio_url, base_url)
    parsed = urlparse(audio_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(f"Invalid audio_url: {audio_url}")

    resp = _session().get(audio_url, timeout=timeout_sec, stream=True)
    if resp.status_code != 200:
        raise RuntimeError(f"Audio download HTTP {resp.status_code}: {resp.text}")
    return resp.content


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate TTS audio via self-hosted service")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--output-file", required=True, help="Output WAV file path")
    parser.add_argument(
        "--base-url",
        required=False,
        default=None,
        help="Override QWEN3_TTS_BASE_URL, e.g. http://<host>:10145",
    )
    parser.add_argument(
        "--timeout-sec",
        required=False,
        type=int,
        default=120,
        help="HTTP timeout in seconds (default: 120)",
    )
    parser.add_argument(
        "--meta-json",
        required=False,
        default=None,
        help="Optional path to write response metadata JSON",
    )
    args = parser.parse_args()

    base_url = _get_base_url(args.base_url)
    result = _post_tts(base_url, args.text, args.timeout_sec)

    # Expected example:
    # {
    #   "success": true,
    #   "sample_rate": 24000,
    #   "audio_url": "http://.../api/v1/audio/<token>",
    #   "expires_in": 3600
    # }
    if not result.get("success", False):
        raise RuntimeError(f"TTS returned success=false: {json.dumps(result, ensure_ascii=False)}")

    audio_url = result.get("audio_url")
    audio_b64 = result.get("audio_base64")
    audio_bytes: bytes

    if audio_url:
        audio_bytes = _download_audio(str(audio_url), base_url, args.timeout_sec)
    elif audio_b64:
        import base64

        audio_bytes = base64.b64decode(str(audio_b64))
    else:
        raise RuntimeError(
            f"Missing audio_url/audio_base64 in response: {json.dumps(result, ensure_ascii=False)}"
        )

    out_dir = os.path.dirname(args.output_file)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output_file, "wb") as f:
        f.write(audio_bytes)

    if args.meta_json:
        meta_dir = os.path.dirname(args.meta_json)
        if meta_dir:
            os.makedirs(meta_dir, exist_ok=True)
        with open(args.meta_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"Saved audio to {args.output_file}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

