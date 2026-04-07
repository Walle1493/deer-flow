from deerflow.agents.middlewares.clarification_middleware import ClarificationMiddleware


def test_clarification_options_string_does_not_split_into_characters() -> None:
    mw = ClarificationMiddleware()
    msg = mw._format_clarification_message(
        {
            "question": "Which one?",
            "clarification_type": "approach_choice",
            "options": '["Option A","Option B"]',
        }
    )
    assert "1. Option A" in msg
    assert "2. Option B" in msg
    # Ensure it didn't enumerate raw JSON characters like '[' or '"'
    assert "1. [" not in msg
    assert '1. "' not in msg


def test_clarification_options_plain_string_becomes_single_option() -> None:
    mw = ClarificationMiddleware()
    msg = mw._format_clarification_message(
        {
            "question": "Please confirm",
            "clarification_type": "risk_confirmation",
            "options": "Proceed (this is a single option string)",
        }
    )
    assert "1. Proceed (this is a single option string)" in msg

