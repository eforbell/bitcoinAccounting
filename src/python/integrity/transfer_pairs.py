"""Transfer-pair integrity checks for treasury integrity.

Detects likely broken internal transfers: one-sided withdrawal/deposit,
amount mismatch above tolerance, and fee anomalies.  Returns severity-tiered
findings consumable by CLI and TUI.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..db.backend import DatabaseBackend

# Default configurable tolerances
DEFAULT_AMOUNT_TOLERANCE: float = 0.001  # 0.1 % relative tolerance
DEFAULT_TIME_WINDOW_HOURS: int = 48
DEFAULT_FEE_ANOMALY_THRESHOLD: float = 0.05  # 5 % fee-to-amount ratio

# Transaction types treated as outgoing / incoming
_SEND_TYPES: frozenset[str] = frozenset({"Withdrawal", "Transfer"})
_RECEIVE_TYPES: frozenset[str] = frozenset({"Deposit", "Transfer"})


class Severity(str, Enum):
    """Severity tier for a transfer-pair finding."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class TransferRecord:
    """A single transfer-direction transaction from the ledger.

    Attributes:
        tx_id: Primary key of the ledger row.
        createddate: Transaction date string (``YYYY-MM-DD``).
        trans_type: Raw transaction type from the ledger.
        coin: Currency code (e.g. ``'BTC'``).
        amount: Absolute amount moved (positive).
        fee: Fee amount on this transaction, or ``None``.
        fee_curr: Currency of the fee, or ``None``.
        wallet: Exchange/wallet name.
        direction: ``"send"`` for outgoing, ``"receive"`` for incoming.
    """

    tx_id: int
    createddate: str
    trans_type: str
    coin: str
    amount: float
    fee: float | None
    fee_curr: str | None
    wallet: str
    direction: str


@dataclass
class TransferFinding:
    """A single integrity finding for a transfer or transfer pair.

    Attributes:
        finding_id: Unique identifier (UUID4).
        severity: :class:`Severity` tier for this finding.
        category: One of ``"one_sided_send"``, ``"one_sided_receive"``,
            ``"amount_mismatch"``, ``"fee_anomaly"``.
        description: Human-readable description of the issue.
        send_tx_id: Ledger ID of the send-side transaction, or ``None``.
        receive_tx_id: Ledger ID of the receive-side transaction, or ``None``.
        coin: Coin code involved.
        send_wallet: Wallet name on the send side, or ``None``.
        receive_wallet: Wallet name on the receive side, or ``None``.
        send_amount: Gross amount sent, or ``None``.
        receive_amount: Net amount received, or ``None``.
        fee_amount: Fee amount from the send transaction, or ``None``.
    """

    finding_id: str
    severity: Severity
    category: str
    description: str
    send_tx_id: int | None
    receive_tx_id: int | None
    coin: str
    send_wallet: str | None
    receive_wallet: str | None
    send_amount: float | None
    receive_amount: float | None
    fee_amount: float | None


@dataclass
class TransferPairResult:
    """Full transfer-pair integrity scan result.

    Attributes:
        coin_filter: Coin filter applied, or ``None`` for all coins.
        wallet_filter: Wallet filter applied, or ``None`` for all wallets.
        start_date: Inclusive start date, or ``None``.
        end_date: Inclusive end date, or ``None``.
        time_window_hours: Maximum hours between matched send/receive.
        amount_tolerance: Relative tolerance for amount matching (0.0–1.0).
        fee_anomaly_threshold: Fee-to-amount ratio that triggers INFO findings.
        findings: List of integrity findings.
        total_transfers_checked: Total send + receive transactions scanned.
        matched_pairs: Count of successfully matched send/receive pairs.
        unmatched_sends: Count of sends with no matching receive.
        unmatched_receives: Count of receives with no matching send.
        amount_mismatches: Count of matched pairs with amount discrepancy.
        fee_anomalies: Count of fee anomaly findings.
        is_clean: ``True`` when no findings exist.
    """

    coin_filter: str | None
    wallet_filter: str | None
    start_date: str | None
    end_date: str | None
    time_window_hours: int
    amount_tolerance: float
    fee_anomaly_threshold: float
    findings: list[TransferFinding] = field(default_factory=list)
    total_transfers_checked: int = 0
    matched_pairs: int = 0
    unmatched_sends: int = 0
    unmatched_receives: int = 0
    amount_mismatches: int = 0
    fee_anomalies: int = 0
    is_clean: bool = True


@dataclass
class TransferPairSnapshot:
    """Immutable timestamped snapshot wrapping a :class:`TransferPairResult`.

    Attributes:
        run_id: Unique identifier for this scan run (UUID4).
        timestamp: ISO 8601 UTC timestamp of when the snapshot was taken.
        result: The underlying transfer-pair result.
    """

    run_id: str
    timestamp: str
    result: TransferPairResult


class TransferPairChecker:
    """Detect broken internal transfer pairs in the ledger.

    Each call to :meth:`run` produces a :class:`TransferPairSnapshot` with a
    fresh ``run_id`` and ``timestamp``, ensuring snapshots are individually
    identifiable for trend tracking.

    Args:
        backend: Database backend used for all queries.
        time_window_hours: Maximum hours between matched send/receive.
            Defaults to :data:`DEFAULT_TIME_WINDOW_HOURS`.
        amount_tolerance: Relative tolerance for amount matching.
            Defaults to :data:`DEFAULT_AMOUNT_TOLERANCE`.
        fee_anomaly_threshold: Fee-to-amount ratio that triggers INFO findings.
            Defaults to :data:`DEFAULT_FEE_ANOMALY_THRESHOLD`.
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        time_window_hours: int = DEFAULT_TIME_WINDOW_HOURS,
        amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
        fee_anomaly_threshold: float = DEFAULT_FEE_ANOMALY_THRESHOLD,
    ) -> None:
        self._backend = backend
        self._time_window_hours = time_window_hours
        self._amount_tolerance = amount_tolerance
        self._fee_anomaly_threshold = fee_anomaly_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        coin: str | None = None,
        wallet: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> TransferPairSnapshot:
        """Run transfer-pair integrity check and return a timestamped snapshot.

        Args:
            coin: Restrict to this coin. ``None`` = all coins.
            wallet: Restrict to this wallet. ``None`` = all wallets.
            start_date: Inclusive start date (``YYYY-MM-DD``). ``None`` = no
                lower bound.
            end_date: Inclusive end date (``YYYY-MM-DD``). ``None`` = no
                upper bound.

        Returns:
            :class:`TransferPairSnapshot` with a unique run_id.
        """
        exclusive_end = self._exclusive_end(end_date)
        sends = self._fetch_transfers("send", coin, wallet, start_date, exclusive_end)
        receives = self._fetch_transfers(
            "receive", coin, wallet, start_date, exclusive_end
        )

        findings: list[TransferFinding] = []
        matched_pair_count = 0
        amount_mismatch_count = 0
        fee_anomaly_count = 0

        unmatched_receives = list(receives)
        unmatched_sends: list[TransferRecord] = []

        for send in sends:
            matched = self._find_best_match(send, unmatched_receives)
            if matched is None:
                unmatched_sends.append(send)
            else:
                unmatched_receives.remove(matched)
                matched_pair_count += 1

                gross_send = send.amount
                net_receive = matched.amount
                fee = self._coin_fee(send)
                expected_receive = gross_send - fee
                relative_diff = abs(net_receive - expected_receive) / max(
                    gross_send, 1e-10
                )

                if relative_diff > self._amount_tolerance:
                    amount_mismatch_count += 1
                    findings.append(
                        self._make_finding(
                            Severity.WARNING,
                            "amount_mismatch",
                            (
                                f"Transfer pair {send.coin} "
                                f"{send.wallet}\u2192{matched.wallet}: "
                                f"sent {gross_send:.8f}, received {net_receive:.8f} "
                                f"(expected \u2248{expected_receive:.8f}, "
                                f"diff {relative_diff * 100:.3f}%)"
                            ),
                            send_tx_id=send.tx_id,
                            receive_tx_id=matched.tx_id,
                            coin=send.coin,
                            send_wallet=send.wallet,
                            receive_wallet=matched.wallet,
                            send_amount=gross_send,
                            receive_amount=net_receive,
                            fee_amount=send.fee,
                        )
                    )

                if self._coin_fee(send) > 0 and gross_send > 1e-10:
                    fee_ratio = self._coin_fee(send) / gross_send
                    if fee_ratio > self._fee_anomaly_threshold:
                        fee_anomaly_count += 1
                        findings.append(
                            self._make_finding(
                                Severity.INFO,
                                "fee_anomaly",
                                (
                                    f"High fee on {send.coin} transfer from "
                                    f"{send.wallet}: fee {send.fee:.8f} is "
                                    f"{fee_ratio * 100:.2f}% of sent amount"
                                ),
                                send_tx_id=send.tx_id,
                                receive_tx_id=matched.tx_id,
                                coin=send.coin,
                                send_wallet=send.wallet,
                                receive_wallet=matched.wallet,
                                send_amount=gross_send,
                                receive_amount=net_receive,
                                fee_amount=send.fee,
                            )
                        )

        # Unmatched sends → CRITICAL (we know funds left but never arrived)
        for send in unmatched_sends:
            if self._coin_fee(send) > 0 and send.amount > 1e-10:
                fee_ratio = self._coin_fee(send) / send.amount
                if fee_ratio > self._fee_anomaly_threshold:
                    fee_anomaly_count += 1
                    findings.append(
                        self._make_finding(
                            Severity.INFO,
                            "fee_anomaly",
                            (
                                f"High fee on unmatched {send.coin} send from "
                                f"{send.wallet}: fee {send.fee:.8f} is "
                                f"{fee_ratio * 100:.2f}% of sent amount"
                            ),
                            send_tx_id=send.tx_id,
                            receive_tx_id=None,
                            coin=send.coin,
                            send_wallet=send.wallet,
                            receive_wallet=None,
                            send_amount=send.amount,
                            receive_amount=None,
                            fee_amount=send.fee,
                        )
                    )
            findings.append(
                self._make_finding(
                    Severity.CRITICAL,
                    "one_sided_send",
                    (
                        f"Unmatched send: {send.coin} {send.amount:.8f} "
                        f"from {send.wallet} on {send.createddate} — no matching "
                        f"receive found within {self._time_window_hours}h window"
                    ),
                    send_tx_id=send.tx_id,
                    receive_tx_id=None,
                    coin=send.coin,
                    send_wallet=send.wallet,
                    receive_wallet=None,
                    send_amount=send.amount,
                    receive_amount=None,
                    fee_amount=send.fee,
                )
            )

        # Unmatched receives → WARNING (could be external deposit, less alarming)
        for recv in unmatched_receives:
            findings.append(
                self._make_finding(
                    Severity.WARNING,
                    "one_sided_receive",
                    (
                        f"Unmatched receive: {recv.coin} {recv.amount:.8f} "
                        f"at {recv.wallet} on {recv.createddate} — no matching "
                        f"send found within {self._time_window_hours}h window"
                    ),
                    send_tx_id=None,
                    receive_tx_id=recv.tx_id,
                    coin=recv.coin,
                    send_wallet=None,
                    receive_wallet=recv.wallet,
                    send_amount=None,
                    receive_amount=recv.amount,
                    fee_amount=None,
                )
            )

        result = TransferPairResult(
            coin_filter=coin,
            wallet_filter=wallet,
            start_date=start_date,
            end_date=end_date,
            time_window_hours=self._time_window_hours,
            amount_tolerance=self._amount_tolerance,
            fee_anomaly_threshold=self._fee_anomaly_threshold,
            findings=findings,
            total_transfers_checked=len(sends) + len(receives),
            matched_pairs=matched_pair_count,
            unmatched_sends=len(unmatched_sends),
            unmatched_receives=len(unmatched_receives),
            amount_mismatches=amount_mismatch_count,
            fee_anomalies=fee_anomaly_count,
            is_clean=(len(findings) == 0),
        )

        return TransferPairSnapshot(
            run_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            result=result,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _exclusive_end(end_date: str | None) -> str | None:
        """Convert an inclusive end date to an exclusive upper bound."""
        if end_date is None:
            return None
        dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        return (dt + timedelta(days=1)).strftime("%Y-%m-%d")

    def _fetch_transfers(
        self,
        direction: str,
        coin_filter: str | None,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[TransferRecord]:
        """Query the ledger for send or receive transfer transactions."""
        if direction == "send":
            type_set = _SEND_TYPES
            coin_col = "sell_curr"
            amount_col = "sell"
        else:
            type_set = _RECEIVE_TYPES
            coin_col = "buy_curr"
            amount_col = "buy"

        type_placeholders = ", ".join(
            f":type_{i}" for i in range(len(type_set))
        )
        params: dict[str, Any] = {
            f"type_{i}": t for i, t in enumerate(sorted(type_set))
        }
        clauses = [
            "(deleted = 0 OR deleted IS NULL)",
            f"trans_type IN ({type_placeholders})",
            f"{coin_col} IS NOT NULL",
            f"{amount_col} IS NOT NULL",
            f"{amount_col} > 0",
        ]

        if coin_filter is not None:
            clauses.append(f"{coin_col} = :coin_filter")
            params["coin_filter"] = coin_filter

        if wallet_filter is not None:
            clauses.append("exchange = :wallet_filter")
            params["wallet_filter"] = wallet_filter

        if start_date is not None:
            clauses.append("createddate >= :start_date")
            params["start_date"] = start_date

        if exclusive_end is not None:
            clauses.append("createddate < :exclusive_end")
            params["exclusive_end"] = exclusive_end

        where = "WHERE " + " AND ".join(clauses)
        query = f"""
            SELECT id, createddate, trans_type,
                   {coin_col} AS coin, {amount_col} AS amount,
                   fee, fee_curr, exchange AS wallet
            FROM ledger
            {where}
            ORDER BY createddate, id
        """
        rows = self._backend.execute(query, params)
        return [
            TransferRecord(
                tx_id=int(row["id"]),
                createddate=row["createddate"],
                trans_type=row["trans_type"],
                coin=row["coin"],
                amount=float(row["amount"]),
                fee=float(row["fee"]) if row["fee"] is not None else None,
                fee_curr=row["fee_curr"],
                wallet=row["wallet"] or "",
                direction=direction,
            )
            for row in rows
        ]

    def _find_best_match(
        self,
        send: TransferRecord,
        candidates: list[TransferRecord],
    ) -> TransferRecord | None:
        """Find the best matching receive for a given send transaction.

        Criteria (all must hold):
        - Same coin
        - Different wallet
        - Receive date within ``time_window_hours`` of send date
        - Net receive amount within 50 % of expected receive (gross minus fee)

        Returns:
            Best candidate (lowest absolute amount difference), or ``None``.
        """
        send_dt = self._parse_date(send.createddate)
        window = timedelta(hours=self._time_window_hours)
        gross_send = send.amount
        fee = self._coin_fee(send)
        expected_receive = gross_send - fee

        best: TransferRecord | None = None
        best_diff: float = float("inf")

        for candidate in candidates:
            if candidate.coin != send.coin:
                continue
            if candidate.wallet == send.wallet:
                continue
            recv_dt = self._parse_date(candidate.createddate)
            if abs((recv_dt - send_dt).total_seconds()) > window.total_seconds():
                continue
            diff = abs(candidate.amount - expected_receive)
            if diff < best_diff:
                best = candidate
                best_diff = diff

        # Reject if the best match is implausibly far from expected (> 50 %)
        if best is not None:
            relative_diff = best_diff / max(gross_send, 1e-10)
            if relative_diff > 0.5:
                return None
        return best

    @staticmethod
    def _coin_fee(send: TransferRecord) -> float:
        """Return the fee only when it is denominated in the same coin as the transfer.

        A fee in a different currency (e.g. USD fee on a BTC transfer) must
        not be subtracted from the expected coin receive amount, as doing so
        corrupts the matching expectation and generates false findings.
        When ``fee_curr`` is ``None`` the fee is assumed to be in the transfer
        coin (legacy records that do not track fee currency).
        """
        if send.fee is None:
            return 0.0
        if send.fee_curr is None or send.fee_curr == send.coin:
            return send.fee
        return 0.0

    @staticmethod
    def _parse_date(date_str: str | datetime) -> datetime:
        """Parse a date value into a naive datetime for time-window comparisons.

        The PostgreSQL backend returns ``datetime`` objects directly from
        psycopg2; SQLite returns strings.  Both cases are handled:

        * ``datetime`` — returned as-is (timezone info stripped if present).
        * ``str`` — fractional-second and ``Z``-suffix variants are tried
          before the bare-date fallback so that full time precision is kept.
        """
        if isinstance(date_str, datetime):
            # psycopg2 may return timezone-aware datetimes; strip tzinfo so
            # comparisons with naive datetimes don't raise TypeError.
            return date_str.replace(tzinfo=None)
        # Strip a trailing 'Z' (UTC marker) before format matching so that
        # ISO 8601 timestamps like '2021-04-08T19:18:37.381Z' are handled
        # correctly rather than falling back to date-only precision.
        clean = date_str.rstrip("Z")
        for fmt in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
        ):
            try:
                return datetime.strptime(clean, fmt)
            except ValueError:
                continue
        return datetime.strptime(clean[:10], "%Y-%m-%d")

    @staticmethod
    def _make_finding(
        severity: Severity,
        category: str,
        description: str,
        *,
        send_tx_id: int | None,
        receive_tx_id: int | None,
        coin: str,
        send_wallet: str | None,
        receive_wallet: str | None,
        send_amount: float | None,
        receive_amount: float | None,
        fee_amount: float | None,
    ) -> TransferFinding:
        return TransferFinding(
            finding_id=str(uuid.uuid4()),
            severity=severity,
            category=category,
            description=description,
            send_tx_id=send_tx_id,
            receive_tx_id=receive_tx_id,
            coin=coin,
            send_wallet=send_wallet,
            receive_wallet=receive_wallet,
            send_amount=send_amount,
            receive_amount=receive_amount,
            fee_amount=fee_amount,
        )
