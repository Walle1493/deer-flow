"""Contract test: z-image skill must hard-require present_files delivery."""

from __future__ import annotations

from pathlib import Path


def test_z_image_skill_mentions_present_files_and_immediate_delivery() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skill = repo_root / "skills" / "custom" / "z-image" / "SKILL.md"
    text = skill.read_text("utf-8", errors="ignore")
    assert "present_files" in text
    assert "Immediately after download" in text

