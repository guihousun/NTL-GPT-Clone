import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TARGETS = [
    ROOT / "tools" / "NTL_Knowledge_Base.py",
    ROOT / "tools" / "NTL_Knowledge_Base_Searcher.py",
    ROOT / "agents" / "NTL_Knowledge_Base_manager.py",
]


def test_no_hardcoded_openai_keys_in_target_files():
    key_pattern = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
    for path in TARGETS:
        content = path.read_text(encoding="utf-8")
        assert not key_pattern.search(content), f"Hardcoded key found in {path}"

