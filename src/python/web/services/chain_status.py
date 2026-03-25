"""Chain status service for optional Bitcoin node presence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from web.config import WebConfig
from web.models import ChainStatusResponse


class ChainStatusError(RuntimeError):
    """Raised when bitcoind RPC communication fails."""


@dataclass(frozen=True)
class _RpcCredentials:
    username: str
    password: str


class ChainStatusService:
    """Query a local bitcoind instance and normalize status data."""

    def __init__(self, config: WebConfig) -> None:
        self._config = config

    def get_status(self) -> ChainStatusResponse:
        """Return normalized chain status for the web dashboard."""
        if not self._config.chain_status_enabled:
            return self._unavailable(
                enabled=False,
                warning="Bitcoin node presence is disabled for this deployment.",
            )

        rpc_url = (self._config.bitcoin_rpc_url or "").strip()
        if not rpc_url:
            return self._unavailable(
                enabled=True,
                warning="Bitcoin RPC URL is not configured.",
            )

        try:
            blockchain = self._rpc_call("getblockchaininfo")
            network = self._rpc_call("getnetworkinfo")
            mempool = self._rpc_call("getmempoolinfo")
        except ChainStatusError as exc:
            return self._unavailable(enabled=True, warning=str(exc))

        block_height = int(blockchain.get("blocks", 0))
        header_height = int(blockchain.get("headers", 0))
        verification_progress = float(blockchain.get("verificationprogress", 0.0))
        initial_block_download = bool(blockchain.get("initialblockdownload", False))
        is_synced = (
            not initial_block_download
            and header_height <= block_height
            and verification_progress >= 0.9999
        )

        last_block_at = self._timestamp_to_datetime(blockchain.get("mediantime"))
        seconds_since_last_block = None
        if last_block_at is not None:
            seconds_since_last_block = int(
                (datetime.now(timezone.utc) - last_block_at).total_seconds()
            )

        warnings: list[str] = []
        chain_name = str(blockchain.get("chain", "unknown"))
        if chain_name != "main":
            warnings.append(f"Node is reporting '{chain_name}' chain, not mainnet.")
        if not is_synced:
            warnings.append("Node is still syncing and may not reflect the current tip yet.")
        if bool(blockchain.get("pruned", False)):
            warnings.append("Node is pruned; chain status is available but historical depth is limited.")

        return ChainStatusResponse(
            enabled=True,
            available=True,
            source="bitcoind",
            network=chain_name,
            block_height=block_height,
            header_height=header_height,
            verification_progress=verification_progress,
            is_synced=is_synced,
            last_block_at=last_block_at,
            seconds_since_last_block=seconds_since_last_block,
            peer_count=int(network.get("connections", 0)),
            mempool_tx_count=int(mempool.get("size", 0)),
            mempool_usage_bytes=int(mempool.get("usage", 0)),
            pruned=bool(blockchain.get("pruned", False)),
            warnings=warnings,
            refreshed_at=datetime.now(timezone.utc),
        )

    def _unavailable(self, *, enabled: bool, warning: str) -> ChainStatusResponse:
        return ChainStatusResponse(
            enabled=enabled,
            available=False,
            source="bitcoind",
            network=None,
            block_height=None,
            header_height=None,
            verification_progress=None,
            is_synced=None,
            last_block_at=None,
            seconds_since_last_block=None,
            peer_count=None,
            mempool_tx_count=None,
            mempool_usage_bytes=None,
            pruned=None,
            warnings=[warning],
            refreshed_at=datetime.now(timezone.utc),
        )

    def _rpc_call(self, method: str) -> dict[str, Any]:
        payload = {
            "jsonrpc": "1.0",
            "id": method,
            "method": method,
            "params": [],
        }
        try:
            response = requests.post(
                (self._config.bitcoin_rpc_url or "").strip(),
                json=payload,
                auth=self._rpc_auth(),
                timeout=self._config.bitcoin_rpc_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (OSError, ValueError, requests.RequestException) as exc:
            raise ChainStatusError(f"Bitcoin RPC unavailable: {exc}") from exc

        error = body.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise ChainStatusError(f"Bitcoin RPC error: {message}")

        result = body.get("result")
        if not isinstance(result, dict):
            raise ChainStatusError(
                f"Bitcoin RPC returned invalid result for method '{method}'."
            )
        return result

    def _rpc_auth(self) -> tuple[str, str]:
        cookie_file = (self._config.bitcoin_rpc_cookie_file or "").strip()
        if cookie_file:
            return self._load_cookie_auth(cookie_file)
        return (
            (self._config.bitcoin_rpc_user or "").strip(),
            (self._config.bitcoin_rpc_password or "").strip(),
        )

    @staticmethod
    def _load_cookie_auth(cookie_file: str) -> tuple[str, str]:
        try:
            cookie_text = Path(cookie_file).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ChainStatusError(f"Unable to read Bitcoin RPC cookie file: {exc}") from exc

        username, separator, password = cookie_text.partition(":")
        if not separator or not username or not password:
            raise ChainStatusError("Bitcoin RPC cookie file is malformed.")
        return username, password

    @staticmethod
    def _timestamp_to_datetime(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (TypeError, ValueError, OSError):
            return None
