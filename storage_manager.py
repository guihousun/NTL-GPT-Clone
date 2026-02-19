import os
from pathlib import Path
from typing import Dict, Any, Optional
import contextvars

# 创建一个上下文变量，用于保存当前会话的 thread_id
current_thread_id = contextvars.ContextVar("thread_id", default="debug")

class StorageManager:
    def __init__(self, base_dir="user_data", shared_dir="base_data"):
        self.base_dir = Path(base_dir).resolve()
        self.shared_dir = Path(shared_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.shared_dir.mkdir(parents=True, exist_ok=True)

    def get_workspace(self, thread_id: Optional[str] = None) -> Path:
        # 修正后的逻辑：优先使用参数，参数没有再拿上下文
        if thread_id is None:
            thread_id = current_thread_id.get()
            
        if not thread_id or not thread_id.strip():
            raise ValueError("No valid thread_id available in context or argument.")
        
        tid = thread_id.strip()
        workspace = self.base_dir / tid
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / "inputs").mkdir(exist_ok=True)
        (workspace / "outputs").mkdir(exist_ok=True)
        return workspace

    def resolve_input_path(self, filename: str, thread_id: Optional[str] = None) -> str:
        if thread_id is None:
            thread_id = current_thread_id.get()
        
        # Debugging print
        print(f"[StorageManager] Resolving '{filename}' for thread_id='{thread_id}'")
        
        # Clean the filename to prevent double path segments (e.g. inputs/inputs/file.tif)
        safe_filename = os.path.basename(filename)
        
        workspace = self.get_workspace(thread_id)
        user_input = workspace / "inputs" / safe_filename
        shared_input = self.shared_dir / safe_filename

        if user_input.exists():
            print(f"[StorageManager] Found in user workspace: {user_input}")
            return str(user_input.absolute())
        elif shared_input.exists():
            print(f"[StorageManager] Found in shared directory: {shared_input}")
            return str(shared_input.absolute())
        else:
            print(f"[StorageManager] Not found. Defaulting to user workspace path: {user_input}")
            return str(user_input.absolute())

    def resolve_output_path(self, filename: str, thread_id: Optional[str] = None) -> str:
        if thread_id is None:
            thread_id = current_thread_id.get()
        workspace = self.get_workspace(thread_id)
        safe_filename = os.path.basename(filename)
        output_path = workspace / "outputs" / safe_filename
        return str(output_path.absolute())

    @staticmethod
    def get_thread_id_from_config(config: Dict[str, Any]) -> str:
        """
        从 LangChain/LangGraph 的 RunnableConfig 中安全提取 thread_id。
        用法示例：
            tid = storage_manager.get_thread_id_from_config(config)
        """
        return config.get("configurable", {}).get("thread_id", "")

# 单例模式
storage_manager = StorageManager()