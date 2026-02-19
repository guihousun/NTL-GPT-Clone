import json
from pathlib import Path

from utils.ntl_kb_aliases import TOOL_ALIAS_MAP


ROOT = Path(__file__).resolve().parent.parent
GUIDANCE_DIR = ROOT / "RAG" / "guidence_json"


def test_workflow_is_flat_and_schema_complete():
    workflow = json.loads((GUIDANCE_DIR / "Workflow.json").read_text(encoding="utf-8"))
    assert isinstance(workflow, list)
    assert all(isinstance(item, dict) for item in workflow)
    assert all(not isinstance(item, list) for item in workflow)

    tool_specs = json.loads((GUIDANCE_DIR / "tools.json").read_text(encoding="utf-8"))
    tool_names = {item["tool_name"] for item in tool_specs if isinstance(item, dict)}

    for task in workflow:
        for key in ("task_id", "task_name", "category", "description", "steps", "output"):
            assert key in task
        assert isinstance(task["steps"], list)

        for step in task["steps"]:
            assert isinstance(step, dict)
            assert "type" in step
            assert "name" in step
            assert step["name"]
            assert step["name"] not in TOOL_ALIAS_MAP  # legacy names must be normalized

            if step["type"] == "builtin_tool":
                assert isinstance(step.get("input"), dict)
                assert step["name"] in tool_names

