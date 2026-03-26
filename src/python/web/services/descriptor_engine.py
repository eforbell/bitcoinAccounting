"""Descriptor-engine abstraction and bitcoind-backed implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

from web.config import WebConfig


class DescriptorEngineError(RuntimeError):
    """Raised when descriptor inspection or derivation fails."""


@dataclass(frozen=True)
class DescriptorBranch:
    """One descriptor branch after normalization/expansion."""

    branch_name: str
    descriptor: str


@dataclass(frozen=True)
class DescriptorInspection:
    """Normalized descriptor inspection result."""

    normalized_descriptor: str
    checksum: str | None
    is_range: bool
    branches: list[DescriptorBranch]


@dataclass(frozen=True)
class DerivedAddress:
    """One derived address with branch/index metadata."""

    branch_name: str
    index: int
    address: str


class DescriptorEngine(Protocol):
    """Abstract descriptor-engine interface."""

    def inspect_descriptor(self, descriptor: str) -> DescriptorInspection:
        """Validate and normalize one descriptor."""

    def derive_addresses(self, descriptor: str, *, start_index: int, end_index: int) -> list[DerivedAddress]:
        """Derive addresses for one descriptor and index range."""


class BitcoindDescriptorEngine:
    """Use local bitcoind as the descriptor authority for v1."""

    def __init__(self, config: WebConfig) -> None:
        self._config = config

    def inspect_descriptor(self, descriptor: str) -> DescriptorInspection:
        body = self._rpc_call("getdescriptorinfo", [descriptor])
        normalized = body.get("descriptor")
        if not isinstance(normalized, str) or not normalized:
            raise DescriptorEngineError("Bitcoin Core returned an invalid normalized descriptor.")
        is_range = bool(body.get("isrange", False))
        checksum = self._extract_checksum(normalized)
        multipath = body.get("multipath_expansion")
        branches: list[DescriptorBranch]
        if isinstance(multipath, list) and multipath:
            branches = [
                DescriptorBranch(branch_name=f"branch_{idx}", descriptor=str(item))
                for idx, item in enumerate(multipath)
            ]
        else:
            branches = [DescriptorBranch(branch_name="primary", descriptor=normalized)]
        return DescriptorInspection(
            normalized_descriptor=normalized,
            checksum=checksum,
            is_range=is_range,
            branches=branches,
        )

    def derive_addresses(
        self,
        descriptor: str,
        *,
        start_index: int,
        end_index: int,
    ) -> list[DerivedAddress]:
        if start_index < 0 or end_index < start_index:
            raise DescriptorEngineError("Invalid descriptor derivation range.")
        body = self._rpc_call("deriveaddresses", [descriptor, [start_index, end_index]])
        if not isinstance(body, list):
            raise DescriptorEngineError("Bitcoin Core returned invalid deriveaddresses payload.")
        derived: list[DerivedAddress] = []
        if body and all(isinstance(item, list) for item in body):
            for branch_idx, group in enumerate(body):
                for offset, address in enumerate(group):
                    derived.append(
                        DerivedAddress(
                            branch_name=f"branch_{branch_idx}",
                            index=start_index + offset,
                            address=str(address),
                        )
                    )
            return derived
        for offset, address in enumerate(body):
            derived.append(
                DerivedAddress(
                    branch_name="primary",
                    index=start_index + offset,
                    address=str(address),
                )
            )
        return derived

    def _rpc_call(self, method: str, params: list[object]) -> Any:
        rpc_url = (self._config.bitcoin_rpc_url or "").strip()
        if not rpc_url:
            raise DescriptorEngineError("Bitcoin RPC URL is not configured.")
        payload = {"jsonrpc": "1.0", "id": method, "method": method, "params": params}
        try:
            response = requests.post(
                rpc_url,
                json=payload,
                auth=self._rpc_auth(),
                timeout=self._config.bitcoin_rpc_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
        except (OSError, ValueError, requests.RequestException) as exc:
            raise DescriptorEngineError(f"Bitcoin descriptor RPC unavailable: {exc}") from exc
        error = body.get("error")
        if error:
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise DescriptorEngineError(f"Bitcoin descriptor RPC error: {message}")
        return body.get("result")

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
            raise DescriptorEngineError(f"Unable to read Bitcoin RPC cookie file: {exc}") from exc
        username, separator, password = cookie_text.partition(":")
        if not separator or not username or not password:
            raise DescriptorEngineError("Bitcoin RPC cookie file is malformed.")
        return username, password

    @staticmethod
    def _extract_checksum(descriptor: str) -> str | None:
        _, separator, checksum = descriptor.rpartition("#")
        if not separator:
            return None
        return checksum

