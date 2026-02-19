import json
from pathlib import Path


WORKFLOW_PATH = Path('RAG/guidence_json/Workflow.json')
TOOLS_PATH = Path('RAG/guidence_json/tools.json')


def _load_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def _task_by_id(task_id: str) -> dict:
    tasks = _load_json(WORKFLOW_PATH)
    for task in tasks:
        if task.get('task_id') == task_id:
            return task
    raise AssertionError(f'task not found: {task_id}')


def _tool_by_name(tool_name: str) -> dict:
    tools = _load_json(TOOLS_PATH)
    for tool in tools:
        if tool.get('tool_name') == tool_name:
            return tool
    raise AssertionError(f'tool not found: {tool_name}')


def test_q19_q20_workflow_text_avoids_hardcoded_expected_outcomes():
    q19_desc = _task_by_id('Q19')['steps'][3]['description']
    q20_step2_desc = _task_by_id('Q20')['steps'][1]['description']
    q20_step3_desc = _task_by_id('Q20')['steps'][2]['description']

    banned_q19 = [
        'ground-truth data from the image',
        'expected best',
    ]
    banned_q20 = [
        'Baseline: 2.01',
        'Event Night: 0.89',
        'Recovery: 1.31',
        '(-55.7%)',
        "as shown in the NTL Engineer's final analysis",
    ]

    q19_lower = q19_desc.lower()
    for token in banned_q19:
        assert token.lower() not in q19_lower

    q20_lower = (q20_step2_desc + '\n' + q20_step3_desc).lower()
    for token in banned_q20:
        assert token.lower() not in q20_lower


def test_landscan_out_name_is_directory_style_in_workflows():
    q2_out_name = _task_by_id('Q2')['steps'][0]['input']['out_name']
    q25_out_name = _task_by_id('Q25')['steps'][1]['input']['out_name']

    assert not q2_out_name.lower().endswith('.tif')
    assert not q25_out_name.lower().endswith('.tif')


def test_landscan_tool_doc_matches_directory_contract():
    tool = _tool_by_name('LandScan_download_tool')
    out_name_desc = tool['parameters']['out_name'].lower()
    output_desc = tool['output']

    assert 'directory' in out_name_desc
    assert '.tif filename' in out_name_desc
    assert 'LandScan_<study_area>_<year>.tif' in output_desc
