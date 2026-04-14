"""Regression: extract outputs paths from tool output when present_files missing."""

from app.channels.manager import _extract_artifacts


def test_extracts_outputs_path_from_tool_message_content() -> None:
    result = {
        "messages": [
            {"type": "human", "content": "make image"},
            {"type": "ai", "content": "Generating..."},
            {"type": "tool", "name": "bash", "content": "saved /mnt/user-data/outputs/zimage-out.png"},
            {"type": "ai", "content": "Done."},
        ]
    }
    assert _extract_artifacts(result) == ["/mnt/user-data/outputs/zimage-out.png"]

