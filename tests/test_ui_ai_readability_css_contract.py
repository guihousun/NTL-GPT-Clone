from pathlib import Path


def test_ai_readability_css_tokens_and_scopes_exist():
    text = Path("app_ui.py").read_text(encoding="utf-8")

    required_tokens = [
        "--ntl-ai-bg-1",
        "--ntl-ai-bg-2",
        "--ntl-ai-text",
        "--ntl-ai-muted",
        "--ntl-ai-code-bg",
        "--ntl-ai-code-text",
        "--ntl-ai-table-border",
        "--ntl-ai-table-head-bg",
    ]
    for token in required_tokens:
        assert token in text, f"missing css token: {token}"

    required_selectors = [
        ".chat-message.bot .message",
        ".chat-message.bot .message code",
        ".chat-message.bot .message table",
        '[data-testid="stAppViewContainer"] [data-testid="stCodeBlock"]',
        '[data-testid="stAppViewContainer"] [data-testid="stDataFrame"]',
    ]
    for selector in required_selectors:
        assert selector in text, f"missing css selector: {selector}"
