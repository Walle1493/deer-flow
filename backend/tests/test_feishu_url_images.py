"""Tests for Feishu auto-fetch of image URLs from agent text."""

from __future__ import annotations

import asyncio

from app.channels.feishu_url_images import (
    append_feishu_image_attachments_from_text,
    extract_image_candidate_urls,
    rewrite_loopback_service_url,
)


def test_extract_z_image_urls():
    text = 'done {"image_url":"http://127.0.0.1:10146/api/v1/image/AbCdEf"}'
    urls = extract_image_candidate_urls(text)
    assert urls == ["http://127.0.0.1:10146/api/v1/image/AbCdEf"]


def test_extract_dedupes():
    text = "see http://10.0.0.1:9/api/v1/image/x and http://10.0.0.1:9/api/v1/image/x"
    urls = extract_image_candidate_urls(text)
    assert urls == ["http://10.0.0.1:9/api/v1/image/x"]


def test_extract_skips_non_image_urls():
    text = "read https://example.com/doc.html and https://x.com/y"
    assert extract_image_candidate_urls(text) == []


def test_collect_text_includes_tool_output_with_image_url():
    from app.channels.manager import _feishu_url_scan_text

    result = {
        "messages": [
            {"type": "human", "content": "画一张图"},
            {"type": "ai", "content": "好的，我来生成。"},
            {
                "type": "tool",
                "name": "bash",
                "content": '{"success":true,"image_url":"http://10.0.0.1:9/api/v1/image/abc123"}',
            },
            {"type": "ai", "content": "已完成。"},
        ]
    }
    scan = _feishu_url_scan_text(result, _extract_rt(result))
    assert "/api/v1/image/abc123" in scan


def _extract_rt(result):
    from app.channels.manager import _extract_response_text

    return _extract_response_text(result)


def test_rewrite_loopback(monkeypatch):
    monkeypatch.setenv("Z_IMAGE_BASE_URL", "http://10.131.12.157:10146")
    assert (
        rewrite_loopback_service_url("http://127.0.0.1:10146/api/v1/image/abc")
        == "http://10.131.12.157:10146/api/v1/image/abc"
    )
    assert rewrite_loopback_service_url("http://10.131.12.157:10146/api/v1/image/abc") == (
        "http://10.131.12.157:10146/api/v1/image/abc"
    )


def test_append_skips_when_not_feishu():
    from pathlib import Path

    from app.channels.message_bus import ResolvedAttachment

    att = ResolvedAttachment(
        virtual_path="/x",
        actual_path=Path("/tmp"),
        filename="x",
        mime_type="text/plain",
        size=1,
        is_image=False,
    )
    text = "http://127.0.0.1:10146/api/v1/image/abc"
    out = asyncio.run(append_feishu_image_attachments_from_text("slack", text, [att], enabled=True))
    assert len(out) == 1


def test_append_skips_when_already_has_image():
    from pathlib import Path

    from app.channels.message_bus import ResolvedAttachment

    att = ResolvedAttachment(
        virtual_path="/mnt/user-data/outputs/a.png",
        actual_path=Path("/tmp/a.png"),
        filename="a.png",
        mime_type="image/png",
        size=10,
        is_image=True,
    )
    text = "http://127.0.0.1:10146/api/v1/image/abc"
    out = asyncio.run(append_feishu_image_attachments_from_text("feishu", text, [att], enabled=True))
    assert out == [att]
