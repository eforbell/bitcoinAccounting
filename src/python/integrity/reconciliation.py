"""Ledger reconciliation engine for treasury integrity.

Computes expected vs observed balances by coin and wallet over a selected
date range, producing deterministic snapshots with timestamped metadata.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..db.backend import DatabaseBackend

# Tolerance for floating-point balance comparisons
DEFAULT_TOLERANCE: float = 1e-8


@dataclass
class CoinWalletBalance:
    """Balance record for a single (coin, wallet) pair.

    Attributes:
        coin: Currency code (e.g., 'BTC').
        wallet: Wallet/exchange name.
        net_buy: Sum of all buy amounts for this coin in this wallet.
        net_sell: Sum of all sell amounts for this coin in this wallet.
        balance: net_buy minus net_sell.
        is_negative: True when balance is below zero, indicating an error.
    """

    coin: str
    wallet: str
    net_buy: float
    net_sell: float
    balance: float
    is_negative: bool


@dataclass
class CoinSummary:
    """Cross-check summary for a single coin across all wallets.

    Compares the sum of per-wallet balances against the independently
    computed aggregate ledger total.  A non-zero delta indicates that
    some transactions lack wallet attribution or have been miscategorised.

    Attributes:
        coin: Currency code.
        wallet_sum: Sum of per-wallet balance values for this coin.
        ledger_total: Direct aggregate balance from the full ledger.
        delta: wallet_sum minus ledger_total.
        is_reconciled: True when |delta| <= tolerance.
    """

    coin: str
    wallet_sum: float
    ledger_total: float
    delta: float
    is_reconciled: bool


@dataclass
class ReconciliationResult:
    """Full reconciliation result for a single run.

    Attributes:
        coin_filter: Coin filter applied, or None for all coins.
        wallet_filter: Wallet filter applied, or None for all wallets.
        start_date: Inclusive lower bound of the date range, or None.
        end_date: Inclusive upper bound of the date range, or None.
        wallet_balances: Per-(coin, wallet) balance records.
        coin_summaries: Per-coin cross-check summaries.
        total_coins_checked: Number of distinct coins evaluated.
        total_wallets_checked: Number of distinct wallets evaluated.
        reconciled_count: Number of coins that passed the cross-check.
        discrepancy_count: Number of coins with a non-zero delta.
        negative_balance_count: Number of (coin, wallet) pairs with
            balance < 0.
        is_clean: True when discrepancy_count == 0 and
            negative_balance_count == 0.
    """

    coin_filter: str | None
    wallet_filter: str | None
    start_date: str | None
    end_date: str | None
    wallet_balances: list[CoinWalletBalance] = field(default_factory=list)
    coin_summaries: list[CoinSummary] = field(default_factory=list)
    total_coins_checked: int = 0
    total_wallets_checked: int = 0
    reconciled_count: int = 0
    discrepancy_count: int = 0
    negative_balance_count: int = 0
    is_clean: bool = True


@dataclass
class ReconciliationSnapshot:
    """Immutable timestamped snapshot wrapping a ReconciliationResult.

    Attributes:
        run_id: Unique identifier for this reconciliation run (UUID4).
        timestamp: ISO 8601 timestamp of when the snapshot was taken.
        result: The underlying reconciliation result.
    """

    run_id: str
    timestamp: str
    result: ReconciliationResult


class ReconciliationEngine:
    """Compute expected vs observed balances for treasury integrity.

    Each call to :meth:`run` produces a :class:`ReconciliationSnapshot`
    with a fresh run_id and timestamp, ensuring snapshots are individually
    identifiable for trend tracking.

    Args:
        backend: Database backend used for all queries.
        tolerance: Maximum absolute delta considered reconciled.
            Defaults to :data:`DEFAULT_TOLERANCE`.
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        tolerance: float = DEFAULT_TOLERANCE,
    ) -> None:
        self._backend = backend
        self._tolerance = tolerance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        coin: str | None = None,
        wallet: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> ReconciliationSnapshot:
        """Run a full reconciliation and return a timestamped snapshot.

        Args:
            coin: Restrict reconciliation to this coin. None = all coins.
            wallet: Restrict reconciliation to this wallet. None = all.
            start_date: Inclusive start date (``YYYY-MM-DD``). None = no
                lower bound.
            end_date: Inclusive end date (``YYYY-MM-DD``). None = no
                upper bound.

        Returns:
            :class:`ReconciliationSnapshot` with a unique run_id and the
            full reconciliation result.
        """
        exclusive_end = self._exclusive_end(end_date)

        coins = self._discover_coins(coin, wallet, start_date, exclusive_end)
        wallets = self._discover_wallets(coin, wallet, start_date, exclusive_end)

        wallet_balances = self._compute_wallet_balances(
            coins, wallet, start_date, exclusive_end
        )
        coin_summaries = self._compute_coin_summaries(
            coins, wallet_balances, wallet, start_date, exclusive_end
        )

        negative_count = sum(1 for b in wallet_balances if b.is_negative)
        discrepancy_count = sum(1 for s in coin_summaries if not s.is_reconciled)
        reconciled_count = len(coin_summaries) - discrepancy_count

        result = ReconciliationResult(
            coin_filter=coin,
            wallet_filter=wallet,
            start_date=start_date,
            end_date=end_date,
            wallet_balances=wallet_balances,
            coin_summaries=coin_summaries,
            total_coins_checked=len(coins),
            total_wallets_checked=len(wallets),
            reconciled_count=reconciled_count,
            discrepancy_count=discrepancy_count,
            negative_balance_count=negative_count,
            is_clean=(discrepancy_count == 0 and negative_count == 0),
        )

        return ReconciliationSnapshot(
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

    def _discover_coins(
        self,
        coin_filter: str | None,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[str]:
        """Return sorted list of distinct coins present in the ledger."""
        if coin_filter is not None:
            return [coin_filter]

        clauses, params = self._base_clauses(None, wallet_filter, start_date, exclusive_end)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        # Named params can safely appear in both sides of the UNION
        query = f"""
            SELECT DISTINCT coin FROM (
                SELECT buy_curr AS coin FROM ledger {where}
                UNION
                SELECT sell_curr AS coin FROM ledger {where}
            ) sub
            WHERE coin IS NOT NULL AND coin != ''
            ORDER BY coin
        """
        rows = self._backend.execute(query, params or None)
        return [r["coin"] for r in rows]

    def _discover_wallets(
        self,
        coin_filter: str | None,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[str]:
        """Return sorted list of distinct wallets present in the ledger."""
        if wallet_filter is not None:
            return [wallet_filter]

        clauses, params = self._base_clauses(coin_filter, None, start_date, exclusive_end)
        # Include exchange non-null check inside the single WHERE block
        clauses.append("exchange IS NOT NULL")
        clauses.append("exchange != ''")
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        query = f"""
            SELECT DISTINCT exchange AS wallet FROM ledger {where}
            ORDER BY exchange
        """
        rows = self._backend.execute(query, params or None)
        return [r["wallet"] for r in rows]

    def _compute_wallet_balances(
        self,
        coins: list[str],
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[CoinWalletBalance]:
        """Compute per-(coin, wallet) buy/sell/balance breakdown."""
        results: list[CoinWalletBalance] = []

        for coin in coins:
            clauses, params = self._base_clauses(
                coin, wallet_filter, start_date, exclusive_end
            )
            # Exclude rows with no wallet attribution so that unassigned
            # transactions are not silently absorbed into the wallet sum.
            # Without this filter, wallet_sum == ledger_total even when
            # transactions lack an exchange value, suppressing the discrepancy.
            clauses.append("exchange IS NOT NULL")
            clauses.append("exchange != ''")
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

            query = f"""
                SELECT
                    exchange AS wallet,
                    COALESCE(SUM(CASE WHEN buy_curr = :_coin THEN buy ELSE 0 END), 0.0)
                        AS net_buy,
                    COALESCE(SUM(CASE WHEN sell_curr = :_coin THEN sell ELSE 0 END), 0.0)
                        AS net_sell
                FROM ledger
                {where}
                GROUP BY exchange
                ORDER BY exchange
            """
            params["_coin"] = coin
            rows = self._backend.execute(query, params)

            for row in rows:
                wallet_name = row["wallet"] or ""
                net_buy = float(row["net_buy"])
                net_sell = float(row["net_sell"])
                balance = net_buy - net_sell
                results.append(
                    CoinWalletBalance(
                        coin=coin,
                        wallet=wallet_name,
                        net_buy=net_buy,
                        net_sell=net_sell,
                        balance=balance,
                        is_negative=balance < -self._tolerance,
                    )
                )

        return results

    def _compute_coin_summaries(
        self,
        coins: list[str],
        wallet_balances: list[CoinWalletBalance],
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> list[CoinSummary]:
        """Compute per-coin cross-check between wallet sums and ledger totals."""
        summaries: list[CoinSummary] = []

        for coin in coins:
            wallet_sum = sum(
                b.balance for b in wallet_balances if b.coin == coin
            )
            ledger_total = self._ledger_total_for_coin(
                coin, wallet_filter, start_date, exclusive_end
            )
            delta = wallet_sum - ledger_total
            summaries.append(
                CoinSummary(
                    coin=coin,
                    wallet_sum=wallet_sum,
                    ledger_total=ledger_total,
                    delta=delta,
                    is_reconciled=abs(delta) <= self._tolerance,
                )
            )

        return summaries

    def _ledger_total_for_coin(
        self,
        coin: str,
        wallet_filter: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> float:
        """Compute overall net balance for a coin via aggregate query."""
        clauses, params = self._base_clauses(
            coin, wallet_filter, start_date, exclusive_end
        )
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params["_coin"] = coin

        query = f"""
            SELECT
                COALESCE(SUM(CASE WHEN buy_curr = :_coin THEN buy ELSE 0 END), 0.0)
                - COALESCE(SUM(CASE WHEN sell_curr = :_coin THEN sell ELSE 0 END), 0.0)
                AS total
            FROM ledger
            {where}
        """
        result = self._backend.execute_scalar(query, params)
        return float(result) if result is not None else 0.0

    @staticmethod
    def _base_clauses(
        coin: str | None,
        wallet: str | None,
        start_date: str | None,
        exclusive_end: str | None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Build shared WHERE clauses and params for all ledger queries."""
        clauses: list[str] = ["(deleted = 0 OR deleted IS NULL)"]
        params: dict[str, Any] = {}

        if coin is not None:
            clauses.append("(buy_curr = :coin OR sell_curr = :coin)")
            params["coin"] = coin

        if wallet is not None:
            clauses.append("exchange = :wallet")
            params["wallet"] = wallet

        if start_date is not None:
            clauses.append("createddate >= :start_date")
            params["start_date"] = start_date

        if exclusive_end is not None:
            clauses.append("createddate < :exclusive_end")
            params["exclusive_end"] = exclusive_end

        return clauses, params
