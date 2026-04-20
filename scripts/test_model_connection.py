#!/usr/bin/env python3
"""
Smoke-test the chat model from repo config.yaml (same stack as DeerFlow: PatchedChatOpenAI + base_url).

Usage (from repo root or backend/):
  cd backend && uv run python ../scripts/test_model_connection.py [model_name]

Requires:
  - config.yaml with a valid OpenAI-compatible base_url (WSL + intranet: use Windows forwarder, e.g. http://127.0.0.1:55001/v1)
  - Optional: .env with NO_PROXY for 10.x if HTTP_PROXY is set
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    os.environ.setdefault("DEER_FLOW_CONFIG_PATH", str(repo_root / "config.yaml"))
    os.chdir(repo_root)

    try:
        from dotenv import load_dotenv

        load_dotenv(repo_root / ".env")
    except ImportError:
        pass

    from deerflow.config.app_config import reset_app_config
    from deerflow.models.factory import create_chat_model
    from langchain_core.messages import HumanMessage

    reset_app_config()

    name = sys.argv[1] if len(sys.argv) > 1 else "Qwen3.5-27B"
    print(f"Testing model: {name}", flush=True)
    model = create_chat_model(name)
    msg = HumanMessage(content='Reply with exactly one word: OK')
    resp = model.invoke([msg])
    text = getattr(resp, "content", None) or str(resp)
    print("Response:", (text[:800] + "…") if len(str(text)) > 800 else text, flush=True)
    print("OK", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print("FAILED:", e, file=sys.stderr, flush=True)
        raise SystemExit(1)
