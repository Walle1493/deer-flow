"""Download image URLs from agent text for Feishu inline image delivery.

Feishu cannot load arbitrary intranet URLs inside a card. When the model pastes an
``image_url`` (e.g. z-image ``/api/v1/image/...``) but does not call ``present_files``,
we fetch bytes on the gateway host, then reuse the existing ``send_file`` → upload image
path (same as workspace outputs).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import httpx

from app.channels.message_bus import ResolvedAttachment

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r"https?://[^\s\)\]<>\"']+", re.IGNORECASE)
_MAX_BYTES = 10 * 1024 * 1024
_TIMEOUT = httpx.Timeout(120.0, connect=30.0)


def rewrite_loopback_service_url(url: str) -> str:
    """If the API returned 127.0.0.1/localhost, rewrite origin from Z_IMAGE_BASE_URL."""
    base = (os.environ.get("Z_IMAGE_BASE_URL") or "").strip().rstrip("/")
    if not base:
        return url
    try:
        raw_u = urlparse(url)
        if raw_u.hostname not in ("127.0.0.1", "localhost", "::1"):
            return url
        bu = urlparse(base)
        new = raw_u._replace(scheme=bu.scheme or raw_u.scheme, netloc=bu.netloc)
        return urlunparse(new)
    except Exception:
        return url


def _should_try_fetch(url: str) -> bool:
    try:
        p = urlparse(url)
        path = (p.path or "").lower()
    except Exception:
        return False
    if "/api/v1/image/" in path:
        return True
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.endswith(ext):
            return True
    return False


def extract_image_candidate_urls(text: str) -> list[str]:
    """Deduplicated URLs from *text* that look like direct image resources."""
    if not (text or "").strip():
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in _URL_RE.findall(text):
        u = raw.rstrip(").,;\"'")
        if u in seen or not _should_try_fetch(u):
            continue
        seen.add(u)
        out.append(u)
    return out


def _sniff_image_mime(data: bytes) -> str | None:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _extension_for_mime(mime: str) -> str:
    ext = mimetypes.guess_extension(mime.split(";")[0].strip(), strict=False)
    if ext in (".jpe", ".jpeg"):
        return ".jpg"
    return ext or ".png"


async def _download_one(client: httpx.AsyncClient, url: str, index: int) -> ResolvedAttachment | None:
    fetch_url = rewrite_loopback_service_url(url)
    try:
        response = await client.get(fetch_url, follow_redirects=True)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("[Feishu] failed to GET image URL %s: %s", fetch_url, exc)
        return None

    data = response.content
    if len(data) == 0:
        logger.warning("[Feishu] empty response for image URL %s", fetch_url)
        return None
    if len(data) > _MAX_BYTES:
        logger.warning("[Feishu] image too large (%d bytes), skip %s", len(data), fetch_url)
        return None

    ct = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if ct and not ct.startswith("image/") and ct != "application/octet-stream":
        logger.info("[Feishu] skip URL with non-image Content-Type %s: %s", ct, fetch_url)
        return None

    mime = ct if ct.startswith("image/") else _sniff_image_mime(data)
    if not mime:
        logger.info("[Feishu] could not infer image type, skip %s", fetch_url)
        return None

    ext = _extension_for_mime(mime)
    fd, path_str = tempfile.mkstemp(suffix=ext, prefix="feishu-url-img-")
    os.close(fd)
    path = Path(path_str)
    path.write_bytes(data)

    virtual = f"__feishu_url_image__/{index}{ext}"
    try:
        return ResolvedAttachment(
            virtual_path=virtual,
            actual_path=path.resolve(),
            filename=path.name,
            mime_type=mime,
            size=path.stat().st_size,
            is_image=True,
        )
    except Exception:
        logger.exception("[Feishu] failed to build attachment for %s", fetch_url)
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None


async def append_feishu_image_attachments_from_text(
    channel_name: str,
    text: str,
    existing: list[ResolvedAttachment],
    *,
    enabled: bool = True,
    max_images: int = 3,
) -> list[ResolvedAttachment]:
    """If Feishu and no image attachment yet, download image-like URLs from *text*."""
    if channel_name != "feishu" or not enabled:
        return existing
    if any(a.is_image for a in existing):
        return existing

    urls = extract_image_candidate_urls(text)[:max_images]
    if not urls:
        return existing

    merged = list(existing)
    async with httpx.AsyncClient(trust_env=True, timeout=_TIMEOUT) as client:
        for i, url in enumerate(urls):
            att = await _download_one(client, url, i)
            if att is not None:
                merged.append(att)
                logger.info("[Feishu] fetched image from URL for upload: %s -> %s", url, att.filename)

    return merged
