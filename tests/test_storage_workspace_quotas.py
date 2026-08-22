from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


class StorageWorkspaceQuotaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self._old_env = {
            name: os.environ.get(name)
            for name in (
                "NTL_USER_DATA_DIR",
                "NTL_SHARED_DATA_DIR",
                "NTL_THREAD_WORKSPACE_QUOTA_MB",
                "NTL_USER_WORKSPACE_QUOTA_MB",
                "NTL_HISTORY_DB_URL",
            )
        }
        os.environ["NTL_USER_DATA_DIR"] = str(Path(self.tempdir.name) / "user_data")
        os.environ["NTL_SHARED_DATA_DIR"] = str(Path(self.tempdir.name) / "base_data")
        os.environ["NTL_THREAD_WORKSPACE_QUOTA_MB"] = "1"
        os.environ["NTL_USER_WORKSPACE_QUOTA_MB"] = "2"
        history_db = (Path(self.tempdir.name) / "history.sqlite3").as_posix()
        os.environ["NTL_HISTORY_DB_URL"] = f"sqlite:///{history_db}"
        self.addCleanup(self._restore_env)

        import runtime_governance
        import storage_manager
        import history_store

        self.runtime_governance = importlib.reload(runtime_governance)
        self.storage_manager_module = importlib.reload(storage_manager)
        self.history_store = importlib.reload(history_store)
        self.storage_manager = self.storage_manager_module.storage_manager

    def _restore_env(self) -> None:
        for name, value in self._old_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def _write_bytes(self, path: Path, size_bytes: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"a" * size_bytes)

    def test_thread_quota_snapshot_rejects_projected_write(self) -> None:
        thread_id = "alice-a1"
        workspace = self.storage_manager.get_workspace(thread_id)
        self._write_bytes(workspace / "inputs" / "sample.bin", 800 * 1024)

        snapshot = self.storage_manager.thread_quota_snapshot(thread_id, additional_bytes=300 * 1024)

        self.assertEqual(snapshot["limit_bytes"], 1 * 1024 * 1024)
        self.assertFalse(snapshot["allowed"])
        self.assertGreater(snapshot["projected_bytes"], snapshot["limit_bytes"])

    def test_user_quota_snapshot_counts_multiple_threads(self) -> None:
        user_id = "alice"
        thread_ids = ["alice-a1", "alice-b2"]
        self.history_store.bind_thread_to_user(user_id, thread_ids[0])
        self.history_store.bind_thread_to_user(user_id, thread_ids[1])

        workspace_a = self.storage_manager.get_workspace(thread_ids[0])
        workspace_b = self.storage_manager.get_workspace(thread_ids[1])
        self._write_bytes(workspace_a / "outputs" / "a.bin", 700 * 1024)
        self._write_bytes(workspace_b / "outputs" / "b.bin", 900 * 1024)

        resolved_thread_ids = [row["thread_id"] for row in self.history_store.list_user_threads(user_id, limit=0)]
        snapshot = self.storage_manager.user_quota_snapshot(resolved_thread_ids, additional_bytes=500 * 1024)

        self.assertEqual(snapshot["limit_bytes"], 2 * 1024 * 1024)
        self.assertFalse(snapshot["allowed"])
        self.assertGreater(snapshot["usage_bytes"], 1_500 * 1024)
        self.assertGreater(snapshot["projected_bytes"], snapshot["limit_bytes"])

    def test_nested_paths_are_preserved_and_output_roots_are_enforced(self) -> None:
        thread_id = "alice-nested"
        workspace = self.storage_manager.get_workspace(thread_id)
        nested_input = workspace / "inputs" / "boundaries" / "districts.shp"
        nested_input.parent.mkdir(parents=True, exist_ok=True)
        nested_input.write_bytes(b"shape")

        self.assertEqual(
            Path(self.storage_manager.resolve_input_path("boundaries/districts.shp", thread_id)),
            nested_input.resolve(),
        )
        self.assertEqual(
            Path(self.storage_manager.resolve_output_path("tables/result.csv", thread_id)),
            (workspace / "outputs" / "tables" / "result.csv").resolve(),
        )
        self.assertEqual(
            Path(self.storage_manager.resolve_input_path("", thread_id)),
            (workspace / "inputs").resolve(),
        )
        with self.assertRaises(PermissionError):
            self.storage_manager.resolve_output_path("inputs/not-an-output.txt", thread_id)
        with self.assertRaises(PermissionError):
            self.storage_manager.resolve_output_path("/data/raw/not-an-output.txt", thread_id)

    def test_deepagents_inputs_outputs_aliases_resolve_with_their_workspace_roots(self) -> None:
        thread_id = "alice-aliases"
        workspace = self.storage_manager.get_workspace(thread_id)

        self.assertEqual(
            self.storage_manager.resolve_workspace_relative_path(
                "/inputs/source.json",
                thread_id,
                default_root="outputs",
                allowed_roots=("inputs",),
            ),
            (workspace / "inputs" / "source.json").resolve(),
        )
        self.assertEqual(
            self.storage_manager.resolve_workspace_relative_path(
                "/outputs/results/table.csv",
                thread_id,
                default_root="inputs",
                allowed_roots=("outputs",),
            ),
            (workspace / "outputs" / "results" / "table.csv").resolve(),
        )
        with self.assertRaises(ValueError):
            self.storage_manager.resolve_workspace_relative_path(
                "/outputs/../escape.csv",
                thread_id,
                allowed_roots=("outputs",),
            )

    def test_thread_ids_and_windows_absolute_paths_cannot_escape_workspace(self) -> None:
        with self.assertRaises(ValueError):
            self.storage_manager.get_workspace("../outside")
        with self.assertRaises(ValueError):
            self.storage_manager.get_workspace("nested/thread")
        with self.assertRaises(ValueError):
            self.storage_manager.resolve_output_path(r"C:\outside\result.txt", "alice-safe")

    def test_atomic_write_rejects_quota_overflow_without_partial_file(self) -> None:
        thread_id = "alice-atomic-quota"
        workspace = self.storage_manager.get_workspace(thread_id)
        self._write_bytes(workspace / "inputs" / "existing.bin", 900 * 1024)

        with self.assertRaises(self.storage_manager_module.StorageQuotaExceededError):
            self.storage_manager.atomic_write_text(
                "too-large.txt",
                "x" * (200 * 1024),
                thread_id=thread_id,
            )

        self.assertFalse((workspace / "outputs" / "too-large.txt").exists())
        self.assertEqual(list((workspace / "outputs").glob(".tmp-*.tmp")), [])

    def test_atomic_write_uses_short_temp_prefix_for_long_contract_names(self) -> None:
        thread_id = "alice-long-contract"
        workspace = self.storage_manager.get_workspace(thread_id)
        parent = workspace / "outputs" / "runs" / "run-1" / "contracts"
        desired_filename_chars = 248 - len(str(parent)) - 1
        stem_budget = desired_filename_chars - len("event_context__") - len(".json")
        self.assertGreater(stem_budget, 32)
        long_name = "event_context__" + ("a" * stem_budget) + ".json"
        self.assertLessEqual(len(str(parent / long_name)), 248)
        captured_prefixes: list[str] = []
        real_named_temporary_file = tempfile.NamedTemporaryFile

        def capture_named_temporary_file(*args, **kwargs):
            captured_prefixes.append(str(kwargs.get("prefix")))
            return real_named_temporary_file(*args, **kwargs)

        with patch.object(
            self.storage_manager_module.tempfile,
            "NamedTemporaryFile",
            side_effect=capture_named_temporary_file,
        ):
            target = self.storage_manager.atomic_write_text(
                f"runs/run-1/contracts/{long_name}",
                '{"status":"ready"}',
                thread_id=thread_id,
            )

        self.assertEqual(captured_prefixes, [".tmp-"])
        self.assertEqual(target.read_text(encoding="utf-8"), '{"status":"ready"}')
        self.assertEqual(list(target.parent.glob(".tmp-*.tmp")), [])

    def test_jsonl_appends_are_valid_under_thread_concurrency(self) -> None:
        thread_id = "alice-jsonl"

        def append_event(index: int) -> None:
            self.storage_manager.append_jsonl(
                "events.jsonl",
                {"index": index},
                thread_id=thread_id,
            )

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(append_event, range(40)))

        history_path = self.storage_manager.get_workspace(thread_id) / "outputs" / "events.jsonl"
        records = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(records), 40)
        self.assertEqual({record["index"] for record in records}, set(range(40)))


if __name__ == "__main__":
    unittest.main()
