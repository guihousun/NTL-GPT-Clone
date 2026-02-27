import contextvars
import os
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Optional

# Thread-scoped context used across LangGraph/Deep Agents execution.
current_thread_id = contextvars.ContextVar("thread_id", default="debug")


class StorageManager:
    def __init__(self, base_dir: str = "user_data", shared_dir: str = "base_data"):
        self.base_dir = Path(base_dir).resolve()
        self.shared_dir = Path(shared_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)

    def get_workspace(self, thread_id: Optional[str] = None) -> Path:
        if thread_id is None:
            thread_id = current_thread_id.get()
        if not thread_id or not str(thread_id).strip():
            raise ValueError("No valid thread_id available in context or argument.")

        tid = str(thread_id).strip()
        workspace = self.base_dir / tid
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "inputs").mkdir(exist_ok=True)
        (workspace / "outputs").mkdir(exist_ok=True)
        (workspace / "memory").mkdir(exist_ok=True)
        return workspace

    @staticmethod
    def _is_deepagents_virtual_path(path_value: str) -> bool:
        if not isinstance(path_value, str):
            return False
        return path_value.startswith(("/data/raw/", "/data/processed/", "/memories/", "/shared/"))

    @staticmethod
    def _safe_virtual_tail(full_path: str, prefix: str) -> PurePosixPath:
        tail = full_path[len(prefix) :].strip("/")
        rel = PurePosixPath(tail)
        if not tail or rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Unsafe or empty virtual path tail: {full_path}")
        return rel

    def resolve_deepagents_path(self, deep_path: str, thread_id: Optional[str] = None) -> Path:
        workspace = self.get_workspace(thread_id)
        if deep_path.startswith("/data/raw/"):
            rel = self._safe_virtual_tail(deep_path, "/data/raw/")
            target = workspace / "inputs" / Path(*rel.parts)
        elif deep_path.startswith("/data/processed/"):
            rel = self._safe_virtual_tail(deep_path, "/data/processed/")
            target = workspace / "outputs" / Path(*rel.parts)
        elif deep_path.startswith("/memories/"):
            rel = self._safe_virtual_tail(deep_path, "/memories/")
            target = workspace / "memory" / Path(*rel.parts)
        elif deep_path.startswith("/shared/"):
            rel = self._safe_virtual_tail(deep_path, "/shared/")
            target = self.shared_dir / Path(*rel.parts)
        else:
            raise ValueError(f"Unknown Deep Agents virtual path: {deep_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target.resolve()

    @staticmethod
    def _is_shared_virtual_path(path_value: str) -> bool:
        return isinstance(path_value, str) and path_value.startswith("/shared/")

    def resolve_input_path(self, filename: str, thread_id: Optional[str] = None) -> str:
        if thread_id is None:
            thread_id = current_thread_id.get()
        tid = str(thread_id).strip()
        print(f"[StorageManager] Resolving '{filename}' for thread_id='{tid}'")

        if self._is_deepagents_virtual_path(filename):
            path_obj = self.resolve_deepagents_path(filename, tid)
            print(f"[StorageManager] Resolved virtual path to: {path_obj}")
            return str(path_obj)

        safe_filename = os.path.basename(filename)
        workspace = self.get_workspace(tid)
        user_input = workspace / "inputs" / safe_filename
        shared_input = self.shared_dir / safe_filename

        if user_input.exists():
            print(f"[StorageManager] Found in user workspace: {user_input}")
            return str(user_input.absolute())
        if shared_input.exists():
            print(f"[StorageManager] Found in shared directory: {shared_input}")
            return str(shared_input.absolute())
        print(f"[StorageManager] Not found. Defaulting to user workspace path: {user_input}")
        return str(user_input.absolute())

    def resolve_output_path(self, filename: str, thread_id: Optional[str] = None) -> str:
        if thread_id is None:
            thread_id = current_thread_id.get()
        tid = str(thread_id).strip()

        if self._is_deepagents_virtual_path(filename):
            if self._is_shared_virtual_path(filename):
                raise PermissionError(
                    "Shared dataset path is read-only. "
                    "Use resolve_input_path('/shared/...') for reading and resolve_output_path(...) for workspace outputs."
                )
            path_obj = self.resolve_deepagents_path(filename, tid)
            return str(path_obj)

        workspace = self.get_workspace(tid)
        safe_filename = os.path.basename(filename)
        output_path = workspace / "outputs" / safe_filename
        return str(output_path.absolute())

    def list_workspace(self, thread_id: Optional[str] = None) -> Dict[str, list[str]]:
        workspace = self.get_workspace(thread_id)
        return {
            "inputs": [p.name for p in (workspace / "inputs").glob("*") if p.is_file()],
            "outputs": [p.name for p in (workspace / "outputs").glob("*") if p.is_file()],
            "memory": [p.name for p in (workspace / "memory").glob("*") if p.is_file()],
        }

    @staticmethod
    def get_thread_id_from_config(config: Dict[str, Any]) -> str:
        return config.get("configurable", {}).get("thread_id", "")


storage_manager = StorageManager()
