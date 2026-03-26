"""Verification result persistence for web wallet verification."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from uuid import uuid4

from bitcoinAccounts import BitcoinAccounts
from db import DatabaseBackend
from web.config import WebConfig
from web.services.descriptor_engine import BitcoindDescriptorEngine, DerivedAddress, DescriptorInspection
from web.services.descriptor_engine import DescriptorEngineError
from web.services.electrum_client import ElectrumClient, ElectrumClientError, ElectrumEndpoint
from web.models_verification import (
    PortfolioVerificationPostureResource,
    WalletVerificationCreateRequest,
    WalletVerificationEligibilityResource,
    WalletVerificationListResponse,
    WalletVerificationRunResponse,
    WalletVerificationResource,
)

_RUNS_TABLE = "web_wallet_verification_runs"
_STATE_TABLE = "web_wallet_verification_state"
_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_BECH32M_CONST = 0x2BC830A3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.isoformat()


def ensure_wallet_verification_tables(backend: DatabaseBackend) -> None:
    """Create lightweight web-owned verification tables if absent."""
    backend.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_RUNS_TABLE} (
            verification_id TEXT PRIMARY KEY,
            wallet_id TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage TEXT NOT NULL,
            descriptor_source_type TEXT NOT NULL,
            recency_window_days INTEGER NOT NULL,
            ledger_balance REAL NULL,
            verified_balance REAL NULL,
            drift_btc REAL NULL,
            chain_height INTEGER NULL,
            branch_count INTEGER NULL,
            descriptor_count INTEGER NULL,
            highest_scanned_index INTEGER NULL,
            highest_used_index INTEGER NULL,
            scan_ceiling INTEGER NULL,
            gap_limit INTEGER NULL,
            warning_text TEXT NULL,
            error_text TEXT NULL,
            verified_at TEXT NOT NULL,
            stale_after TEXT NOT NULL
        )
        """
    )
    backend.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_STATE_TABLE} (
            wallet_id TEXT PRIMARY KEY,
            verification_id TEXT NOT NULL,
            status TEXT NOT NULL,
            coverage TEXT NOT NULL,
            descriptor_source_type TEXT NOT NULL,
            recency_window_days INTEGER NOT NULL,
            ledger_balance REAL NULL,
            verified_balance REAL NULL,
            drift_btc REAL NULL,
            chain_height INTEGER NULL,
            branch_count INTEGER NULL,
            descriptor_count INTEGER NULL,
            highest_scanned_index INTEGER NULL,
            highest_used_index INTEGER NULL,
            scan_ceiling INTEGER NULL,
            gap_limit INTEGER NULL,
            warning_text TEXT NULL,
            error_text TEXT NULL,
            verified_at TEXT NOT NULL,
            stale_after TEXT NOT NULL
        )
        """
    )
    backend.commit()


def _row_to_resource(row: dict[str, object]) -> WalletVerificationResource:
    verified_at = datetime.fromisoformat(str(row["verified_at"]))
    stale_after = datetime.fromisoformat(str(row["stale_after"]))
    now = _utcnow()
    return WalletVerificationResource(
        verification_id=str(row["verification_id"]),
        wallet_id=str(row["wallet_id"]),
        status=str(row["status"]),
        coverage=str(row["coverage"]),
        descriptor_source_type=str(row["descriptor_source_type"]),
        recency_window_days=int(row["recency_window_days"]),
        is_recent=stale_after >= now,
        ledger_balance=float(row["ledger_balance"]) if row["ledger_balance"] is not None else None,
        verified_balance=float(row["verified_balance"]) if row["verified_balance"] is not None else None,
        drift_btc=float(row["drift_btc"]) if row["drift_btc"] is not None else None,
        chain_height=int(row["chain_height"]) if row["chain_height"] is not None else None,
        branch_count=int(row["branch_count"]) if row["branch_count"] is not None else None,
        descriptor_count=int(row["descriptor_count"]) if row["descriptor_count"] is not None else None,
        highest_scanned_index=(
            int(row["highest_scanned_index"]) if row["highest_scanned_index"] is not None else None
        ),
        highest_used_index=(
            int(row["highest_used_index"]) if row["highest_used_index"] is not None else None
        ),
        scan_ceiling=int(row["scan_ceiling"]) if row["scan_ceiling"] is not None else None,
        gap_limit=int(row["gap_limit"]) if row["gap_limit"] is not None else None,
        warning_text=str(row["warning_text"]) if row["warning_text"] is not None else None,
        error_text=str(row["error_text"]) if row["error_text"] is not None else None,
        verified_at=verified_at,
        stale_after=stale_after,
    )


def record_wallet_verification_run(
    backend: DatabaseBackend,
    *,
    wallet_id: str,
    status: str,
    coverage: str,
    descriptor_source_type: str = "session",
    recency_window_days: int = 30,
    ledger_balance: float | None = None,
    verified_balance: float | None = None,
    drift_btc: float | None = None,
    chain_height: int | None = None,
    branch_count: int | None = None,
    descriptor_count: int | None = None,
    highest_scanned_index: int | None = None,
    highest_used_index: int | None = None,
    scan_ceiling: int | None = None,
    gap_limit: int | None = None,
    warning_text: str | None = None,
    error_text: str | None = None,
    verified_at: datetime | None = None,
) -> WalletVerificationResource:
    """Persist one verification run and update latest wallet state."""
    ensure_wallet_verification_tables(backend)
    now = verified_at or _utcnow()
    stale_after = now + timedelta(days=recency_window_days)
    verification_id = str(uuid4())
    params = {
        "verification_id": verification_id,
        "wallet_id": wallet_id,
        "status": status,
        "coverage": coverage,
        "descriptor_source_type": descriptor_source_type,
        "recency_window_days": recency_window_days,
        "ledger_balance": ledger_balance,
        "verified_balance": verified_balance,
        "drift_btc": drift_btc,
        "chain_height": chain_height,
        "branch_count": branch_count,
        "descriptor_count": descriptor_count,
        "highest_scanned_index": highest_scanned_index,
        "highest_used_index": highest_used_index,
        "scan_ceiling": scan_ceiling,
        "gap_limit": gap_limit,
        "warning_text": warning_text,
        "error_text": error_text,
        "verified_at": _isoformat(now),
        "stale_after": _isoformat(stale_after),
    }
    backend.execute(
        f"""
        INSERT INTO {_RUNS_TABLE} (
            verification_id, wallet_id, status, coverage, descriptor_source_type,
            recency_window_days, ledger_balance, verified_balance, drift_btc,
            chain_height, branch_count, descriptor_count, highest_scanned_index,
            highest_used_index, scan_ceiling, gap_limit, warning_text, error_text,
            verified_at, stale_after
        ) VALUES (
            :verification_id, :wallet_id, :status, :coverage, :descriptor_source_type,
            :recency_window_days, :ledger_balance, :verified_balance, :drift_btc,
            :chain_height, :branch_count, :descriptor_count, :highest_scanned_index,
            :highest_used_index, :scan_ceiling, :gap_limit, :warning_text, :error_text,
            :verified_at, :stale_after
        )
        """,
        params,
    )
    backend.execute(
        f"""
        INSERT INTO {_STATE_TABLE} (
            wallet_id, verification_id, status, coverage, descriptor_source_type,
            recency_window_days, ledger_balance, verified_balance, drift_btc,
            chain_height, branch_count, descriptor_count, highest_scanned_index,
            highest_used_index, scan_ceiling, gap_limit, warning_text, error_text,
            verified_at, stale_after
        ) VALUES (
            :wallet_id, :verification_id, :status, :coverage, :descriptor_source_type,
            :recency_window_days, :ledger_balance, :verified_balance, :drift_btc,
            :chain_height, :branch_count, :descriptor_count, :highest_scanned_index,
            :highest_used_index, :scan_ceiling, :gap_limit, :warning_text, :error_text,
            :verified_at, :stale_after
        )
        ON CONFLICT(wallet_id) DO UPDATE SET
            verification_id = excluded.verification_id,
            status = excluded.status,
            coverage = excluded.coverage,
            descriptor_source_type = excluded.descriptor_source_type,
            recency_window_days = excluded.recency_window_days,
            ledger_balance = excluded.ledger_balance,
            verified_balance = excluded.verified_balance,
            drift_btc = excluded.drift_btc,
            chain_height = excluded.chain_height,
            branch_count = excluded.branch_count,
            descriptor_count = excluded.descriptor_count,
            highest_scanned_index = excluded.highest_scanned_index,
            highest_used_index = excluded.highest_used_index,
            scan_ceiling = excluded.scan_ceiling,
            gap_limit = excluded.gap_limit,
            warning_text = excluded.warning_text,
            error_text = excluded.error_text,
            verified_at = excluded.verified_at,
            stale_after = excluded.stale_after
        """,
        params,
    )
    backend.commit()
    row = backend.execute_one(
        f"SELECT * FROM {_RUNS_TABLE} WHERE verification_id = :verification_id",
        {"verification_id": verification_id},
    )
    if row is None:
        raise RuntimeError("Verification run was persisted but could not be reloaded.")
    return _row_to_resource(row)


def get_latest_wallet_verification(
    backend: DatabaseBackend,
    wallet_id: str,
) -> WalletVerificationResource | None:
    """Return the latest persisted verification state for one wallet."""
    ensure_wallet_verification_tables(backend)
    row = backend.execute_one(
        f"SELECT * FROM {_STATE_TABLE} WHERE wallet_id = :wallet_id",
        {"wallet_id": wallet_id},
    )
    return _row_to_resource(row) if row is not None else None


def list_wallet_verification_runs(
    backend: DatabaseBackend,
    wallet_id: str,
    *,
    limit: int = 20,
) -> list[WalletVerificationResource]:
    """Return recent verification runs for one wallet."""
    ensure_wallet_verification_tables(backend)
    rows = backend.execute(
        f"""
        SELECT *
        FROM {_RUNS_TABLE}
        WHERE wallet_id = :wallet_id
        ORDER BY verified_at DESC
        LIMIT :limit
        """,
        {"wallet_id": wallet_id, "limit": limit},
    )
    return [_row_to_resource(row) for row in rows]


def build_portfolio_verification_posture(
    backend: DatabaseBackend,
    *,
    eligible_wallet_ids: list[str],
    recency_window_days: int = 30,
) -> PortfolioVerificationPostureResource:
    """Build a strict aggregate verification posture for dashboard surfaces."""
    ensure_wallet_verification_tables(backend)
    refreshed_at = _utcnow()
    if not eligible_wallet_ids:
        return PortfolioVerificationPostureResource(
            status="ineligible",
            recency_window_days=recency_window_days,
            eligible_wallet_count=0,
            verified_wallet_count=0,
            partial_wallet_count=0,
            stale_wallet_count=0,
            failed_wallet_count=0,
            drift_wallet_count=0,
            refreshed_at=refreshed_at,
        )

    latest_rows = [
        get_latest_wallet_verification(backend, wallet_id)
        for wallet_id in eligible_wallet_ids
    ]
    verified = 0
    partial = 0
    stale = 0
    failed = 0
    drift = 0
    for row in latest_rows:
        if row is None:
            stale += 1
            continue
        if not row.is_recent:
            stale += 1
        elif row.status == "verified" and row.coverage == "full":
            verified += 1
        elif row.status == "drift_detected":
            drift += 1
        elif row.status == "failed":
            failed += 1
        else:
            partial += 1

    status = "not_fully_verified"
    if verified == len(eligible_wallet_ids):
        status = "verified"
    elif failed:
        status = "failed"
    elif drift:
        status = "drift_detected"
    elif partial:
        status = "partial_coverage"
    elif stale:
        status = "stale"

    return PortfolioVerificationPostureResource(
        status=status,
        recency_window_days=recency_window_days,
        eligible_wallet_count=len(eligible_wallet_ids),
        verified_wallet_count=verified,
        partial_wallet_count=partial,
        stale_wallet_count=stale,
        failed_wallet_count=failed,
        drift_wallet_count=drift,
        refreshed_at=refreshed_at,
    )


def get_wallet_verification_list(
    backend: DatabaseBackend,
    wallet_id: str,
    *,
    limit: int = 20,
) -> WalletVerificationListResponse:
    """Return latest + recent history for one wallet."""
    latest = get_latest_wallet_verification(backend, wallet_id)
    runs = list_wallet_verification_runs(backend, wallet_id, limit=limit)
    return WalletVerificationListResponse(wallet_id=wallet_id, latest=latest, runs=runs)


def get_wallet_verification_eligibility(
    accounts: BitcoinAccounts,
    wallet_id: str,
) -> WalletVerificationEligibilityResource:
    """Return whether a wallet is eligible for descriptor-based verification."""
    wallet_meta = next(
        (wallet for wallet in accounts.get_wallets(active_only=False) if wallet.get("wallet_id") == wallet_id),
        None,
    )
    if wallet_meta is None:
        return WalletVerificationEligibilityResource(
            eligible=False,
            reason="Wallet was not found in wallet metadata.",
        )

    custody = str(wallet_meta.get("custody") or "").strip().lower()
    wallet_type = str(wallet_meta.get("type") or "").strip().lower()
    if custody in {"custodial", "exchange", "third-party"} or wallet_type == "exchange":
        return WalletVerificationEligibilityResource(
            eligible=False,
            reason="Descriptor-based verification is only available for self-custodied or multisig wallets.",
        )

    if custody in {"self-custodied", "self", "cold", "hardware", "hot", "multisig", "multi-sig", "collaborative"}:
        return WalletVerificationEligibilityResource(eligible=True)

    return WalletVerificationEligibilityResource(
        eligible=False,
        reason="Wallet custody is unknown. Set wallet custody to self-custodied or multisig before verifying.",
    )


def run_manual_wallet_verification(
    accounts: BitcoinAccounts,
    config: WebConfig,
    payload: WalletVerificationCreateRequest,
) -> WalletVerificationRunResponse:
    """Run the first balance-only manual verification flow."""
    ensure_wallet_verification_tables(accounts.backend)
    wallet_id = payload.wallet_id.strip()
    eligibility = get_wallet_verification_eligibility(accounts, wallet_id)
    if not eligibility.eligible:
        raise ValueError(eligibility.reason or "Wallet is not eligible for descriptor verification.")

    ledger_balance = float(accounts.get_balance_by_account("BTC", wallet_id))
    tx_count = int(
        accounts.backend.execute_scalar(
            """
            SELECT COUNT(*)
            FROM ledger
            WHERE exchange = :wallet_id
            AND (deleted = 0 OR deleted IS NULL)
            """,
            {"wallet_id": wallet_id},
        )
        or 0
    )

    if ledger_balance == 0.0 and tx_count == 0:
        result = record_wallet_verification_run(
            accounts.backend,
            wallet_id=wallet_id,
            status="not_meaningful",
            coverage="none",
            recency_window_days=config.verification_recency_days,
            ledger_balance=0.0,
            verified_balance=None,
            warning_text="Wallet has no meaningful on-chain ledger activity to verify yet.",
        )
        return WalletVerificationRunResponse(
            result=result,
            ledger_transaction_count=tx_count,
            meaningful_to_verify=False,
        )

    descriptors = _resolve_descriptor_inputs(payload)
    engine = BitcoindDescriptorEngine(config)
    electrum = _build_electrum_client(config)

    branches: list[tuple[str, str]] = []
    try:
        for descriptor in descriptors:
            inspection = engine.inspect_descriptor(descriptor)
            branches.extend(_named_branches(inspection))
        if not branches:
            raise RuntimeError("No descriptor branches were available after inspection.")

        first_scan_ceiling = payload.first_scan_ceiling or 50
        all_addresses: list[DerivedAddress] = []
        for branch_name, descriptor in branches:
            derived = engine.derive_addresses(
                descriptor,
                start_index=0,
                end_index=max(first_scan_ceiling - 1, 0),
            )
            all_addresses.extend(
                DerivedAddress(
                    branch_name=branch_name,
                    index=row.index,
                    address=row.address,
                )
                for row in derived
            )

        verified_sats = 0
        highest_scanned_index = None
        highest_used_index = None
        scripthashes_by_row: list[tuple[DerivedAddress, str]] = [
            (row, _electrum_scripthash_for_address(row.address))
            for row in all_addresses
        ]
        balances_by_scripthash = electrum.get_scripthash_balances(
            [scripthash for _, scripthash in scripthashes_by_row]
        )
        for row, scripthash in scripthashes_by_row:
            balance = balances_by_scripthash[scripthash]
            total = int(balance["confirmed"]) + int(balance["unconfirmed"])
            if total != 0:
                if highest_used_index is None or row.index > highest_used_index:
                    highest_used_index = row.index
            verified_sats += total
            if highest_scanned_index is None or row.index > highest_scanned_index:
                highest_scanned_index = row.index

        verified_balance = verified_sats / 100_000_000
        drift_btc = verified_balance - ledger_balance
        status = "verified" if abs(drift_btc) < 1e-12 else "drift_detected"
        coverage = "full" if payload.descriptor else "partial"
        result = record_wallet_verification_run(
            accounts.backend,
            wallet_id=wallet_id,
            status=status,
            coverage=coverage,
            recency_window_days=config.verification_recency_days,
            ledger_balance=ledger_balance,
            verified_balance=verified_balance,
            drift_btc=drift_btc,
            descriptor_count=len(descriptors),
            branch_count=len(branches),
            highest_scanned_index=highest_scanned_index,
            highest_used_index=highest_used_index,
            scan_ceiling=first_scan_ceiling,
            gap_limit=payload.gap_limit,
        )
    except (DescriptorEngineError, ElectrumClientError) as exc:
        record_wallet_verification_run(
            accounts.backend,
            wallet_id=wallet_id,
            status="failed",
            coverage="partial" if payload.external_descriptor or payload.change_descriptor else "none",
            recency_window_days=config.verification_recency_days,
            ledger_balance=ledger_balance,
            error_text=str(exc),
            scan_ceiling=payload.first_scan_ceiling or 50,
            gap_limit=payload.gap_limit,
        )
        raise
    except Exception as exc:
        result = record_wallet_verification_run(
            accounts.backend,
            wallet_id=wallet_id,
            status="failed",
            coverage="partial" if payload.external_descriptor or payload.change_descriptor else "none",
            recency_window_days=config.verification_recency_days,
            ledger_balance=ledger_balance,
            error_text=str(exc),
            scan_ceiling=payload.first_scan_ceiling or 50,
            gap_limit=payload.gap_limit,
        )

    return WalletVerificationRunResponse(
        result=result,
        ledger_transaction_count=tx_count,
        meaningful_to_verify=True,
    )


def _resolve_descriptor_inputs(payload: WalletVerificationCreateRequest) -> list[str]:
    descriptors: list[str] = []
    if payload.descriptor:
        descriptors.append(payload.descriptor.strip())
    if payload.external_descriptor:
        descriptors.append(payload.external_descriptor.strip())
    if payload.change_descriptor:
        descriptors.append(payload.change_descriptor.strip())
    descriptors = [descriptor for descriptor in descriptors if descriptor]
    if not descriptors:
        raise ValueError("Provide a combined descriptor or at least one branch descriptor.")
    return descriptors


def _build_electrum_client(config: WebConfig) -> ElectrumClient:
    host = (config.electrum_host or "").strip()
    port = config.electrum_port
    if not host or port is None:
        raise RuntimeError("Electrum host/port are not configured.")
    return ElectrumClient(
        ElectrumEndpoint(
            host=host,
            port=port,
            use_ssl=config.electrum_use_ssl,
            timeout_seconds=config.electrum_timeout_seconds,
        )
    )


def _named_branches(inspection: DescriptorInspection) -> list[tuple[str, str]]:
    if len(inspection.branches) == 1:
        return [("primary", inspection.branches[0].descriptor)]
    names = ["receive", "change"]
    result: list[tuple[str, str]] = []
    for idx, branch in enumerate(inspection.branches):
        branch_name = names[idx] if idx < len(names) else branch.branch_name
        result.append((branch_name, branch.descriptor))
    return result


def _electrum_scripthash_for_address(address: str) -> str:
    script_bytes = _address_to_script_pub_key(address)
    return sha256(script_bytes).digest()[::-1].hex()


def _address_to_script_pub_key(address: str) -> bytes:
    normalized = address.strip()
    if not normalized:
        raise RuntimeError("Derived address was empty.")
    if normalized.lower().startswith(("bc1", "tb1", "bcrt1")):
        return _segwit_script_pub_key(normalized)
    return _base58_script_pub_key(normalized)


def _base58_script_pub_key(address: str) -> bytes:
    payload = _base58check_decode(address)
    if len(payload) != 21:
        raise RuntimeError("Unsupported Base58 address payload length.")
    version = payload[0]
    data = payload[1:]
    if version in {0x00, 0x6F}:  # mainnet/testnet p2pkh
        return b"\x76\xa9\x14" + data + b"\x88\xac"
    if version in {0x05, 0xC4}:  # mainnet/testnet p2sh
        return b"\xa9\x14" + data + b"\x87"
    raise RuntimeError(f"Unsupported Base58 address version: {version}")


def _segwit_script_pub_key(address: str) -> bytes:
    hrp, data, encoding_constant = _bech32_decode(address)
    if hrp not in {"bc", "tb", "bcrt"}:
        raise RuntimeError(f"Unsupported segwit address prefix: {hrp}")
    if not data:
        raise RuntimeError("Segwit address payload was empty.")

    witness_version = data[0]
    witness_program = bytes(_convert_bits(data[1:], 5, 8, pad=False))
    if witness_version > 16:
        raise RuntimeError("Unsupported witness version.")
    if not (2 <= len(witness_program) <= 40):
        raise RuntimeError("Invalid witness program length.")
    if witness_version == 0:
        if len(witness_program) not in {20, 32}:
            raise RuntimeError("Version 0 witness program must be 20 or 32 bytes.")
        if encoding_constant != 1:
            raise RuntimeError("Version 0 segwit addresses must use Bech32 checksum.")
        version_opcode = 0x00
    else:
        if encoding_constant != _BECH32M_CONST:
            raise RuntimeError("Witness versions 1+ must use Bech32m checksum.")
        version_opcode = 0x50 + witness_version
    return bytes([version_opcode, len(witness_program)]) + witness_program


def _base58check_decode(value: str) -> bytes:
    number = 0
    for char in value:
        try:
            digit = _BASE58_ALPHABET.index(char)
        except ValueError as exc:
            raise RuntimeError(f"Invalid Base58 character: {char}") from exc
        number = number * 58 + digit

    decoded = number.to_bytes((number.bit_length() + 7) // 8, byteorder="big")
    leading_zeroes = len(value) - len(value.lstrip("1"))
    payload = (b"\x00" * leading_zeroes) + decoded
    if len(payload) < 5:
        raise RuntimeError("Base58 address payload was too short.")
    body, checksum = payload[:-4], payload[-4:]
    expected = sha256(sha256(body).digest()).digest()[:4]
    if checksum != expected:
        raise RuntimeError("Base58 address checksum mismatch.")
    return body


def _bech32_decode(value: str) -> tuple[str, list[int], int]:
    if value.lower() != value and value.upper() != value:
        raise RuntimeError("Bech32 address cannot mix uppercase and lowercase.")
    normalized = value.lower()
    separator = normalized.rfind("1")
    if separator <= 0 or separator + 7 > len(normalized):
        raise RuntimeError("Invalid Bech32 separator position.")
    hrp = normalized[:separator]
    data_chars = normalized[separator + 1 :]
    try:
        data = [_BECH32_CHARSET.index(char) for char in data_chars]
    except ValueError as exc:
        raise RuntimeError("Invalid Bech32 character.") from exc
    polymod = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if polymod == 1:
        encoding_constant = 1
    elif polymod == _BECH32M_CONST:
        encoding_constant = _BECH32M_CONST
    else:
        raise RuntimeError("Bech32 checksum mismatch.")
    return hrp, data[:-6], encoding_constant


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _bech32_polymod(values: list[int]) -> int:
    generator = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for idx, factor in enumerate(generator):
            if (top >> idx) & 1:
                checksum ^= factor
    return checksum


def _convert_bits(data: list[int], from_bits: int, to_bits: int, *, pad: bool) -> list[int]:
    accumulator = 0
    bits = 0
    result: list[int] = []
    max_value = (1 << to_bits) - 1
    for value in data:
        if value < 0 or value >> from_bits:
            raise RuntimeError("Invalid value during bit conversion.")
        accumulator = (accumulator << from_bits) | value
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            result.append((accumulator >> bits) & max_value)
    if pad:
        if bits:
            result.append((accumulator << (to_bits - bits)) & max_value)
    elif bits >= from_bits or ((accumulator << (to_bits - bits)) & max_value):
        raise RuntimeError("Invalid padding during bit conversion.")
    return result
