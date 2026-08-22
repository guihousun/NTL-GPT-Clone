from __future__ import annotations

from pathlib import Path

import pytest

from ntl_toolkit.schemas import ToolResult
from ntl_toolkit.core import vnp46a1_download as core
from tools import _EXPORTS, _GROUPS
from tools import vnp46a1_official_h5_tool as module


@pytest.fixture()
def isolated_workspace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    workspace = tmp_path / "thread"
    monkeypatch.setattr(module, "_thread_id", lambda config=None: "thread")
    monkeypatch.setattr(module.storage_manager, "get_workspace", lambda thread_id: workspace)
    return workspace


def test_official_vnp46a1_tool_is_registered_for_data_searcher() -> None:
    name = "official_vnp46a1_h5_tool"
    assert name in _EXPORTS
    assert name in _GROUPS["data_searcher_tools"]
    assert name in _GROUPS["specialized_tool_catalog"]
    assert name not in _GROUPS["engineer_tools"]


def test_vnp46a1_plan_is_bbox_scoped_and_preserves_utc_time(isolated_workspace: Path) -> None:
    result = module.run_official_vnp46a1_h5(
        start_date="2026-08-07",
        end_date="2026-08-07",
        output_root="vnp46a1_test",
        bbox=[121.0, 30.0, 122.0, 31.0],
        include_utc_time=True,
        execution_mode="plan",
    )

    assert result["status"] == "plan"
    assert result["product"] == "VNP46A1"
    assert result["band"] == "DNB_At_Sensor_Radiance_500m"
    assert result["include_utc_time"] is True
    assert result["target_mode"] == "bbox"
    assert result["output_root"] == str(isolated_workspace / "outputs" / "vnp46a1_test")


def test_vnp46a1_requires_exactly_one_target_mode() -> None:
    with pytest.raises(ValueError, match="exactly one of countries or bbox"):
        module.run_official_vnp46a1_h5(
            start_date="2026-08-07",
            end_date="2026-08-07",
            countries=["CHN"],
            bbox=[121.0, 30.0, 122.0, 31.0],
            execution_mode="plan",
        )


def test_vnp46a1_run_delegates_to_shared_core_without_provider(
    isolated_workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_run(request, *, progress=None):
        seen["request"] = request
        seen["progress"] = progress
        return ToolResult.succeeded(
            tool="download_vnp46a1_official_h5",
            summary="fake bounded execution",
            metrics={"run_root": str(request.run_root)},
        )

    monkeypatch.setattr(module, "run_vnp46a1_download", fake_run)
    result = module.run_official_vnp46a1_h5(
        start_date="2026-08-07",
        end_date="2026-08-07",
        output_root="vnp46a1_test",
        bbox=[121.0, 30.0, 122.0, 31.0],
        include_utc_time=True,
        execution_mode="run",
    )

    request = seen["request"]
    assert result["status"] == "succeeded"
    assert list(request.bbox) == [121.0, 30.0, 122.0, 31.0]
    assert request.include_utc_time is True
    assert request.output_root == str(isolated_workspace / "outputs" / "vnp46a1_test")


def test_vnp46a1_download_guard_uses_dotenv_resolver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = core.Vnp46a1DownloadRequest(
        start_date="2026-08-07",
        end_date="2026-08-07",
        output_root=str(tmp_path / "run"),
        bbox=[121.0, 30.0, 122.0, 31.0],
        phase="download",
        execution_mode="run",
    )
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    monkeypatch.setattr(
        "experiments.official_daily_ntl_fastpath.cmr_client.resolve_token",
        lambda _name: "dotenv-token",
    )
    monkeypatch.setattr(core, "_prepare_geometry", lambda _request: object())
    seen: dict[str, object] = {}

    def fake_download(_request, _geometry):
        seen["called"] = True

    monkeypatch.setattr(core, "_download_days", fake_download)
    result = core.run_vnp46a1_download(request)

    assert result.status == "succeeded"
    assert seen["called"] is True
