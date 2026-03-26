"""Tests for the Electrum client seam."""

from __future__ import annotations

import json

import pytest

from web.services.electrum_client import ElectrumClient, ElectrumClientError, ElectrumEndpoint


class _FakeSocket:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = [
            (json.dumps(response) + "\n").encode("utf-8")
            for response in responses
        ]
        self.sent: list[bytes] = []
        self.closed = False

    def __enter__(self) -> "_FakeSocket":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def sendall(self, data: bytes) -> None:
        self.sent.append(data)

    def recv(self, size: int) -> bytes:
        if not self._responses:
            return b""
        return self._responses.pop(0)

    def settimeout(self, timeout: float) -> None:
        return None


def test_electrum_client_server_version(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSocket(
        [{"jsonrpc": "2.0", "id": 1, "result": ["electrs 0.10.9", "1.4"], "error": None}]
    )
    monkeypatch.setattr(
        "web.services.electrum_client.socket.create_connection",
        lambda *args, **kwargs: fake,
    )

    client = ElectrumClient(ElectrumEndpoint(host="127.0.0.1", port=50001))
    result = client.server_version()

    assert result == ["electrs 0.10.9", "1.4"]
    request = json.loads(fake.sent[0].decode("utf-8"))
    assert request["method"] == "server.version"


def test_electrum_client_balance_and_history(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeSocket(
        [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {"confirmed": 1234, "unconfirmed": -5},
                "error": None,
            },
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": [{"tx_hash": "abc", "height": 100}],
                "error": None,
            },
        ]
    )
    monkeypatch.setattr(
        "web.services.electrum_client.socket.create_connection",
        lambda *args, **kwargs: fake,
    )

    client = ElectrumClient(ElectrumEndpoint(host="127.0.0.1", port=50001))
    balance = client.get_scripthash_balance("deadbeef")
    history = client.get_scripthash_history("deadbeef")

    assert balance["confirmed"] == 1234
    assert balance["unconfirmed"] == -5
    assert history[0]["tx_hash"] == "abc"


def test_electrum_client_reuses_one_connection_for_batched_balances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSocket(
        [
            {"jsonrpc": "2.0", "id": 1, "result": {"confirmed": 1, "unconfirmed": 0}, "error": None},
            {"jsonrpc": "2.0", "id": 2, "result": {"confirmed": 2, "unconfirmed": 0}, "error": None},
        ]
    )
    connection_calls = 0

    def _fake_create_connection(*args: object, **kwargs: object) -> _FakeSocket:
        nonlocal connection_calls
        connection_calls += 1
        return fake

    monkeypatch.setattr(
        "web.services.electrum_client.socket.create_connection",
        _fake_create_connection,
    )

    client = ElectrumClient(ElectrumEndpoint(host="127.0.0.1", port=50001))
    balances = client.get_scripthash_balances(["a", "b"])

    assert connection_calls == 1
    assert balances["a"]["confirmed"] == 1
    assert balances["b"]["confirmed"] == 2
    assert fake.closed is True


def test_electrum_client_rejects_response_id_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _FakeSocket(
        [{"jsonrpc": "2.0", "id": 999, "result": ["electrs 0.10.9", "1.4"], "error": None}]
    )
    monkeypatch.setattr(
        "web.services.electrum_client.socket.create_connection",
        lambda *args, **kwargs: fake,
    )

    client = ElectrumClient(ElectrumEndpoint(host="127.0.0.1", port=50001))
    with pytest.raises(ElectrumClientError, match="ID mismatch"):
        client.server_version()


def test_electrum_client_rejects_oversized_line() -> None:
    with pytest.raises(ElectrumClientError, match="maximum size"):
        ElectrumClient._recv_line(  # type: ignore[arg-type]
            _OversizedSocket(),
            max_bytes=64,
        )


class _OversizedSocket:
    def recv(self, size: int) -> bytes:
        return b"x" * size
