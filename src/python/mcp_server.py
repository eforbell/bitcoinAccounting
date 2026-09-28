"""MCP stdio server — read-only Bitcoin treasury tools (Feature-17).

Exposes 12 read-only tools over the MCP stdio transport so AI clients
(primarily Claude Desktop) can query treasury details, capital gains,
tax summaries, integrity health, and wallet verification status directly.

Entry point: ``bitcoin-mcp`` (see pyproject.toml).

No write operations are exposed via MCP — all mutations stay in the TUI.
The synchronous DB layer is wrapped in ``asyncio.to_thread()`` per call,
with open/close per tool invocation (matches the pattern in integrity/cli.py).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from mcp.server import MCPServer

mcp = MCPServer(
    "bitcoin-accounting",
    instructions="Read-only Bitcoin treasury tools for financial planning and tax optimization.",
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_accounts():
    """Create a fresh BitcoinAccounts instance (opens a DB connection)."""
    from bitcoinAccounts import BitcoinAccounts

    return BitcoinAccounts()


def _open_backend():
    """Open a fresh database backend (reads DB_BACKEND env var)."""
    from db import get_backend

    return get_backend()


def _serialize(obj: Any) -> Any:
    """Recursively convert non-JSON-serializable types to JSON-safe equivalents.

    - ``datetime`` / ``date``  → ISO-8601 string via ``.isoformat()``
    - ``Decimal`` and other float-like types → ``float``
    - ``dict`` / ``list`` → recursed element-by-element
    - All other types → returned as-is
    """
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if obj is not None and hasattr(obj, "__float__") and not isinstance(obj, (int, float, bool)):
        # Catches Decimal, numpy scalars, etc.
        return float(obj)
    return obj


def main() -> None:
    """Entry point for the ``bitcoin-mcp`` CLI command.

    Loads ``.env`` from the current working directory (with override=False
    so already-set environment variables take precedence), configures file
    logging to ``~/.bitcoin-mcp.log``, then starts the MCP server over stdio.
    """
    import logging
    from pathlib import Path

    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

    log_path = Path.home() / ".bitcoin-mcp.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("bitcoin-mcp").info("Starting bitcoin-mcp server (log: %s)", log_path)

    mcp.run(transport="stdio")


# ---------------------------------------------------------------------------
# Group A — Financial Snapshot (MCP-002)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_treasury_summary(coin: str = "BTC") -> dict[str, Any]:
    """Return a high-level treasury snapshot for a coin.

    Includes total balance, average cost basis, wallet counts, and a
    breakdown of balance by custody type (exchange vs self-custody vs
    hardware wallet, etc.).

    Args:
        coin: Cryptocurrency symbol (default ``"BTC"``).

    Returns:
        dict with keys:
            - ``coin`` (str)
            - ``total_balance`` (float)
            - ``avg_cost_basis_usd`` (float | None)
            - ``wallet_count`` (int)
            - ``active_wallet_count`` (int)
            - ``custody_breakdown`` (dict[str, float]) — balance per custody type
    """
    import asyncio

    def _run() -> dict[str, Any]:
        accts = _make_accounts()
        try:
            balance = accts.get_balance(coin)
            basis = accts.get_basis(coin)
            wallets = accts.get_wallets(active_only=False)
            active_wallets = accts.get_wallets(active_only=True)

            # Build custody breakdown: sum balance per custody type
            custody_breakdown: dict[str, float] = {}
            wallet_balances = accts.get_wallet_balance(coin, wallet=None)
            if isinstance(wallet_balances, dict):
                for wallet_obj in wallets:
                    w_name = wallet_obj.get("wallet_id", "")
                    w_custody = wallet_obj.get("custody", "unknown")
                    w_bal = float(wallet_balances.get(w_name, 0.0))
                    custody_breakdown[w_custody] = custody_breakdown.get(w_custody, 0.0) + w_bal

            return {
                "coin": coin,
                "total_balance": float(balance),
                "avg_cost_basis_usd": float(basis) if basis is not None else None,
                "wallet_count": len(wallets),
                "active_wallet_count": len(active_wallets),
                "custody_breakdown": {k: round(v, 8) for k, v in custody_breakdown.items()},
            }
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_treasury_summary failed: {exc}") from exc


@mcp.tool()
async def get_wallet_balances(coin: str = "BTC") -> list[dict[str, Any]]:
    """Return per-wallet balances for a coin (zero-balance wallets omitted).

    Args:
        coin: Cryptocurrency symbol (default ``"BTC"``).

    Returns:
        List of wallet dicts, each with:
            - ``name`` (str)
            - ``balance`` (float)
            - ``custody_type`` (str)
            - ``wallet_type`` (str)
            - ``active`` (bool)
    """
    import asyncio

    def _run() -> list[dict[str, Any]]:
        accts = _make_accounts()
        try:
            wallets = accts.get_wallets(active_only=False)
            all_balances = accts.get_wallet_balance(coin, wallet=None)
            if not isinstance(all_balances, dict):
                all_balances = {}

            result = []
            for w in wallets:
                w_id = w.get("wallet_id", "")
                bal = float(all_balances.get(w_id, 0.0))
                if abs(bal) < 1e-12:
                    continue
                result.append(
                    {
                        "name": w_id,
                        "balance": round(bal, 8),
                        "custody_type": w.get("custody", "unknown"),
                        "wallet_type": w.get("type", "unknown"),
                        "active": bool(w.get("active", True)),
                    }
                )
            return result
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_wallet_balances failed: {exc}") from exc


@mcp.tool()
async def get_transactions(
    coin: str | None = None,
    wallet: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return transactions from the ledger with optional filters.

    Args:
        coin: Optional coin filter (e.g. ``"BTC"``).
        wallet: Optional wallet/exchange name filter.
        start_date: Optional inclusive start date ``YYYY-MM-DD``.
        end_date: Optional inclusive end date ``YYYY-MM-DD``.
        limit: Maximum rows to return (default 100, capped at 500).

    Returns:
        dict with keys:
            - ``columns`` (list[str]) — column names
            - ``transactions`` (list[dict]) — rows as dicts with ISO-serialized dates
            - ``total_returned`` (int)
    """
    import asyncio

    effective_limit = min(max(1, limit), 500)

    def _run() -> dict[str, Any]:
        accts = _make_accounts()
        try:
            columns, rows = accts.get_transactions(
                coin=coin,
                wallet=wallet,
                start_date=start_date,
                end_date=end_date,
            )
            sliced = list(rows)[:effective_limit]
            serialized = [_serialize(dict(row) if not isinstance(row, dict) else row) for row in sliced]
            return {
                "columns": list(columns),
                "transactions": serialized,
                "total_returned": len(serialized),
            }
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_transactions failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Group B — Tax & Capital Gains (MCP-003)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_purchase_lots(
    coin: str = "BTC",
    wallet: str | None = None,
) -> list[dict[str, Any]]:
    """Return all open purchase lots with unrealized P&L at today's price.

    This is the primary tool for tax-optimal selling advice — each lot shows
    its holding term (Short/Long), days held, unit cost, and unrealized gain
    or loss at the current market price.

    Args:
        coin: Cryptocurrency symbol (default ``"BTC"``).
        wallet: Optional wallet filter for per-wallet FIFO (2025+ compliance).

    Returns:
        List of lot dicts, each with:
            - ``acquire_date`` (str | None) — ISO-8601 date
            - ``quantity`` (float)
            - ``unit_cost`` (float) — cost basis per unit in USD
            - ``total_cost`` (float) — total cost basis
            - ``wallet`` (str)
            - ``current_price`` (float | None) — today's price per unit in USD
            - ``unrealized_pnl`` (float | None) — ``(current_price - unit_cost) * quantity``
            - ``holding_days`` (int)
            - ``term`` (str) — ``"Short"`` (< 365 days) or ``"Long"`` (≥ 365 days)
    """
    import asyncio
    from datetime import datetime as dt

    def _run() -> list[dict[str, Any]]:
        accts = _make_accounts()
        try:
            raw_lots = accts.capital_gains_calc.get_purchase_lots(coin, wallet)
            current_price = accts.price_lookup.get_price(coin, "USD")

            result = []
            today = dt.now()
            for lot in raw_lots:
                acquire_date, quantity, unit_cost, total_cost, exchange = lot

                # Normalise date
                if isinstance(acquire_date, str):
                    acquire_date = dt.fromisoformat(acquire_date.replace("Z", "+00:00"))

                # Strip tzinfo so subtraction never mixes aware/naive
                if acquire_date is not None and acquire_date.tzinfo is not None:
                    acquire_date = acquire_date.replace(tzinfo=None)

                quantity_f = float(quantity)
                unit_cost_f = float(unit_cost) if unit_cost is not None else 0.0
                total_cost_f = float(total_cost) if total_cost is not None else 0.0

                holding_days = (today - acquire_date).days if acquire_date else 0
                term = "Long" if holding_days >= 365 else "Short"

                if current_price is not None:
                    unrealized_pnl = round((current_price - unit_cost_f) * quantity_f, 2)
                else:
                    unrealized_pnl = None

                result.append(
                    {
                        "acquire_date": acquire_date.isoformat() if acquire_date else None,
                        "quantity": quantity_f,
                        "unit_cost": unit_cost_f,
                        "total_cost": total_cost_f,
                        "wallet": str(exchange) if exchange else None,
                        "current_price": float(current_price) if current_price is not None else None,
                        "unrealized_pnl": unrealized_pnl,
                        "holding_days": holding_days,
                        "term": term,
                    }
                )
            return result
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_purchase_lots failed: {exc}") from exc


@mcp.tool()
async def forecast_capital_gains(
    quantity: float,
    sale_price_usd: float | None = None,
    coin: str = "BTC",
    wallet: str | None = None,
) -> dict[str, Any]:
    """Forecast capital gains for a hypothetical sale without recording it.

    Uses FIFO cost basis to match the requested quantity against open purchase
    lots, producing a per-lot breakdown and summary statistics.

    Args:
        quantity: Amount of ``coin`` to simulate selling (must be > 0).
        sale_price_usd: Hypothetical sale price per unit in USD.
            If ``None``, proceeds are not computed (summary totals will be 0).
        coin: Cryptocurrency symbol (default ``"BTC"``).
        wallet: Optional wallet filter for per-wallet FIFO.

    Returns:
        dict with keys:
            - ``lots`` (list[dict]) — FIFO lots consumed (acquire_date serialized)
            - ``summary`` (dict) — totals including short/long breakdown
    """
    import asyncio

    if quantity <= 0:
        raise ValueError(f"quantity must be > 0, got {quantity}")

    def _run() -> dict[str, Any]:
        accts = _make_accounts()
        try:
            lots, summary = accts.forecast_capital_gains_fifo(
                coin=coin,
                quantity=quantity,
                sale_price_usd=sale_price_usd,
                wallet=wallet,
            )
            return {
                "lots": _serialize(lots),
                "summary": _serialize(summary),
            }
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"forecast_capital_gains failed: {exc}") from exc


@mcp.tool()
async def get_tax_summary(
    tax_year: int,
    coin: str = "BTC",
    wallet: str | None = None,
) -> dict[str, Any]:
    """Return 1099-B data and a gain/loss summary for a tax year.

    Works for **past and current years** — passing the current year returns
    year-to-date realized gains, which is the primary mid-year tax planning
    use case.

    For tax years 2025+, IRS Rev. Proc. 2024-28 requires per-wallet FIFO.
    Calling this tool for 2025+ **without** a ``wallet`` filter raises
    ``ValueError`` — matching the strict policy enforced by the web product.

    Args:
        tax_year: Four-digit tax year (e.g. ``2026`` for current-year YTD).
        coin: Cryptocurrency symbol (default ``"BTC"``).
        wallet: Wallet filter. **Required** for tax years 2025+.

    Returns:
        dict with keys:
            - ``tax_year`` (int)
            - ``coin`` (str)
            - ``wallet`` (str | None)
            - ``form_8949_entries`` (list[dict]) — TaxAct-compatible rows
            - ``worksheet`` (list[dict]) — detailed FIFO calculation breakdown
            - ``entry_count`` (int)
            - ``short_term_count`` (int)
            - ``long_term_count`` (int)
            - ``per_wallet_compliance_required`` (bool) — True for 2025+

    Raises:
        ValueError: If ``tax_year >= 2025`` and ``wallet`` is ``None``.
    """
    import asyncio

    if tax_year >= 2025 and wallet is None:
        raise ValueError(
            "Tax year 2025 and later requires an explicit wallet filter for "
            "wallet-separated FIFO reporting (IRS Rev. Proc. 2024-28)."
        )

    def _run() -> dict[str, Any]:
        accts = _make_accounts()
        try:
            form_entries, worksheet = accts.get_sales_for_1099b(
                coin=coin, tax_year=tax_year, wallet=wallet
            )
            short_count = sum(1 for e in form_entries if e.get("Term") == "Short")
            long_count = sum(1 for e in form_entries if e.get("Term") == "Long")
            return {
                "tax_year": tax_year,
                "coin": coin,
                "wallet": wallet,
                "form_8949_entries": _serialize(form_entries),
                "worksheet": _serialize(worksheet),
                "entry_count": len(form_entries),
                "short_term_count": short_count,
                "long_term_count": long_count,
                "per_wallet_compliance_required": tax_year >= 2025,
            }
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_tax_summary failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Group C — Integrity & Attestation (MCP-004)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_treasury_health() -> dict[str, Any]:
    """Return the two most recent treasury health score snapshots and their delta.

    Reads persisted snapshots from the ``integrity_health_snapshots`` table
    (populated by ``bitcoin-integrity --persist`` or the TUI monitoring screen).
    Returns a graceful fallback when no snapshots exist.

    Returns:
        dict with keys:
            - ``latest`` (dict | None) — most recent snapshot row
            - ``previous`` (dict | None) — second-most-recent snapshot row
            - ``score_delta`` (float | None) — ``latest.overall_score - previous.overall_score``
    """
    import asyncio

    def _run() -> dict[str, Any]:
        backend = _open_backend()
        try:
            from integrity.health_score import TreasuryHealthScorer

            scorer = TreasuryHealthScorer(backend=backend)
            try:
                snaps = scorer.load_snapshots(limit=2)
            except Exception:
                snaps = []

            latest = _serialize(dict(snaps[0])) if len(snaps) >= 1 else None
            previous = _serialize(dict(snaps[1])) if len(snaps) >= 2 else None
            delta: float | None = None
            if latest is not None and previous is not None:
                delta = round(
                    float(latest["overall_score"]) - float(previous["overall_score"]), 4
                )
            return {"latest": latest, "previous": previous, "score_delta": delta}
        finally:
            backend.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_treasury_health failed: {exc}") from exc


@mcp.tool()
async def get_unresolved_findings(
    source: str | None = None,
    severity: str | None = None,
    coin: str | None = None,
    wallet: str | None = None,
) -> list[dict[str, Any]]:
    """Run all integrity checks and return unresolved findings, with optional filters.

    Runs the four integrity checks in-memory (does not persist results).
    Findings from transfer-pair, basis-continuity, and reconciliation checks
    are flattened into a uniform list and filtered by the supplied criteria.

    Args:
        source: Filter to a single check source:
            ``"transfer_integrity"``, ``"basis_continuity"``, or ``"reconciliation"``.
        severity: Filter to ``"critical"`` or ``"warning"``.
        coin: Optional coin filter applied to both the check run and the output list.
        wallet: Optional wallet filter applied to both the check run and the output list.

    Returns:
        List of finding dicts with keys ``source``, ``severity``, ``category``,
        ``coin``, ``wallet``, ``tx_id``, ``description``.
    """
    import asyncio

    def _run() -> list[dict[str, Any]]:
        backend = _open_backend()
        try:
            from attestation.generator import _extract_unresolved
            from integrity.cli import run_integrity_check as _run_check

            report = _run_check(backend=backend, coin=coin, wallet=wallet, persist=False)
            findings = _extract_unresolved(report)

            # Apply post-run filters
            if source:
                findings = [f for f in findings if f.get("source") == source]
            if severity:
                findings = [f for f in findings if f.get("severity") == severity]
            if coin:
                findings = [f for f in findings if f.get("coin") == coin]
            if wallet:
                findings = [f for f in findings if f.get("wallet") == wallet]

            return _serialize(findings)
        finally:
            backend.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_unresolved_findings failed: {exc}") from exc


@mcp.tool()
async def run_integrity_check_tool(
    coin: str | None = None,
    wallet: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """Run all four treasury integrity checks and return a structured summary.

    Does **not** persist the health snapshot (use the TUI or
    ``bitcoin-integrity --persist`` for that).

    Args:
        coin: Optional coin filter (e.g. ``"BTC"``).
        wallet: Optional wallet filter.
        start_date: Inclusive start date ``YYYY-MM-DD``.
        end_date: Inclusive end date ``YYYY-MM-DD``.

    Returns:
        dict with keys:
            - ``overall_score`` (float) — weighted aggregate 0–100
            - ``tier`` (str) — ``"healthy"``, ``"warning"``, or ``"critical"``
            - ``sub_scores`` (dict[str, float]) — per-component scores
            - ``finding_counts`` (dict) — counts of critical/warning findings
              by check source
    """
    import asyncio

    def _run() -> dict[str, Any]:
        backend = _open_backend()
        try:
            from integrity.cli import run_integrity_check as _run_check

            report = _run_check(
                backend=backend,
                coin=coin,
                wallet=wallet,
                start_date=start_date,
                end_date=end_date,
                persist=False,
            )
            h = report.health_snap
            r = h.result
            sub_map = {s.name: s.value for s in r.sub_scores}

            tr = report.transfer_snap.result
            br = report.basis_snap.result
            rr = report.recon_snap.result

            return {
                "overall_score": r.overall_score,
                "tier": r.tier.value,
                "sub_scores": sub_map,
                "finding_counts": {
                    "transfer_critical": sum(
                        1 for f in tr.findings if f.severity.value == "critical"
                    ),
                    "transfer_warning": sum(
                        1 for f in tr.findings if f.severity.value == "warning"
                    ),
                    "basis_issues": br.total_issues,
                    "reconciliation_discrepancies": rr.discrepancy_count,
                    "negative_balances": rr.negative_balance_count,
                },
            }
        finally:
            backend.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"run_integrity_check_tool failed: {exc}") from exc


@mcp.tool()
async def get_attestation_bundle(
    year: int,
    month: int,
    coin: str | None = None,
    wallet: str | None = None,
) -> dict[str, Any]:
    """Generate and return a month-end attestation bundle as a parsed dict.

    Runs all four integrity checks scoped to the given month and packages
    results with a deterministic run ID for audit traceability.

    Args:
        year: Four-digit year (e.g. ``2026``).
        month: Month number 1–12.
        coin: Optional coin filter.
        wallet: Optional wallet filter.

    Returns:
        Parsed attestation bundle dict (see ``AttestationGenerator.export_bundle_json``
        for the full schema).

    Raises:
        ValueError: If ``month`` is not in the range 1–12.
    """
    import asyncio
    import json

    if not (1 <= month <= 12):
        raise ValueError(f"month must be between 1 and 12, got {month}")

    def _run() -> dict[str, Any]:
        backend = _open_backend()
        try:
            from attestation.generator import AttestationGenerator

            gen = AttestationGenerator(backend)
            bundle = gen.generate(year=year, month=month, coin=coin, wallet=wallet, persist=False)
            return json.loads(gen.export_bundle_json(bundle))
        finally:
            backend.close()

    try:
        return await asyncio.to_thread(_run)
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"get_attestation_bundle failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Group D — Wallet Verification (MCP-005)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_wallet_verification_status(
    wallet_id: str,
) -> dict[str, Any]:
    """Return the on-chain verification status for a single wallet.

    Shows whether this wallet's balance has been verified against the
    Bitcoin blockchain, including eligibility, latest verification result,
    and any drift between the ledger and on-chain balances.

    Only self-custodied and multisig wallets are eligible for descriptor-based
    blockchain verification. Exchange/custodial wallets are ineligible.

    Args:
        wallet_id: The wallet identifier (e.g. ``"Coldcard"``, ``"Sparrow"``).

    Returns:
        dict with keys:
            - ``wallet_id`` (str)
            - ``eligible`` (bool) — whether this wallet supports verification
            - ``eligibility_reason`` (str | None) — why ineligible, if applicable
            - ``latest_verification`` (dict | None) — most recent verification run:
                - ``status`` (str) — ``"verified"``, ``"drift_detected"``,
                  ``"failed"``, ``"partial"``, ``"not_meaningful"``, ``"stale"``
                - ``coverage`` (str) — ``"full"`` or ``"partial"``
                - ``is_recent`` (bool) — within recency window
                - ``ledger_balance`` (float | None) — balance per ledger
                - ``verified_balance`` (float | None) — balance per blockchain
                - ``drift_btc`` (float | None) — difference (chain − ledger)
                - ``chain_height`` (int | None) — block height at verification
                - ``verified_at`` (str) — ISO-8601 timestamp
                - ``stale_after`` (str) — ISO-8601 recency expiry
            - ``run_count`` (int) — total historical verification runs
    """
    import asyncio

    def _run() -> dict[str, Any]:
        accts = _make_accounts()
        try:
            from web.services.wallet_verification import (
                get_latest_wallet_verification,
                get_wallet_verification_eligibility,
                list_wallet_verification_runs,
            )

            eligibility = get_wallet_verification_eligibility(accts, wallet_id)
            latest = get_latest_wallet_verification(accts.backend, wallet_id)
            runs = list_wallet_verification_runs(accts.backend, wallet_id, limit=1000)

            latest_dict = None
            if latest is not None:
                latest_dict = {
                    "status": latest.status,
                    "coverage": latest.coverage,
                    "is_recent": latest.is_recent,
                    "ledger_balance": latest.ledger_balance,
                    "verified_balance": latest.verified_balance,
                    "drift_btc": latest.drift_btc,
                    "chain_height": latest.chain_height,
                    "verified_at": latest.verified_at.isoformat(),
                    "stale_after": latest.stale_after.isoformat(),
                }

            return {
                "wallet_id": wallet_id,
                "eligible": eligibility.eligible,
                "eligibility_reason": eligibility.reason,
                "latest_verification": latest_dict,
                "run_count": len(runs),
            }
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_wallet_verification_status failed: {exc}") from exc


@mcp.tool()
async def get_portfolio_verification_posture(
    coin: str = "BTC",
) -> dict[str, Any]:
    """Return the aggregate blockchain verification posture for the portfolio.

    Evaluates all self-custodied and multisig wallets with a positive balance
    to produce a portfolio-level verification verdict. This is the primary
    tool for answering "has my portfolio been verified on-chain?"

    The portfolio is ``"verified"`` only when **every** eligible wallet has a
    recent, full-coverage, clean verification with no drift.

    Args:
        coin: Cryptocurrency symbol (default ``"BTC"``).

    Returns:
        dict with keys:
            - ``status`` (str) — ``"verified"``, ``"partial_coverage"``,
              ``"stale"``, ``"drift_detected"``, ``"failed"``,
              ``"not_fully_verified"``, ``"ineligible"``
            - ``eligible_wallet_count`` (int)
            - ``verified_wallet_count`` (int) — recent + full + clean
            - ``partial_wallet_count`` (int)
            - ``stale_wallet_count`` (int) — verified but outside recency window
            - ``failed_wallet_count`` (int)
            - ``drift_wallet_count`` (int) — balance mismatch detected
            - ``recency_window_days`` (int)
            - ``wallets`` (list[dict]) — per-wallet summary with:
                - ``wallet_id``, ``balance``, ``custody_type``, ``eligible``,
                  ``verification_status``, ``verification_coverage``,
                  ``verification_is_recent``
    """
    import asyncio

    def _run() -> dict[str, Any]:
        accts = _make_accounts()
        try:
            from web.services.wallet_verification import (
                build_portfolio_verification_posture,
                get_latest_wallet_verification,
                get_wallet_verification_eligibility,
            )

            wallets = accts.get_wallets(active_only=False)
            all_balances = accts.get_wallet_balance(coin, wallet=None)
            if not isinstance(all_balances, dict):
                all_balances = {}

            eligible_ids: list[str] = []
            wallet_details: list[dict[str, Any]] = []

            for w in wallets:
                wallet_id = w.get("wallet_id") or w.get("name") or w.get("wallet_name", "")
                bal = float(all_balances.get(wallet_id, 0.0))
                active = bool(w.get("active", True))
                custody = w.get("custody_type") or w.get("custody", "unknown")

                eligibility = get_wallet_verification_eligibility(accts, wallet_id)
                latest = get_latest_wallet_verification(accts.backend, wallet_id)

                if active and bal > 0 and eligibility.eligible:
                    eligible_ids.append(wallet_id)

                if abs(bal) < 1e-12:
                    continue

                wallet_details.append({
                    "wallet_id": wallet_id,
                    "balance": round(bal, 8),
                    "custody_type": custody,
                    "eligible": eligibility.eligible,
                    "verification_status": latest.status if latest else None,
                    "verification_coverage": latest.coverage if latest else None,
                    "verification_is_recent": latest.is_recent if latest else None,
                })

            posture = build_portfolio_verification_posture(
                accts.backend,
                eligible_wallet_ids=eligible_ids,
            )

            return {
                "status": posture.status,
                "eligible_wallet_count": posture.eligible_wallet_count,
                "verified_wallet_count": posture.verified_wallet_count,
                "partial_wallet_count": posture.partial_wallet_count,
                "stale_wallet_count": posture.stale_wallet_count,
                "failed_wallet_count": posture.failed_wallet_count,
                "drift_wallet_count": posture.drift_wallet_count,
                "recency_window_days": posture.recency_window_days,
                "wallets": wallet_details,
            }
        finally:
            accts.close()

    try:
        return await asyncio.to_thread(_run)
    except Exception as exc:
        raise RuntimeError(f"get_portfolio_verification_posture failed: {exc}") from exc


if __name__ == "__main__":
    main()
