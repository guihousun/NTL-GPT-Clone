from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_SRC = REPO_ROOT / "packages" / "ntl_toolkit" / "src"
if str(PACKAGE_SRC) not in sys.path:
    sys.path.insert(0, str(PACKAGE_SRC))

from ntl_toolkit.adapters.mcp.gis_core import build_gis_core_mcp


def build():
    return build_gis_core_mcp()


def main() -> None:
    build().run(transport="stdio")


if __name__ == "__main__":
    main()
