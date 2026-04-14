"""Guardrails: lead agent system prompt must steer text-to-image to z-image, not image_search-only."""

from deerflow.agents.lead_agent.prompt import apply_prompt_template


def test_system_prompt_includes_text_to_image_z_image_guidance() -> None:
    text = apply_prompt_template(subagent_enabled=False)
    assert "Text-to-image" in text
    assert "z-image" in text
    assert "image_search" in text
    assert "present_files" in text
