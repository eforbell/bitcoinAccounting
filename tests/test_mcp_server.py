"""Tests for the MCP stdio server (Feature-17).

Organised into four test classes mirroring the story breakdown:

    TestScaffold        — MCP-001: helpers and infrastructure
    TestFinancialSnapshot — MCP-002: treasury summary, wallet balances, transactions
    TestTaxTools        — MCP-003: purchase lots, forecast, tax summary
    TestIntegrityTools  — MCP-004: health, findings, integrity check, attestation bundle

Unit tests mock BitcoinAccounts / the backend.
Integration tests use an in-memory SQLite DB via SqliteBackend(":memory:").
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers shared across tests
# ---------------------------------------------------------------------------


def _backend_with_schema():
    """Return an in-memory SqliteBackend with all tables created."""
    from src.python.db.schema import create_tables
    from src.python.db.sqlite import SqliteBackend

    backend = SqliteBackend(":memory:", auto_create_tables=False)
    create_tables(backend)
    return backend


def _insert_tx(
    backend,
    *,
    trans_type: str,
    buy: float | None = None,
    buy_curr: str | None = None,
    sell: float | None = None,
    sell_curr: str | None = None,
    fee: float | None = None,
    fee_curr: str | None = None,
    exchange: str = "TestWallet",
    createddate: str = "2024-06-15",
    deleted: int = 0,
) -> None:
    backend.execute(
        """
        INSERT INTO ledger
            (trans_type, buy, buy_curr, sell, sell_curr, fee, fee_curr,
             exchange, createddate, deleted)
        VALUES
            (:trans_type, :buy, :buy_curr, :sell, :sell_curr, :fee, :fee_curr,
             :exchange, :createddate, :deleted)
        """,
        {
            "trans_type": trans_type,
            "buy": buy,
            "buy_curr": buy_curr,
            "sell": sell,
            "sell_curr": sell_curr,
            "fee": fee,
            "fee_curr": fee_curr,
            "exchange": exchange,
            "createddate": createddate,
            "deleted": deleted,
        },
    )
    backend.commit()


# ---------------------------------------------------------------------------
# TestScaffold — MCP-001
# ---------------------------------------------------------------------------


class TestScaffold:
    """Server scaffold and helpers."""

    def test_fastmcp_instance_name(self):
        from src.python.mcp_server import mcp

        assert mcp.name == "bitcoin-accounting"

    def test_serialize_datetime(self):
        from src.python.mcp_server import _serialize

        assert _serialize(datetime(2024, 3, 15, 10, 30, 0)) == "2024-03-15T10:30:00"

    def test_serialize_date(self):
        from src.python.mcp_server import _serialize

        assert _serialize(date(2024, 3, 15)) == "2024-03-15"

    def test_serialize_decimal(self):
        from src.python.mcp_server import _serialize

        assert _serialize(Decimal("98765.12")) == pytest.approx(98765.12)

    def test_serialize_none(self):
        from src.python.mcp_server import _serialize

        assert _serialize(None) is None

    def test_serialize_primitives(self):
        from src.python.mcp_server import _serialize

        assert _serialize(42) == 42
        assert _serialize(3.14) == pytest.approx(3.14)
        assert _serialize("hello") == "hello"
        assert _serialize(True) is True

    def test_serialize_nested_dict(self):
        from src.python.mcp_server import _serialize

        obj = {"dt": datetime(2024, 1, 1), "val": Decimal("1.5"), "inner": {"d": date(2025, 6, 1)}}
        result = _serialize(obj)
        assert result == {"dt": "2024-01-01T00:00:00", "val": 1.5, "inner": {"d": "2025-06-01"}}

    def test_serialize_list(self):
        from src.python.mcp_server import _serialize

        result = _serialize([datetime(2024, 1, 1), Decimal("2.0"), None, "x"])
        assert result == ["2024-01-01T00:00:00", 2.0, None, "x"]

    def test_serialize_mixed_nested(self):
        from src.python.mcp_server import _serialize

        obj = [{"date": date(2024, 12, 31), "amount": Decimal("0.005")}, None]
        result = _serialize(obj)
        assert result[0]["date"] == "2024-12-31"
        assert result[0]["amount"] == pytest.approx(0.005)
        assert result[1] is None

    def test_main_is_callable(self):
        from src.python.mcp_server import main

        assert callable(main)

    def test_twelve_tools_registered(self):
        """All 12 tools must be registered on the FastMCP instance."""
        from src.python.mcp_server import mcp

        import asyncio
        tools = asyncio.run(mcp.list_tools())
        tool_names = {t.name for t in tools}
        expected = {
            "get_treasury_summary",
            "get_wallet_balances",
            "get_transactions",
            "get_purchase_lots",
            "forecast_capital_gains",
            "get_tax_summary",
            "get_treasury_health",
            "get_unresolved_findings",
            "run_integrity_check_tool",
            "get_attestation_bundle",
            "get_wallet_verification_status",
            "get_portfolio_verification_posture",
        }
        assert expected == tool_names


# ---------------------------------------------------------------------------
# TestFinancialSnapshot — MCP-002
# ---------------------------------------------------------------------------


class TestFinancialSnapshot:
    """get_treasury_summary, get_wallet_balances, get_transactions."""

    # ------------------------------------------------------------------
    # get_treasury_summary
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_treasury_summary_shape(self):
        mock_accts = MagicMock()
        mock_accts.get_balance.return_value = 1.5
        mock_accts.get_basis.return_value = 40000.0
        mock_accts.get_wallets.side_effect = [
            # active_only=False
            [{"wallet_id": "Strike", "type": "exchange", "custody": "custodial", "active": True},
             {"wallet_id": "Coldcard", "type": "hardware", "custody": "self-custodied", "active": True}],
            # active_only=True
            [{"wallet_id": "Strike", "type": "exchange", "custody": "custodial", "active": True},
             {"wallet_id": "Coldcard", "type": "hardware", "custody": "self-custodied", "active": True}],
        ]
        mock_accts.get_wallet_balance.return_value = {"Strike": 0.5, "Coldcard": 1.0}

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_treasury_summary

            result = await get_treasury_summary(coin="BTC")

        assert result["coin"] == "BTC"
        assert result["total_balance"] == pytest.approx(1.5)
        assert result["avg_cost_basis_usd"] == pytest.approx(40000.0)
        assert result["wallet_count"] == 2
        assert result["active_wallet_count"] == 2
        assert "custodial" in result["custody_breakdown"]
        assert "self-custodied" in result["custody_breakdown"]
        assert result["custody_breakdown"]["custodial"] == pytest.approx(0.5)
        assert result["custody_breakdown"]["self-custodied"] == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_treasury_summary_none_basis(self):
        mock_accts = MagicMock()
        mock_accts.get_balance.return_value = 0.0
        mock_accts.get_basis.return_value = None
        mock_accts.get_wallets.return_value = []
        mock_accts.get_wallet_balance.return_value = {}

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_treasury_summary

            result = await get_treasury_summary()

        assert result["avg_cost_basis_usd"] is None
        assert result["wallet_count"] == 0

    @pytest.mark.asyncio
    async def test_treasury_summary_db_error_raises_runtime(self):
        mock_accts = MagicMock()
        mock_accts.get_balance.side_effect = Exception("DB gone")

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_treasury_summary

            with pytest.raises(RuntimeError, match="get_treasury_summary failed"):
                await get_treasury_summary()

    # ------------------------------------------------------------------
    # get_wallet_balances
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_wallet_balances_omits_zero(self):
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = [
            {"wallet_id": "Strike", "type": "exchange", "custody": "custodial", "active": True},
            {"wallet_id": "Empty", "type": "exchange", "custody": "custodial", "active": False},
            {"wallet_id": "Vault", "type": "hardware", "custody": "self-custodied", "active": True},
        ]
        mock_accts.get_wallet_balance.return_value = {"Strike": 0.25, "Empty": 0.0, "Vault": 1.0}

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_wallet_balances

            result = await get_wallet_balances("BTC")

        names = [w["name"] for w in result]
        assert "Empty" not in names
        assert "Strike" in names
        assert "Vault" in names
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_wallet_balances_fields(self):
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = [
            {"wallet_id": "River", "type": "exchange", "custody": "custodial", "active": True},
        ]
        mock_accts.get_wallet_balance.return_value = {"River": 0.1}

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_wallet_balances

            result = await get_wallet_balances()

        assert len(result) == 1
        w = result[0]
        assert set(w.keys()) >= {"name", "balance", "custody_type", "wallet_type", "active"}
        assert w["balance"] == pytest.approx(0.1)
        assert w["active"] is True

    # ------------------------------------------------------------------
    # get_transactions
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_transactions_shape(self):
        mock_accts = MagicMock()
        rows = [
            {"id": 1, "trans_type": "Trade", "createddate": datetime(2024, 6, 1), "buy": 0.1},
            {"id": 2, "trans_type": "Deposit", "createddate": datetime(2024, 7, 1), "buy": 0.05},
        ]
        mock_accts.get_transactions.return_value = (["id", "trans_type", "createddate", "buy"], rows)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_transactions

            result = await get_transactions(coin="BTC", limit=50)

        assert "columns" in result
        assert "transactions" in result
        assert "total_returned" in result
        assert result["total_returned"] == 2
        # datetime should be serialized
        assert result["transactions"][0]["createddate"] == "2024-06-01T00:00:00"

    @pytest.mark.asyncio
    async def test_transactions_limit_capped_at_500(self):
        mock_accts = MagicMock()
        # Return 600 rows; limit should cap at 500
        rows = [{"id": i, "createddate": "2024-01-01"} for i in range(600)]
        mock_accts.get_transactions.return_value = (["id", "createddate"], rows)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_transactions

            result = await get_transactions(limit=9999)

        assert result["total_returned"] == 500

    @pytest.mark.asyncio
    async def test_transactions_limit_respected(self):
        mock_accts = MagicMock()
        rows = [{"id": i} for i in range(200)]
        mock_accts.get_transactions.return_value = (["id"], rows)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_transactions

            result = await get_transactions(limit=10)

        assert result["total_returned"] == 10

    @pytest.mark.asyncio
    async def test_transactions_db_error(self):
        mock_accts = MagicMock()
        mock_accts.get_transactions.side_effect = Exception("connection reset")

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_transactions

            with pytest.raises(RuntimeError, match="get_transactions failed"):
                await get_transactions()


# ---------------------------------------------------------------------------
# TestTaxTools — MCP-003
# ---------------------------------------------------------------------------


class TestTaxTools:
    """get_purchase_lots, forecast_capital_gains, get_tax_summary."""

    # ------------------------------------------------------------------
    # get_purchase_lots
    # ------------------------------------------------------------------

    def _make_lots_accts(self, lots, current_price):
        """Build a mock BitcoinAccounts for purchase-lot tests."""
        mock_accts = MagicMock()
        mock_accts.capital_gains_calc.get_purchase_lots.return_value = lots
        mock_accts.price_lookup.get_price.return_value = current_price
        return mock_accts

    @pytest.mark.asyncio
    async def test_purchase_lots_shape(self):
        lots = [
            (datetime(2023, 1, 10), 0.5, 20000.0, 10000.0, "Strike"),
            (datetime(2024, 6, 1), 0.25, 60000.0, 15000.0, "River"),
        ]
        mock_accts = self._make_lots_accts(lots, current_price=70000.0)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_purchase_lots

            result = await get_purchase_lots(coin="BTC")

        assert len(result) == 2
        keys = {"acquire_date", "quantity", "unit_cost", "total_cost", "wallet",
                "current_price", "unrealized_pnl", "holding_days", "term"}
        assert keys.issubset(set(result[0].keys()))

    @pytest.mark.asyncio
    async def test_purchase_lots_term_classification(self):
        # One lot > 365 days old (long term), one < 365 days old (short term).
        # Today is ~2026-02-25, so use 2022 for Long and 2026-01 for Short.
        old = datetime(2022, 1, 1)   # long term (~4+ years)
        recent = datetime(2026, 1, 15)  # short term (~40 days ago)
        lots = [
            (old, 0.1, 10000.0, 1000.0, "A"),
            (recent, 0.1, 60000.0, 6000.0, "B"),
        ]
        mock_accts = self._make_lots_accts(lots, 70000.0)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_purchase_lots

            result = await get_purchase_lots()

        # Sort by acquire_date to be deterministic
        result_sorted = sorted(result, key=lambda x: x["acquire_date"])
        assert result_sorted[0]["term"] == "Long"
        assert result_sorted[1]["term"] == "Short"

    @pytest.mark.asyncio
    async def test_purchase_lots_unrealized_pnl(self):
        lots = [(datetime(2023, 1, 1), 1.0, 30000.0, 30000.0, "Vault")]
        mock_accts = self._make_lots_accts(lots, 50000.0)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_purchase_lots

            result = await get_purchase_lots()

        # unrealized_pnl = (50000 - 30000) * 1.0 = 20000
        assert result[0]["unrealized_pnl"] == pytest.approx(20000.0)
        assert result[0]["current_price"] == pytest.approx(50000.0)

    @pytest.mark.asyncio
    async def test_purchase_lots_no_price_graceful(self):
        lots = [(datetime(2023, 6, 1), 0.5, 25000.0, 12500.0, "Vault")]
        mock_accts = self._make_lots_accts(lots, current_price=None)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_purchase_lots

            result = await get_purchase_lots()

        assert result[0]["current_price"] is None
        assert result[0]["unrealized_pnl"] is None

    @pytest.mark.asyncio
    async def test_purchase_lots_timezone_aware_timestamp(self):
        """Lot timestamps with Z suffix must not crash on naive/aware subtraction."""
        lots = [("2024-01-01T00:00:00Z", 0.5, 40000.0, 20000.0, "Vault")]
        mock_accts = self._make_lots_accts(lots, 70000.0)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_purchase_lots

            result = await get_purchase_lots()

        assert len(result) == 1
        assert result[0]["holding_days"] > 0
        assert result[0]["term"] == "Long"

    @pytest.mark.asyncio
    async def test_purchase_lots_acquire_date_serialized(self):
        lots = [(datetime(2024, 3, 15, 10, 0, 0), 0.1, 60000.0, 6000.0, "X")]
        mock_accts = self._make_lots_accts(lots, 70000.0)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_purchase_lots

            result = await get_purchase_lots()

        # acquire_date must be a string (ISO), not a datetime
        assert isinstance(result[0]["acquire_date"], str)
        assert "2024-03-15" in result[0]["acquire_date"]

    # ------------------------------------------------------------------
    # forecast_capital_gains
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_forecast_raises_for_zero_quantity(self):
        from src.python.mcp_server import forecast_capital_gains

        with pytest.raises(ValueError, match="quantity must be > 0"):
            await forecast_capital_gains(quantity=0.0)

    @pytest.mark.asyncio
    async def test_forecast_raises_for_negative_quantity(self):
        from src.python.mcp_server import forecast_capital_gains

        with pytest.raises(ValueError, match="quantity must be > 0"):
            await forecast_capital_gains(quantity=-1.0)

    @pytest.mark.asyncio
    async def test_forecast_shape(self):
        mock_accts = MagicMock()
        lots = [
            {"acquire_date": datetime(2022, 1, 1), "quantity": 0.5,
             "unit_cost": 20000.0, "cost_basis": 10000.0,
             "holding_days": 800, "term": "Long"},
        ]
        summary = {
            "total_quantity": 0.5, "total_cost_basis": 10000.0, "total_proceeds": 35000.0,
            "short_term_count": 0, "short_term_quantity": 0.0,
            "long_term_count": 1, "long_term_quantity": 0.5,
        }
        mock_accts.forecast_capital_gains_fifo.return_value = (lots, summary)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import forecast_capital_gains

            result = await forecast_capital_gains(quantity=0.5, sale_price_usd=70000.0)

        assert "lots" in result
        assert "summary" in result
        assert result["summary"]["long_term_count"] == 1
        # datetime in lots must be serialized
        assert isinstance(result["lots"][0]["acquire_date"], str)

    @pytest.mark.asyncio
    async def test_forecast_passes_args_through(self):
        mock_accts = MagicMock()
        mock_accts.forecast_capital_gains_fifo.return_value = ([], {})

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import forecast_capital_gains

            await forecast_capital_gains(quantity=1.0, sale_price_usd=50000.0,
                                         coin="BTC", wallet="Vault")

        mock_accts.forecast_capital_gains_fifo.assert_called_once_with(
            coin="BTC", quantity=1.0, sale_price_usd=50000.0, wallet="Vault"
        )

    # ------------------------------------------------------------------
    # get_tax_summary
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_tax_summary_shape(self):
        mock_accts = MagicMock()
        entries = [
            {"Description": "0.5 BTC", "Date Acquired": "01/01/2022",
             "Date Sold": "06/15/2024", "Proceeds": "35000.00",
             "Cost Basis": "10000.00", "Term": "Long"},
        ]
        worksheet = [{"Sale Date": "06/15/2024", "Gain/Loss": "25000.00"}]
        mock_accts.get_sales_for_1099b.return_value = (entries, worksheet)

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_tax_summary

            result = await get_tax_summary(tax_year=2024, coin="BTC")

        assert result["tax_year"] == 2024
        assert result["coin"] == "BTC"
        assert result["entry_count"] == 1
        assert result["long_term_count"] == 1
        assert result["short_term_count"] == 0
        assert "form_8949_entries" in result
        assert "worksheet" in result

    @pytest.mark.asyncio
    async def test_tax_summary_per_wallet_compliance_flag(self):
        mock_accts = MagicMock()
        mock_accts.get_sales_for_1099b.return_value = ([], [])

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_tax_summary

            pre_2025 = await get_tax_summary(tax_year=2024)
            # 2025+ requires wallet — pass one
            post_2025 = await get_tax_summary(tax_year=2025, wallet="Vault")
            current = await get_tax_summary(tax_year=2026, wallet="Vault")

        assert pre_2025["per_wallet_compliance_required"] is False
        assert post_2025["per_wallet_compliance_required"] is True
        assert current["per_wallet_compliance_required"] is True

    @pytest.mark.asyncio
    async def test_tax_summary_current_year_works(self):
        """Current (partial) tax year should return without error."""
        mock_accts = MagicMock()
        mock_accts.get_sales_for_1099b.return_value = ([], [])

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_tax_summary

            result = await get_tax_summary(tax_year=2026, wallet="Vault")

        assert result["entry_count"] == 0
        assert result["tax_year"] == 2026

    @pytest.mark.asyncio
    async def test_tax_summary_2025_without_wallet_raises(self):
        """2025+ tax year without wallet must raise ValueError."""
        from src.python.mcp_server import get_tax_summary

        with pytest.raises(ValueError, match="wallet filter"):
            await get_tax_summary(tax_year=2025)

    @pytest.mark.asyncio
    async def test_tax_summary_pre_2025_without_wallet_allowed(self):
        """Pre-2025 tax years still allow global FIFO without wallet."""
        mock_accts = MagicMock()
        mock_accts.get_sales_for_1099b.return_value = ([], [])

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_tax_summary

            result = await get_tax_summary(tax_year=2024)

        assert result["per_wallet_compliance_required"] is False

    @pytest.mark.asyncio
    async def test_tax_summary_wallet_passed_through(self):
        mock_accts = MagicMock()
        mock_accts.get_sales_for_1099b.return_value = ([], [])

        with patch("src.python.mcp_server._make_accounts", return_value=mock_accts):
            from src.python.mcp_server import get_tax_summary

            await get_tax_summary(tax_year=2025, coin="BTC", wallet="Vault")

        mock_accts.get_sales_for_1099b.assert_called_once_with(
            coin="BTC", tax_year=2025, wallet="Vault"
        )


# ---------------------------------------------------------------------------
# TestIntegrityTools — MCP-004
# ---------------------------------------------------------------------------


class TestIntegrityTools:
    """get_treasury_health, get_unresolved_findings, run_integrity_check_tool,
    get_attestation_bundle."""

    # ------------------------------------------------------------------
    # get_treasury_health
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_health_empty_table_returns_nulls(self):
        backend = _backend_with_schema()

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import get_treasury_health

            result = await get_treasury_health()

        assert result["latest"] is None
        assert result["previous"] is None
        assert result["score_delta"] is None

    @pytest.mark.asyncio
    async def test_health_one_snapshot(self):
        backend = _backend_with_schema()
        # Persist one health snapshot via TreasuryHealthScorer
        from src.python.integrity.health_score import TreasuryHealthScorer
        from src.python.integrity.cli import run_integrity_check

        report = run_integrity_check(backend=backend, persist=False)
        scorer = TreasuryHealthScorer(backend=backend)
        snap = scorer.score(report.recon_snap, report.transfer_snap, report.basis_snap)
        scorer.persist(snap)

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import get_treasury_health

            result = await get_treasury_health()

        assert result["latest"] is not None
        assert result["previous"] is None
        assert result["score_delta"] is None
        assert "overall_score" in result["latest"]

    @pytest.mark.asyncio
    async def test_health_two_snapshots_delta(self):
        backend = _backend_with_schema()
        from src.python.integrity.health_score import TreasuryHealthScorer
        from src.python.integrity.cli import run_integrity_check

        scorer = TreasuryHealthScorer(backend=backend)

        # First snapshot
        report1 = run_integrity_check(backend=backend, persist=False)
        snap1 = scorer.score(report1.recon_snap, report1.transfer_snap, report1.basis_snap)
        scorer.persist(snap1)

        # Second snapshot
        report2 = run_integrity_check(backend=backend, persist=False)
        snap2 = scorer.score(report2.recon_snap, report2.transfer_snap, report2.basis_snap)
        scorer.persist(snap2)

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import get_treasury_health

            result = await get_treasury_health()

        assert result["latest"] is not None
        assert result["previous"] is not None
        assert result["score_delta"] is not None
        expected_delta = round(
            float(result["latest"]["overall_score"]) - float(result["previous"]["overall_score"]), 4
        )
        assert result["score_delta"] == pytest.approx(expected_delta)

    # ------------------------------------------------------------------
    # get_unresolved_findings
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_unresolved_findings_empty_db(self):
        backend = _backend_with_schema()

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import get_unresolved_findings

            result = await get_unresolved_findings()

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_unresolved_findings_filter_by_source(self):
        """Source filter reduces the findings list to matching entries only."""
        # Each call closes its backend, so supply a fresh one each time.
        with patch("src.python.mcp_server._open_backend", side_effect=_backend_with_schema):
            from src.python.mcp_server import get_unresolved_findings

            all_findings = await get_unresolved_findings()
            ti_only = await get_unresolved_findings(source="transfer_integrity")
            bc_only = await get_unresolved_findings(source="basis_continuity")

        # Empty ledger → no findings regardless of filter
        assert isinstance(all_findings, list)
        assert isinstance(ti_only, list)
        assert isinstance(bc_only, list)
        # Every returned finding must match the requested source filter
        assert all(f["source"] == "transfer_integrity" for f in ti_only)
        assert all(f["source"] == "basis_continuity" for f in bc_only)

    @pytest.mark.asyncio
    async def test_unresolved_findings_filter_by_severity(self):
        findings = [
            {"source": "transfer_integrity", "severity": "critical", "category": "x",
             "coin": "BTC", "wallet": None, "tx_id": None, "description": "a"},
            {"source": "basis_continuity", "severity": "warning", "category": "y",
             "coin": "BTC", "wallet": None, "tx_id": None, "description": "b"},
        ]
        backend = MagicMock()
        mock_report = MagicMock()

        with (
            patch("src.python.mcp_server._open_backend", return_value=backend),
            patch("src.python.integrity.cli.run_integrity_check", return_value=mock_report),
            patch("src.python.attestation.generator._extract_unresolved", return_value=findings),
        ):
            from src.python.mcp_server import get_unresolved_findings

            critical_only = await get_unresolved_findings(severity="critical")
            warning_only = await get_unresolved_findings(severity="warning")

        assert all(f["severity"] == "critical" for f in critical_only)
        assert all(f["severity"] == "warning" for f in warning_only)

    # ------------------------------------------------------------------
    # run_integrity_check_tool
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_integrity_check_tool_shape(self):
        backend = _backend_with_schema()

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import run_integrity_check_tool

            result = await run_integrity_check_tool()

        assert "overall_score" in result
        assert "tier" in result
        assert "sub_scores" in result
        assert "finding_counts" in result
        assert result["tier"] in ("healthy", "warning", "critical")
        assert set(result["sub_scores"].keys()) == {
            "reconciliation", "transfer_integrity", "basis_continuity"
        }

    @pytest.mark.asyncio
    async def test_integrity_check_tool_does_not_persist(self):
        """run_integrity_check_tool must call run_integrity_check with persist=False."""
        from unittest.mock import call

        backend = _backend_with_schema()
        # Each call to _open_backend returns a fresh backend so the closed-DB
        # issue doesn't occur when we inspect state after the tool has closed it.
        with patch("src.python.mcp_server._open_backend", side_effect=_backend_with_schema):
            from integrity.cli import run_integrity_check as _real_check
            with patch("integrity.cli.run_integrity_check", wraps=_real_check) as mock_check:
                from src.python.mcp_server import run_integrity_check_tool
                await run_integrity_check_tool()

        # Verify persist=False was passed in the call
        assert mock_check.called
        _, kwargs = mock_check.call_args
        assert kwargs.get("persist", False) is False

    @pytest.mark.asyncio
    async def test_integrity_check_tool_finding_counts_keys(self):
        backend = _backend_with_schema()

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import run_integrity_check_tool

            result = await run_integrity_check_tool()

        fc = result["finding_counts"]
        assert "transfer_critical" in fc
        assert "transfer_warning" in fc
        assert "basis_issues" in fc
        assert "reconciliation_discrepancies" in fc
        assert "negative_balances" in fc

    # ------------------------------------------------------------------
    # get_attestation_bundle
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_attestation_bundle_invalid_month_raises(self):
        from src.python.mcp_server import get_attestation_bundle

        with pytest.raises(ValueError, match="month must be between 1 and 12"):
            await get_attestation_bundle(year=2024, month=0)

        with pytest.raises(ValueError, match="month must be between 1 and 12"):
            await get_attestation_bundle(year=2024, month=13)

    @pytest.mark.asyncio
    async def test_attestation_bundle_returns_dict(self):
        backend = _backend_with_schema()

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import get_attestation_bundle

            result = await get_attestation_bundle(year=2024, month=12)

        assert isinstance(result, dict)
        assert "attestation_run_id" in result
        assert "period_label" in result
        assert result["period_label"] == "2024-12"
        assert "unresolved_findings" in result
        assert "integrity" in result

    @pytest.mark.asyncio
    async def test_attestation_bundle_valid_months(self):
        # Each tool call closes its backend, so use side_effect to supply fresh ones.
        with patch("src.python.mcp_server._open_backend", side_effect=_backend_with_schema):
            from src.python.mcp_server import get_attestation_bundle

            # Boundary checks — month 1 and month 12
            r1 = await get_attestation_bundle(year=2025, month=1)
            r12 = await get_attestation_bundle(year=2025, month=12)

        assert r1["period_label"] == "2025-01"
        assert r12["period_label"] == "2025-12"

    @pytest.mark.asyncio
    async def test_attestation_bundle_is_parsed_json_not_string(self):
        """get_attestation_bundle must return a dict, not a JSON string."""
        backend = _backend_with_schema()

        with patch("src.python.mcp_server._open_backend", return_value=backend):
            from src.python.mcp_server import get_attestation_bundle

            result = await get_attestation_bundle(year=2024, month=6)

        assert isinstance(result, dict), "Expected a parsed dict, not a JSON string"
        # Round-trip to JSON must succeed (all values JSON-serializable)
        json.dumps(result)


# ---------------------------------------------------------------------------
# TestWalletVerification — MCP-005
# ---------------------------------------------------------------------------


def _mock_verification_resource(**overrides):
    """Build a mock WalletVerificationResource-like object."""
    defaults = {
        "verification_id": "abc-123",
        "wallet_id": "Coldcard",
        "status": "verified",
        "coverage": "full",
        "descriptor_source_type": "session",
        "recency_window_days": 30,
        "is_recent": True,
        "ledger_balance": 1.5,
        "verified_balance": 1.5,
        "drift_btc": 0.0,
        "chain_height": 880000,
        "branch_count": 2,
        "descriptor_count": 1,
        "highest_scanned_index": 49,
        "highest_used_index": 12,
        "scan_ceiling": 50,
        "gap_limit": None,
        "warning_text": None,
        "error_text": None,
        "verified_at": datetime(2026, 3, 20, 12, 0, 0),
        "stale_after": datetime(2026, 4, 19, 12, 0, 0),
    }
    defaults.update(overrides)
    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


def _mock_eligibility(eligible=True, reason=None):
    mock = MagicMock()
    mock.eligible = eligible
    mock.reason = reason
    return mock


def _mock_posture(**overrides):
    defaults = {
        "status": "verified",
        "recency_window_days": 30,
        "eligible_wallet_count": 2,
        "verified_wallet_count": 2,
        "partial_wallet_count": 0,
        "stale_wallet_count": 0,
        "failed_wallet_count": 0,
        "drift_wallet_count": 0,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


class TestWalletVerification:
    """get_wallet_verification_status and get_portfolio_verification_posture."""

    # ------------------------------------------------------------------
    # get_wallet_verification_status
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_wallet_verification_status_verified(self):
        mock_accts = MagicMock()
        latest = _mock_verification_resource()

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "src.python.mcp_server.get_wallet_verification_status.__wrapped__",
                side_effect=None,
            ) if False else patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(True),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=latest,
            ),
            patch(
                "web.services.wallet_verification.list_wallet_verification_runs",
                return_value=[latest],
            ),
        ):
            from src.python.mcp_server import get_wallet_verification_status

            result = await get_wallet_verification_status(wallet_id="Coldcard")

        assert result["wallet_id"] == "Coldcard"
        assert result["eligible"] is True
        assert result["eligibility_reason"] is None
        assert result["latest_verification"]["status"] == "verified"
        assert result["latest_verification"]["coverage"] == "full"
        assert result["latest_verification"]["is_recent"] is True
        assert result["latest_verification"]["ledger_balance"] == 1.5
        assert result["latest_verification"]["verified_balance"] == 1.5
        assert result["latest_verification"]["drift_btc"] == 0.0
        assert result["latest_verification"]["chain_height"] == 880000
        assert "verified_at" in result["latest_verification"]
        assert "stale_after" in result["latest_verification"]
        assert result["run_count"] == 1

    @pytest.mark.asyncio
    async def test_wallet_verification_status_ineligible_exchange(self):
        mock_accts = MagicMock()

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(
                    False, "Descriptor-based verification is only available for self-custodied or multisig wallets."
                ),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=None,
            ),
            patch(
                "web.services.wallet_verification.list_wallet_verification_runs",
                return_value=[],
            ),
        ):
            from src.python.mcp_server import get_wallet_verification_status

            result = await get_wallet_verification_status(wallet_id="Coinbase")

        assert result["wallet_id"] == "Coinbase"
        assert result["eligible"] is False
        assert "self-custodied" in result["eligibility_reason"]
        assert result["latest_verification"] is None
        assert result["run_count"] == 0

    @pytest.mark.asyncio
    async def test_wallet_verification_status_never_verified(self):
        mock_accts = MagicMock()

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(True),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=None,
            ),
            patch(
                "web.services.wallet_verification.list_wallet_verification_runs",
                return_value=[],
            ),
        ):
            from src.python.mcp_server import get_wallet_verification_status

            result = await get_wallet_verification_status(wallet_id="Sparrow")

        assert result["eligible"] is True
        assert result["latest_verification"] is None
        assert result["run_count"] == 0

    @pytest.mark.asyncio
    async def test_wallet_verification_status_drift_detected(self):
        mock_accts = MagicMock()
        latest = _mock_verification_resource(
            status="drift_detected",
            ledger_balance=2.0,
            verified_balance=1.8,
            drift_btc=-0.2,
        )

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(True),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=latest,
            ),
            patch(
                "web.services.wallet_verification.list_wallet_verification_runs",
                return_value=[latest, _mock_verification_resource()],
            ),
        ):
            from src.python.mcp_server import get_wallet_verification_status

            result = await get_wallet_verification_status(wallet_id="Coldcard")

        assert result["latest_verification"]["status"] == "drift_detected"
        assert result["latest_verification"]["drift_btc"] == pytest.approx(-0.2)
        assert result["run_count"] == 2

    @pytest.mark.asyncio
    async def test_wallet_verification_status_stale(self):
        mock_accts = MagicMock()
        latest = _mock_verification_resource(is_recent=False)

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(True),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=latest,
            ),
            patch(
                "web.services.wallet_verification.list_wallet_verification_runs",
                return_value=[latest],
            ),
        ):
            from src.python.mcp_server import get_wallet_verification_status

            result = await get_wallet_verification_status(wallet_id="Coldcard")

        assert result["latest_verification"]["is_recent"] is False

    # ------------------------------------------------------------------
    # get_portfolio_verification_posture
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_portfolio_posture_all_verified(self):
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = [
            {"wallet_id": "Coldcard", "custody": "self-custodied", "active": True},
            {"wallet_id": "Sparrow", "custody": "self-custodied", "active": True},
        ]
        mock_accts.get_wallet_balance.return_value = {"Coldcard": 1.0, "Sparrow": 0.5}

        posture = _mock_posture(status="verified")
        latest_cc = _mock_verification_resource(wallet_id="Coldcard")
        latest_sp = _mock_verification_resource(wallet_id="Sparrow", verified_balance=0.5, ledger_balance=0.5)

        def mock_eligibility(accts, wid):
            return _mock_eligibility(True)

        def mock_latest(backend, wid):
            return {"Coldcard": latest_cc, "Sparrow": latest_sp}.get(wid)

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                side_effect=mock_eligibility,
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                side_effect=mock_latest,
            ),
            patch(
                "web.services.wallet_verification.build_portfolio_verification_posture",
                return_value=posture,
            ),
        ):
            from src.python.mcp_server import get_portfolio_verification_posture

            result = await get_portfolio_verification_posture(coin="BTC")

        assert result["status"] == "verified"
        assert result["eligible_wallet_count"] == 2
        assert result["verified_wallet_count"] == 2
        assert len(result["wallets"]) == 2
        wallet_ids = {w["wallet_id"] for w in result["wallets"]}
        assert wallet_ids == {"Coldcard", "Sparrow"}

    @pytest.mark.asyncio
    async def test_portfolio_posture_mixed_custody(self):
        """Exchange wallets are included in the wallets list but not eligible."""
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = [
            {"wallet_id": "Coldcard", "custody": "self-custodied", "active": True},
            {"wallet_id": "Coinbase", "custody": "custodial", "active": True},
        ]
        mock_accts.get_wallet_balance.return_value = {"Coldcard": 1.0, "Coinbase": 0.3}

        posture = _mock_posture(
            status="verified",
            eligible_wallet_count=1,
            verified_wallet_count=1,
        )
        latest_cc = _mock_verification_resource(wallet_id="Coldcard")

        def mock_eligibility(accts, wid):
            if wid == "Coinbase":
                return _mock_eligibility(False, "Exchange wallet")
            return _mock_eligibility(True)

        def mock_latest(backend, wid):
            if wid == "Coldcard":
                return latest_cc
            return None

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                side_effect=mock_eligibility,
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                side_effect=mock_latest,
            ),
            patch(
                "web.services.wallet_verification.build_portfolio_verification_posture",
                return_value=posture,
            ),
        ):
            from src.python.mcp_server import get_portfolio_verification_posture

            result = await get_portfolio_verification_posture(coin="BTC")

        assert result["status"] == "verified"
        assert result["eligible_wallet_count"] == 1
        # Both wallets appear in the detail list (both have balance > 0)
        assert len(result["wallets"]) == 2
        cc = next(w for w in result["wallets"] if w["wallet_id"] == "Coldcard")
        cb = next(w for w in result["wallets"] if w["wallet_id"] == "Coinbase")
        assert cc["eligible"] is True
        assert cc["verification_status"] == "verified"
        assert cb["eligible"] is False
        assert cb["verification_status"] is None

    @pytest.mark.asyncio
    async def test_portfolio_posture_no_wallets(self):
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = []
        mock_accts.get_wallet_balance.return_value = {}

        posture = _mock_posture(
            status="ineligible",
            eligible_wallet_count=0,
            verified_wallet_count=0,
        )

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.build_portfolio_verification_posture",
                return_value=posture,
            ),
        ):
            from src.python.mcp_server import get_portfolio_verification_posture

            result = await get_portfolio_verification_posture(coin="BTC")

        assert result["status"] == "ineligible"
        assert result["eligible_wallet_count"] == 0
        assert result["wallets"] == []

    @pytest.mark.asyncio
    async def test_portfolio_posture_wallet_detail_fields(self):
        """Each wallet in the detail list has the expected fields."""
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = [
            {"wallet_id": "Jade", "custody": "self-custodied", "active": True},
        ]
        mock_accts.get_wallet_balance.return_value = {"Jade": 0.75}

        posture = _mock_posture(eligible_wallet_count=1, verified_wallet_count=0, status="stale")
        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(True),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=None,
            ),
            patch(
                "web.services.wallet_verification.build_portfolio_verification_posture",
                return_value=posture,
            ),
        ):
            from src.python.mcp_server import get_portfolio_verification_posture

            result = await get_portfolio_verification_posture(coin="BTC")

        assert len(result["wallets"]) == 1
        w = result["wallets"][0]
        expected_keys = {
            "wallet_id", "balance", "custody_type", "eligible",
            "verification_status", "verification_coverage", "verification_is_recent",
        }
        assert set(w.keys()) == expected_keys
        assert w["wallet_id"] == "Jade"
        assert w["balance"] == pytest.approx(0.75)
        assert w["eligible"] is True
        assert w["verification_status"] is None

    @pytest.mark.asyncio
    async def test_portfolio_posture_zero_balance_wallets_excluded(self):
        """Wallets with zero balance are not included in the detail list."""
        mock_accts = MagicMock()
        mock_accts.get_wallets.return_value = [
            {"wallet_id": "Coldcard", "custody": "self-custodied", "active": True},
            {"wallet_id": "EmptyWallet", "custody": "self-custodied", "active": True},
        ]
        mock_accts.get_wallet_balance.return_value = {"Coldcard": 1.0, "EmptyWallet": 0.0}

        posture = _mock_posture(eligible_wallet_count=1, verified_wallet_count=1)

        with (
            patch("src.python.mcp_server._make_accounts", return_value=mock_accts),
            patch(
                "web.services.wallet_verification.get_wallet_verification_eligibility",
                return_value=_mock_eligibility(True),
            ),
            patch(
                "web.services.wallet_verification.get_latest_wallet_verification",
                return_value=_mock_verification_resource(),
            ),
            patch(
                "web.services.wallet_verification.build_portfolio_verification_posture",
                return_value=posture,
            ),
        ):
            from src.python.mcp_server import get_portfolio_verification_posture

            result = await get_portfolio_verification_posture(coin="BTC")

        wallet_ids = {w["wallet_id"] for w in result["wallets"]}
        assert "EmptyWallet" not in wallet_ids
        assert "Coldcard" in wallet_ids
