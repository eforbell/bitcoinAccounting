"""Tests for the bitcoind-backed descriptor engine."""

from __future__ import annotations

from typing import Any

import pytest

from web.config import WebConfig
from web.services.descriptor_engine import (
    BitcoindDescriptorEngine,
    DescriptorEngineError,
)


class _FakeResponse:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict[str, Any]:
        return self._body


def _config() -> WebConfig:
    return WebConfig(
        bitcoin_rpc_url="http://127.0.0.1:8332",
        bitcoin_rpc_cookie_file="/tmp/fake.cookie",
    )


def test_inspect_descriptor_uses_multipath_expansion(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = BitcoindDescriptorEngine(_config())
    monkeypatch.setattr(
        engine,
        "_rpc_auth",
        lambda: ("user", "pass"),
    )

    def _fake_post(*args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(
            {
                "result": {
                    "descriptor": "wpkh(xpub/<0;1>/*)#abcd1234",
                    "checksum": "abcd1234",
                    "isrange": True,
                    "multipath_expansion": [
                        "wpkh(xpub/0/*)#a1",
                        "wpkh(xpub/1/*)#b2",
                    ],
                },
                "error": None,
            }
        )

    monkeypatch.setattr("web.services.descriptor_engine.requests.post", _fake_post)

    inspection = engine.inspect_descriptor("wpkh(xpub/<0;1>/*)")
    assert inspection.normalized_descriptor == "wpkh(xpub/<0;1>/*)#abcd1234"
    assert inspection.is_range is True
    assert [branch.branch_name for branch in inspection.branches] == ["branch_0", "branch_1"]


def test_derive_addresses_flattens_grouped_multipath_response(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = BitcoindDescriptorEngine(_config())
    monkeypatch.setattr(engine, "_rpc_auth", lambda: ("user", "pass"))

    def _fake_post(*args: object, **kwargs: object) -> _FakeResponse:
        return _FakeResponse(
            {
                "result": [
                    ["bc1qreceive0", "bc1qreceive1"],
                    ["bc1qchange0", "bc1qchange1"],
                ],
                "error": None,
            }
        )

    monkeypatch.setattr("web.services.descriptor_engine.requests.post", _fake_post)

    addresses = engine.derive_addresses("wpkh(xpub/<0;1>/*)", start_index=0, end_index=1)
    assert len(addresses) == 4
    assert addresses[0].branch_name == "branch_0"
    assert addresses[2].branch_name == "branch_1"
    assert addresses[3].index == 1


def test_derive_addresses_rejects_invalid_range() -> None:
    engine = BitcoindDescriptorEngine(_config())
    with pytest.raises(DescriptorEngineError):
        engine.derive_addresses("wpkh(xpub/0/*)", start_index=5, end_index=4)

