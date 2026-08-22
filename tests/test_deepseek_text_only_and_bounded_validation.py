from __future__ import annotations

import json

from langchain_core.messages import HumanMessage, ToolMessage

from agents.NTL_Analyst import system_prompt_analyst
from graph_factory import (
    ChatOpenAI,
    _full_system_prompt,
    _single_agent_prompt,
    _text_only_message,
)


def test_deepseek_payload_replaces_image_blocks_with_text() -> None:
    tool_message = ToolMessage(
        content=[
            {"type": "text", "text": "The artifact was saved."},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64,SECRET_IMAGE_BYTES"},
            },
        ],
        tool_call_id="tool-call-1",
        name="read_file",
    )

    sanitized = _text_only_message(tool_message)
    assert isinstance(sanitized.content, str)
    assert "The artifact was saved." in sanitized.content
    assert "Image content omitted" in sanitized.content
    assert "SECRET_IMAGE_BYTES" not in sanitized.content
    assert sanitized.tool_call_id == "tool-call-1"
    assert sanitized.name == "read_file"

    model = ChatOpenAI(
        api_key="test-key",
        base_url="https://example.invalid/v1",
        model="deepseek-v4-flash",
        temperature=0,
    )
    payload = model._get_request_payload(
        [HumanMessage(content="Continue."), tool_message]
    )
    encoded = json.dumps(payload, ensure_ascii=False)
    assert "image_url" not in encoded
    assert "SECRET_IMAGE_BYTES" not in encoded
    assert "Image content omitted" in encoded


def test_active_prompts_define_minimum_sufficient_stop_policy() -> None:
    full = _full_system_prompt().lower()
    single = _single_agent_prompt().lower()
    analyst = str(system_prompt_analyst.content).lower()

    assert "minimum-sufficient validation" in full
    assert "validate only the exact package handle" in full
    assert "successful route transition must not be repeated" in full
    assert "one batched final validation pass" in single
    assert "do not re-read or re-inspect an unchanged artifact" in single
    assert "one primary execution" in analyst
    assert "never create or execute a third implementation" in analyst
    assert "stop immediately" in analyst
    assert "method fidelity takes precedence" in full
    assert "method fidelity takes precedence" in single
    assert "do not call supplemental knowledge retrieval" in full
    assert "do not call supplemental knowledge retrieval" in single
    assert "exact registered-method dispatch" in full
    assert "exact registered-method dispatch" in single
    assert "dedicated method tool" in analyst
    assert "treat that output as canonical" in analyst
    assert "generic code must not recompute the ratios" in analyst
