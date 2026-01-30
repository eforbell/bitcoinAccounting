"""Tests for btc_viz CLI script (VIZ-005)."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from src.python.db import SqliteBackend

# Path to btc_viz script
SCRIPT_PATH = Path(__file__).parent.parent / "src" / "scripts" / "btc_viz"


class TestCLI:
    """Tests for btc_viz CLI."""

    def test_help_flag(self) -> None:
        """Test --help flag."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--help"],
            capture_output=True,
            text=True
        )

        assert result.returncode == 0
        assert "Bitcoin portfolio visualizations" in result.stdout
        assert "--range" in result.stdout
        assert "--chart" in result.stdout

    def test_invalid_dpi_fails(self) -> None:
        """Test that invalid DPI returns error."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--dpi", "1000"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 1
        assert "dpi" in result.stderr.lower()

    def test_invalid_date_format_fails(self) -> None:
        """Test that invalid date format returns error."""
        result = subprocess.run(
            [".venv/bin/python", str(SCRIPT_PATH), "--start-date", "2023/01/01", "--end-date", "2023-12-31"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 1
        assert "date" in result.stderr.lower()

    def test_empty_database_fails_gracefully(self) -> None:
        """Test that empty database returns appropriate error."""
        # Create empty database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "empty.db"
            backend = SqliteBackend(str(db_path), auto_create_tables=True)
            backend.close()

            # Try to generate charts with empty database
            result = subprocess.run(
                [".venv/bin/python", str(SCRIPT_PATH), "--output", tmpdir],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
                env={"SQLITE_DB_PATH": str(db_path), "DB_BACKEND": "sqlite"}
            )

            # Should fail with non-zero exit code
            assert result.returncode != 0

    def test_generate_single_chart(self) -> None:
        """Test generating a single chart type."""
        # Create test database with data
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            backend = SqliteBackend(str(db_path), auto_create_tables=True)

            # Add sample data
            backend.execute(
                """
                INSERT INTO ledger (
                    createddate, trans_type, buy_curr, buy, sell_curr, sell,
                    fee_curr, fee, exchange, "group", comment
                ) VALUES
                ('2020-01-15 10:00:00', 'Trade', 'BTC', 0.5, 'USD', 5000.0, '', 0, 'Coinbase', '', ''),
                ('2020-06-01 14:30:00', 'Trade', 'BTC', 0.3, 'USD', 3600.0, '', 0, 'Coinbase', '', '')
                """
            )
            backend.execute(
                """
                INSERT INTO pair_price (date, to_curr, from_curr, price) VALUES
                ('2020-01-15 10:00:00', 'BTC', 'USD', 10000.0),
                ('2020-06-01 14:30:00', 'BTC', 'USD', 12000.0)
                """
            )
            backend.commit()
            backend.close()

            output_dir = Path(tmpdir) / "viz"

            # Generate balance chart
            result = subprocess.run(
                [".venv/bin/python", str(SCRIPT_PATH), "--chart", "balance", "--output", str(output_dir)],
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent,
                env={"SQLITE_DB_PATH": str(db_path), "DB_BACKEND": "sqlite", "PATH": str(Path.cwd() / ".venv" / "bin")}
            )

            # Should succeed
            assert result.returncode == 0
            assert "Generating balance plot" in result.stdout
            
            # Check that balance chart was created
            balance_charts = list(output_dir.glob("btc_balance_*.png"))
            assert len(balance_charts) >= 1
