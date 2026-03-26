"""Minimal Electrum JSON-RPC client seam for wallet verification."""

from __future__ import annotations

import json
import socket
import ssl
from dataclasses import dataclass
from typing import Any


class ElectrumClientError(RuntimeError):
    """Raised when Electrum RPC communication fails."""


@dataclass(frozen=True)
class ElectrumEndpoint:
    """Connection details for an Electrum-compatible server."""

    host: str
    port: int
    use_ssl: bool = False
    timeout_seconds: float = 5.0


class ElectrumClient:
    """Minimal line-delimited JSON-RPC client for Electrum servers."""

    def __init__(self, endpoint: ElectrumEndpoint) -> None:
        self._endpoint = endpoint
        self._next_id = 1
        self._conn: socket.socket | ssl.SSLSocket | None = None

    def server_version(
        self,
        client_name: str = "bitcoin-accounting",
        protocol_version: str = "1.4",
    ) -> list[object]:
        result = self._rpc_call("server.version", [client_name, protocol_version])
        if not isinstance(result, list):
            raise ElectrumClientError("Electrum server.version returned invalid payload.")
        return result

    def get_scripthash_balance(self, scripthash: str) -> dict[str, int]:
        result = self._rpc_call("blockchain.scripthash.get_balance", [scripthash])
        if not isinstance(result, dict):
            raise ElectrumClientError("Electrum balance payload was invalid.")
        return {
            "confirmed": int(result.get("confirmed", 0)),
            "unconfirmed": int(result.get("unconfirmed", 0)),
        }

    def get_scripthash_balances(self, scripthashes: list[str]) -> dict[str, dict[str, int]]:
        results: dict[str, dict[str, int]] = {}
        with self.session():
            for scripthash in scripthashes:
                results[scripthash] = self.get_scripthash_balance(scripthash)
        return results

    def get_scripthash_history(self, scripthash: str) -> list[dict[str, object]]:
        result = self._rpc_call("blockchain.scripthash.get_history", [scripthash])
        if not isinstance(result, list):
            raise ElectrumClientError("Electrum history payload was invalid.")
        history: list[dict[str, object]] = []
        for item in result:
            if isinstance(item, dict):
                history.append(dict(item))
        return history

    def close(self) -> None:
        conn = self._conn
        self._conn = None
        if conn is not None:
            conn.close()

    def session(self) -> "_ElectrumSession":
        return _ElectrumSession(self)

    def _rpc_call(self, method: str, params: list[object]) -> Any:
        request_id = self._next_id
        self._next_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        raw = (json.dumps(payload) + "\n").encode("utf-8")
        try:
            conn = self._ensure_connection()
            conn.sendall(raw)
            conn.settimeout(self._endpoint.timeout_seconds)
            response = self._recv_line(conn)
        except OSError as exc:
            self.close()
            raise ElectrumClientError(f"Electrum RPC unavailable: {exc}") from exc
        try:
            body = json.loads(response.decode("utf-8"))
        except ValueError as exc:
            self.close()
            raise ElectrumClientError(f"Electrum RPC returned invalid JSON: {exc}") from exc
        if body.get("id") != request_id:
            raise ElectrumClientError("Electrum RPC response ID mismatch.")
        error = body.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ElectrumClientError(f"Electrum RPC error: {message}")
        return body.get("result")

    def _ensure_connection(self) -> socket.socket | ssl.SSLSocket:
        if self._conn is not None:
            return self._conn
        sock = socket.create_connection(
            (self._endpoint.host, self._endpoint.port),
            timeout=self._endpoint.timeout_seconds,
        )
        conn: socket.socket | ssl.SSLSocket = sock
        if self._endpoint.use_ssl:
            context = ssl.create_default_context()
            conn = context.wrap_socket(sock, server_hostname=self._endpoint.host)
        self._conn = conn
        return conn

    @staticmethod
    def _recv_line(conn: socket.socket | ssl.SSLSocket, max_bytes: int = 1_000_000) -> bytes:
        data = bytearray()
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ElectrumClientError("Electrum RPC response exceeded maximum size.")
            if b"\n" in chunk:
                break
        if not data:
            raise ElectrumClientError("Electrum RPC returned no data.")
        return bytes(data.splitlines()[0])


class _ElectrumSession:
    def __init__(self, client: ElectrumClient) -> None:
        self._client = client

    def __enter__(self) -> ElectrumClient:
        self._client._ensure_connection()
        return self._client

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._client.close()
