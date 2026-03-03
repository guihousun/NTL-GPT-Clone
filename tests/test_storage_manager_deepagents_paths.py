import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from storage_manager import StorageManager


def test_deepagents_virtual_path_maps_to_workspace_inputs_outputs_and_memory(tmp_path: Path):
    sm = StorageManager(base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "base_data"))

    in_path = Path(sm.resolve_input_path("/data/raw/a.tif", thread_id="t1"))
    out_path = Path(sm.resolve_output_path("/data/processed/r.csv", thread_id="t1"))
    mem_path = Path(sm.resolve_input_path("/memories/session.json", thread_id="t1"))

    assert in_path == (tmp_path / "user_data" / "t1" / "inputs" / "a.tif").resolve()
    assert out_path == (tmp_path / "user_data" / "t1" / "outputs" / "r.csv").resolve()
    assert mem_path == (tmp_path / "user_data" / "t1" / "memory" / "session.json").resolve()


def test_deepagents_shared_virtual_path_maps_to_base_data(tmp_path: Path):
    sm = StorageManager(base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "base_data"))

    shared_path = Path(sm.resolve_input_path("/shared/global_ref.tif", thread_id="t2"))
    assert shared_path == (tmp_path / "base_data" / "global_ref.tif").resolve()


def test_deepagents_shared_virtual_path_does_not_create_parent_dirs(tmp_path: Path):
    sm = StorageManager(base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "base_data"))

    target = tmp_path / "base_data" / "nested" / "probe.txt"
    assert not target.parent.exists()
    shared_path = Path(sm.resolve_input_path("/shared/nested/probe.txt", thread_id="t2b"))
    assert shared_path == target.resolve()
    assert not target.parent.exists()


def test_deepagents_virtual_path_rejects_traversal(tmp_path: Path):
    sm = StorageManager(base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "base_data"))

    with pytest.raises(ValueError):
        sm.resolve_input_path("/data/raw/../../escape.txt", thread_id="t3")


def test_legacy_filename_resolution_still_works(tmp_path: Path):
    sm = StorageManager(base_dir=str(tmp_path / "user_data"), shared_dir=str(tmp_path / "base_data"))

    p = Path(sm.resolve_input_path("inputs/demo.csv", thread_id="t4"))
    assert p == (tmp_path / "user_data" / "t4" / "inputs" / "demo.csv").resolve()
