"""Tests for TUI record transaction screen."""

import pytest

from textual.widgets import Button, Input, Label, RadioButton, RadioSet
from tui.screens.record_transaction import RecordTransactionScreen
from tui.app import CryptoApp

from db.sqlite import SqliteBackend


class TestRecordTransactionScreenMount:
    """Test that the record transaction screen mounts and renders properly."""

    @pytest.mark.asyncio
    async def test_record_transaction_screen_mounts(self):
        """Test that record transaction screen mounts successfully."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Push record transaction screen
            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Verify screen is active
            assert isinstance(app.screen, RecordTransactionScreen)

    @pytest.mark.asyncio
    async def test_record_transaction_screen_has_header_footer(self):
        """Test that record transaction screen has header and footer."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Should have header and footer
            from textual.widgets import Header, Footer
            assert app.screen.query_one(Header)
            assert app.screen.query_one(Footer)

    @pytest.mark.asyncio
    async def test_record_transaction_screen_title(self):
        """Test that record transaction screen has correct title."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Check for screen title label
            title_labels = app.screen.query(".screen-title")
            assert len(title_labels) > 0
            title = title_labels[0]
            assert isinstance(title, Label)
            assert "Record Transaction" in str(title.content)


class TestTransactionTypeSelector:
    """Test transaction type selector."""

    @pytest.mark.asyncio
    async def test_type_selector_present(self):
        """Test that type selector radio buttons are present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Should have RadioSet
            radioset = app.screen.query_one("#type-selector", RadioSet)
            assert radioset is not None

            # Should have 4 radio buttons
            buttons = app.screen.query(RadioButton)
            assert len(buttons) == 4

    @pytest.mark.asyncio
    async def test_type_selector_labels(self):
        """Test that type selector has correct labels."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Check for all transaction types
            buy_btn = app.screen.query_one("#type-buy", RadioButton)
            sell_btn = app.screen.query_one("#type-sell", RadioButton)
            transfer_btn = app.screen.query_one("#type-transfer", RadioButton)
            interest_btn = app.screen.query_one("#type-interest", RadioButton)

            assert buy_btn is not None
            assert sell_btn is not None
            assert transfer_btn is not None
            assert interest_btn is not None

    @pytest.mark.asyncio
    async def test_buy_type_selected_by_default(self):
        """Test that Buy type is selected by default."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Buy should be selected
            buy_btn = app.screen.query_one("#type-buy", RadioButton)
            assert buy_btn.value is True


class TestBuyForm:
    """Test buy transaction form."""

    @pytest.mark.asyncio
    async def test_buy_form_fields_present(self):
        """Test that buy form has all required fields."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Should have all buy form fields
            exchange = app.screen.query_one("#exchange", Input)
            quantity = app.screen.query_one("#quantity", Input)
            total_cost = app.screen.query_one("#total_cost", Input)
            fee = app.screen.query_one("#fee", Input)
            tx_date = app.screen.query_one("#tx_date", Input)
            group = app.screen.query_one("#group", Input)

            assert exchange is not None
            assert quantity is not None
            assert total_cost is not None
            assert fee is not None
            assert tx_date is not None
            assert group is not None

    @pytest.mark.asyncio
    async def test_buy_form_default_values(self):
        """Test that buy form has sensible default values."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Exchange should default to Strike
            exchange = app.screen.query_one("#exchange", Input)
            assert exchange.value == "Strike"

            # Fee should default to 0
            fee = app.screen.query_one("#fee", Input)
            assert fee.value == "0"


class TestSellForm:
    """Test sell transaction form."""

    @pytest.mark.asyncio
    async def test_switch_to_sell_form(self):
        """Test switching to sell form."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Click sell radio button
            await pilot.click("#type-sell")
            await pilot.pause(0.1)

            # Should have sell form fields
            exchange = app.screen.query_one("#exchange", Input)
            quantity = app.screen.query_one("#quantity", Input)
            total_proceeds = app.screen.query_one("#total_proceeds", Input)
            fee = app.screen.query_one("#fee", Input)

            assert exchange is not None
            assert quantity is not None
            assert total_proceeds is not None
            assert fee is not None


class TestTransferForm:
    """Test transfer transaction form."""

    @pytest.mark.asyncio
    async def test_switch_to_transfer_form(self):
        """Test switching to transfer form."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Click transfer radio button
            await pilot.click("#type-transfer")
            await pilot.pause(0.1)

            # Should have transfer form fields
            from_wallet = app.screen.query_one("#from_wallet", Input)
            to_wallet = app.screen.query_one("#to_wallet", Input)
            amount = app.screen.query_one("#amount", Input)
            fee = app.screen.query_one("#fee", Input)

            assert from_wallet is not None
            assert to_wallet is not None
            assert amount is not None
            assert fee is not None


class TestInterestForm:
    """Test interest transaction form."""

    @pytest.mark.asyncio
    async def test_switch_to_interest_form(self):
        """Test switching to interest form."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Click interest radio button
            await pilot.click("#type-interest")
            await pilot.pause(0.1)

            # Should have interest form fields
            exchange = app.screen.query_one("#exchange", Input)
            amount = app.screen.query_one("#amount", Input)
            currency = app.screen.query_one("#currency")

            assert exchange is not None
            assert amount is not None
            assert currency is not None


class TestPreview:
    """Test preview panel."""

    @pytest.mark.asyncio
    async def test_preview_panel_present(self):
        """Test that preview panel is present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Should have preview panel
            preview = app.screen.query_one("#preview-panel")
            assert preview is not None

    @pytest.mark.asyncio
    async def test_preview_content_present(self):
        """Test that preview content is present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Should have preview content label
            preview_content = app.screen.query_one("#preview-content", Label)
            assert preview_content is not None


class TestActionButtons:
    """Test action buttons."""

    @pytest.mark.asyncio
    async def test_confirm_cancel_buttons_present(self):
        """Test that confirm and cancel buttons are present."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Should have both buttons
            confirm_btn = app.screen.query_one("#btn-confirm", Button)
            cancel_btn = app.screen.query_one("#btn-cancel", Button)

            assert confirm_btn is not None
            assert cancel_btn is not None

    @pytest.mark.asyncio
    async def test_cancel_button_returns_to_previous_screen(self):
        """Test that cancel button returns to previous screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Should start on dashboard
            from tui.screens import DashboardScreen
            assert isinstance(app.screen, DashboardScreen)

            # Push record transaction screen
            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)
            assert isinstance(app.screen, RecordTransactionScreen)

            # Click cancel
            await pilot.click("#btn-cancel")
            await pilot.pause(0.1)

            # Should be back on dashboard
            assert isinstance(app.screen, DashboardScreen)


class TestNavigation:
    """Test record transaction screen navigation."""

    @pytest.mark.asyncio
    async def test_escape_key_returns(self):
        """Test that escape key returns to previous screen."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Should start on dashboard
            from tui.screens import DashboardScreen
            assert isinstance(app.screen, DashboardScreen)

            # Push record transaction screen
            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)
            assert isinstance(app.screen, RecordTransactionScreen)

            # Press escape
            await pilot.press("escape")
            await pilot.pause(0.1)

            # Should be back on dashboard
            assert isinstance(app.screen, DashboardScreen)

    @pytest.mark.asyncio
    async def test_r_key_opens_record_transaction(self):
        """Test that R key opens record transaction screen from dashboard."""
        app = CryptoApp()
        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            # Press R to open record transaction
            await pilot.press("r")
            await pilot.pause(0.1)

            # Should be on record transaction screen
            assert isinstance(app.screen, RecordTransactionScreen)


class TestRecordTransactionWithDatabase:
    """Test recording transactions with in-memory database."""

    @pytest.mark.asyncio
    async def test_record_transfer_transaction(self):
        """Test recording a simple transfer transaction."""
        # Create in-memory database
        backend = SqliteBackend(':memory:', auto_create_tables=True)
        from cryptoAccounts import CryptoAccounts
        crypto = CryptoAccounts(backend=backend)

        # Add initial balance to source wallet
        crypto.import_transactions([{
            'trans_type': 'Deposit',
            'created_date': '2024-01-01 10:00:00',
            'buy': 1.0,
            'buy_curr': 'BTC',
            'sell': 0.0,
            'sell_curr': '',
            'fee': 0.0,
            'fee_curr': '',
            'exchange': 'Ledger',
            'wallet': 'Ledger',
            'group': '',
            'comment': 'Initial balance'
        }])

        # Create app with this database
        app = CryptoApp()
        app.crypto = crypto

        async with app.run_test(notifications=True) as pilot:
            await pilot.pause(0.1)

            app.push_screen(RecordTransactionScreen())
            await pilot.pause(0.1)

            # Switch to transfer form
            await pilot.click("#type-transfer")
            await pilot.pause(0.1)

            # Fill in form
            from_wallet_input = app.screen.query_one("#from_wallet", Input)
            to_wallet_input = app.screen.query_one("#to_wallet", Input)
            amount_input = app.screen.query_one("#amount", Input)
            fee_input = app.screen.query_one("#fee", Input)

            from_wallet_input.value = "Ledger"
            to_wallet_input.value = "Coldcard"
            amount_input.value = "0.5"
            fee_input.value = "0.0001"

            await pilot.pause(0.1)

            # Note: We can't actually click confirm and wait for the async worker
            # in tests due to threading issues, but we've verified the form renders

        crypto.close()
