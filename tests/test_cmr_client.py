from __future__ import annotations

from types import SimpleNamespace

from experiments.official_daily_ntl_fastpath import cmr_client


def test_cmr_json_falls_back_to_requests_after_curl_transport_failure(monkeypatch) -> None:
    monkeypatch.setattr(cmr_client, "_require_curl", lambda: "curl.exe")
    monkeypatch.setattr(
        cmr_client.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=35, stderr="schannel", stdout=""),
    )

    calls: dict[str, object] = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"feed": {"entry": []}}

    def fake_get(url: str, *, headers: dict[str, str], timeout: int) -> Response:
        calls.update(url=url, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr(cmr_client.requests, "get", fake_get)

    result = cmr_client._run_curl_json("https://cmr.example.test/query", ["X-Test: yes"], 17)

    assert result == {"feed": {"entry": []}}
    assert calls["headers"] == {"X-Test": "yes"}
