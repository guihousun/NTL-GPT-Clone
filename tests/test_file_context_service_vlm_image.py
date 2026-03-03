from __future__ import annotations

from pathlib import Path

from PIL import Image

import file_context_service


def _mk_image(path: Path, suffix: str) -> Path:
    p = path / f"sample{suffix}"
    Image.new("RGB", (64, 32), color=(12, 34, 56)).save(p)
    return p


def test_image_vlm_summary_uses_multimodal_payload(tmp_path, monkeypatch):
    img = _mk_image(tmp_path, ".png")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fake-key")

    captured = {"init": None, "msgs": None}

    class _FakeResp:
        content = "Detected nighttime urban pattern."

    class _FakeLLM:
        def __init__(self, **kwargs):
            captured["init"] = kwargs

        def invoke(self, msgs):
            captured["msgs"] = msgs
            return _FakeResp()

    monkeypatch.setattr(file_context_service, "ChatOpenAI", _FakeLLM)

    text, meta, warning = file_context_service._image_vlm_summary(
        img, model_name="qwen3.5-plus", timeout_s=30
    )

    assert warning is None
    assert "nighttime urban" in text.lower()
    assert meta["understanding_mode"] == "vlm_e2e"
    assert captured["init"]["model"] == "qwen3.5-plus"
    assert captured["msgs"] and isinstance(captured["msgs"], list)
    content = captured["msgs"][0].content
    assert isinstance(content, list) and len(content) >= 2
    assert content[1]["type"] == "image_url"
    assert str(content[1]["image_url"]["url"]).startswith("data:image/png;base64,")


def test_build_context_items_for_png_and_jpg_are_vlm_tagged(tmp_path, monkeypatch):
    png = _mk_image(tmp_path, ".png")
    jpg = _mk_image(tmp_path, ".jpg")

    def _fake_resolve(name: str, thread_id: str):
        if name == png.name:
            return png
        if name == jpg.name:
            return jpg
        return None

    monkeypatch.setattr(file_context_service, "_resolve_existing_workspace_file", lambda filename, thread_id, workspace_lookup="auto": _fake_resolve(filename, thread_id))
    monkeypatch.setattr(
        file_context_service,
        "_image_vlm_summary",
        lambda path, model_name="qwen3.5-plus", api_key=None, timeout_s=90: (
            f"VLM summary for {path.name}",
            {"understanding_mode": "vlm_e2e", "model": model_name},
            None,
        ),
    )

    out = file_context_service.build_context_items_for_files(
        thread_id="user-abc",
        file_names=[png.name, jpg.name],
        vlm_model_name="qwen3.5-plus",
    )

    assert out["status"] in {"success", "partial"}
    assert len(out["items"]) == 2
    sources = {row["source_file"] for row in out["items"]}
    assert sources == {png.name, jpg.name}
    for row in out["items"]:
        assert "vlm" in row.get("tags", [])
        assert row["meta"]["understanding_mode"] == "vlm_e2e"


def test_build_context_items_can_resolve_outputs_when_requested(tmp_path, monkeypatch):
    out_img = _mk_image(tmp_path, ".png")
    out_img = out_img.rename(tmp_path / "result.png")

    def _fake_resolve(name: str, thread_id: str, workspace_lookup: str = "auto"):
        if workspace_lookup == "outputs" and name == out_img.name:
            return out_img
        return None

    monkeypatch.setattr(file_context_service, "_resolve_existing_workspace_file", _fake_resolve)
    monkeypatch.setattr(
        file_context_service,
        "_image_vlm_summary",
        lambda path, model_name="qwen3.5-plus", api_key=None, timeout_s=90: (
            f"VLM summary for {path.name}",
            {"understanding_mode": "vlm_e2e", "model": model_name},
            None,
        ),
    )

    out = file_context_service.build_context_items_for_files(
        thread_id="user-xyz",
        file_names=[out_img.name],
        workspace_lookup="outputs",
        vlm_model_name="qwen3.5-plus",
    )
    assert out["status"] in {"success", "partial"}
    assert len(out["items"]) == 1
    assert out["items"][0]["source_file"] == out_img.name
