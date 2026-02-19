import json
from pathlib import Path


def test_q20_workflow_contains_vnp46a2_first_night_overpass_rule():
    workflow_path = Path(__file__).resolve().parent.parent / "RAG" / "guidence_json" / "Workflow.json"
    items = json.loads(workflow_path.read_text(encoding="utf-8"))
    q20 = next(item for item in items if item.get("task_id") == "Q20")

    step2 = next(step for step in q20.get("steps", []) if step.get("name") == "geospatial_code_step_2")
    desc = step2.get("description", "")
    assert "first post-event overpass night" in desc
    assert "typical local overpass ~01:30" in desc
    assert "use day D+1 as the first post-event night (not day D)" in desc

