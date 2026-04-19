from __future__ import annotations

import json
import re
from pathlib import Path


BASE = Path("docs/isw_storymap_raw")


def main() -> None:
    data = json.loads((BASE / "data.json").read_text(encoding="utf-8"))
    item = json.loads((BASE / "item.json").read_text(encoding="utf-8"))
    print("title:", item.get("title"))
    print("owner:", item.get("owner"))
    print("type:", item.get("type"))
    print("modified:", item.get("modified"))

    text = json.dumps(data, ensure_ascii=False)
    ids = sorted(set(re.findall(r"(?<![a-f0-9])[a-f0-9]{32}(?![a-f0-9])", text, re.I)))
    print("32hex ids", len(ids))
    for value in ids:
        print("id", value)

    urls = sorted(set(re.findall(r"https?://[^\"\\s]+", text)))
    print("urls", len(urls))
    for value in urls:
        print("url", value[:500])

    print("topkeys", [(key, type(value).__name__) for key, value in data.items()])
    print("resources", list(data.get("resources", {}).keys())[:80])
    print("nodes", list(data.get("nodes", {}).keys())[:80])

    resources = data.get("resources", {})
    for key, value in resources.items():
        if isinstance(value, dict):
            print("resource", key, value.get("type"), value.get("itemId"), value.get("url"))


if __name__ == "__main__":
    main()
