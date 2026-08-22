"""Tests for the Bitcoin Core proof-of-spend RPC adapter."""

from __future__ import annotations

from typing import Any

import pytest

from web.config import WebConfig
from web.services.proof_of_spend import ProofOfSpendRPCClient, ProofOfSpendRPCError


class _FakeResponse:
    def __init__(self, body: dict[str, Any]) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


def test_rpc_adapter_uses_testmempoolaccept_without_broadcasting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_post(url: str, **kwargs: object) -> _FakeResponse:
        captured.update({"url": url, **kwargs})
        return _FakeResponse(
            {
                "result": [
                    {
                        "txid": "a" * 64,
                        "wtxid": "b" * 64,
                        "allowed": True,
                        "vsize": 141,
                        "fees": {"base": 0.0000141},
                    }
                ],
                "error": None,
            }
        )

    monkeypatch.setattr("web.services.proof_of_spend.requests.post", _fake_post)
    client = ProofOfSpendRPCClient(
        WebConfig(
            bitcoin_rpc_url="http://127.0.0.1:8332",
            bitcoin_rpc_user="rpc-user",
            bitcoin_rpc_password="rpc-pass",
            bitcoin_rpc_timeout_seconds=7,
        )
    )

    result = client.test_mempool_accept("deadbeef")

    assert result["allowed"] is True
    assert captured["url"] == "http://127.0.0.1:8332"
    assert captured["auth"] == ("rpc-user", "rpc-pass")
    assert captured["timeout"] == 7
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["method"] == "testmempoolaccept"
    assert payload["params"] == [["deadbeef"]]
    assert "sendrawtransaction" not in str(payload)


def test_rpc_adapter_rejects_malformed_core_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "web.services.proof_of_spend.requests.post",
        lambda *args, **kwargs: _FakeResponse({"result": [], "error": None}),
    )
    client = ProofOfSpendRPCClient(
        WebConfig(
            bitcoin_rpc_url="http://127.0.0.1:8332",
            bitcoin_rpc_user="rpc-user",
            bitcoin_rpc_password="rpc-pass",
        )
    )

    with pytest.raises(ProofOfSpendRPCError, match="invalid testmempoolaccept result"):
        client.test_mempool_accept("00")


def test_rpc_adapter_requires_rpc_url() -> None:
    client = ProofOfSpendRPCClient(WebConfig())

    with pytest.raises(ProofOfSpendRPCError, match="URL is not configured"):
        client.test_mempool_accept("00")
