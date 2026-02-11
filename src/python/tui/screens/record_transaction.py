"""Record transaction screen for manual transaction entry."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.validation import Number
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Header,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    Static,
)

if TYPE_CHECKING:
    from tui.app import CryptoApp
    from cryptoAccounts import CryptoAccounts


class RecordTransactionScreen(Screen[None]):
    """Screen for recording transactions manually."""

    DEFAULT_CSS = """
    RecordTransactionScreen {
        background: $background;
    }

    RecordTransactionScreen Container {
        height: 100%;
        layout: vertical;
    }

    RecordTransactionScreen .screen-title {
        dock: top;
        height: 3;
        content-align: center middle;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    RecordTransactionScreen .type-selector {
        dock: top;
        height: auto;
        min-height: 6;
        background: $surface;
        padding: 1;
        margin-bottom: 1;
    }

    RecordTransactionScreen RadioSet {
        height: auto;
        layout: horizontal;
    }

    RecordTransactionScreen RadioButton {
        margin-right: 3;
    }

    RecordTransactionScreen .form-panel {
        height: 1fr;
        layout: vertical;
        background: $surface;
        padding: 1;
        margin-bottom: 1;
        overflow-y: auto;
    }

    RecordTransactionScreen .form-row {
        height: auto;
        min-height: 4;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    RecordTransactionScreen .form-label {
        width: 20;
        padding-right: 1;
        color: $text-muted;
    }

    RecordTransactionScreen Input {
        width: 40;
    }

    RecordTransactionScreen Select {
        width: 40;
    }

    RecordTransactionScreen Checkbox {
        margin-top: 1;
    }

    RecordTransactionScreen .preview-panel {
        dock: bottom;
        height: auto;
        min-height: 8;
        max-height: 15;
        background: $surface;
        padding: 1;
        margin-bottom: 1;
        layout: vertical;
    }

    RecordTransactionScreen .preview-title {
        color: $accent;
        text-style: bold;
        margin-bottom: 1;
    }

    RecordTransactionScreen .preview-line {
        color: $text;
        margin: 0;
    }

    RecordTransactionScreen .button-row {
        dock: bottom;
        height: 3;
        layout: horizontal;
        align: center middle;
    }

    RecordTransactionScreen .button-row Button {
        margin: 0 1;
        min-width: 15;
    }

    RecordTransactionScreen .error-message {
        color: $error;
        text-style: bold;
    }

    RecordTransactionScreen .success-message {
        color: $success;
        text-style: bold;
    }
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._current_type = "buy"

    def compose(self) -> ComposeResult:
        """Compose the screen layout."""
        yield Header()
        with Container():
            yield Label("Record Transaction", classes="screen-title")

            # Transaction type selector
            with Container(classes="type-selector"):
                with RadioSet(id="type-selector"):
                    yield RadioButton("Buy", id="type-buy", value=True)
                    yield RadioButton("Sell", id="type-sell")
                    yield RadioButton("Transfer", id="type-transfer")
                    yield RadioButton("Earn Interest", id="type-interest")

            # Form container (dynamically populated)
            yield Container(id="form-container", classes="form-panel")

            # Preview panel
            with Container(id="preview-panel", classes="preview-panel"):
                yield Label("Preview", classes="preview-title")
                yield Label("Select transaction type and fill in details", id="preview-content")

            # Action buttons
            with Horizontal(classes="button-row"):
                yield Button("Confirm", id="btn-confirm", variant="success")
                yield Button("Cancel", id="btn-cancel")

        yield Footer()

    def on_mount(self) -> None:
        """Handle screen mount."""
        self.app.sub_title = "Record Transaction"
        self._show_buy_form()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle transaction type change."""
        if event.radio_set.id == "type-selector":
            pressed_id = str(event.pressed.id)

            if pressed_id == "type-buy":
                self._current_type = "buy"
                self._show_buy_form()
            elif pressed_id == "type-sell":
                self._current_type = "sell"
                self._show_sell_form()
            elif pressed_id == "type-transfer":
                self._current_type = "transfer"
                self._show_transfer_form()
            elif pressed_id == "type-interest":
                self._current_type = "interest"
                self._show_interest_form()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-confirm":
            self._confirm_transaction()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes to update preview."""
        self._update_preview()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox changes."""
        # Show/hide conditional fields based on checkboxes
        if event.checkbox.id == "withdraw-check":
            self._toggle_withdraw_fields(event.checkbox.value)
        elif event.checkbox.id == "transfer-check":
            self._toggle_transfer_fields(event.checkbox.value)

    def _show_buy_form(self) -> None:
        """Show the buy transaction form."""
        form_container = self.query_one("#form-container", Container)
        form_container.remove_children()

        # Exchange
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Exchange:", classes="form-label"))
        row.mount(Input(value="Strike", id="exchange", placeholder="Exchange name"))

        # Quantity
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Quantity (BTC):", classes="form-label"))
        row.mount(Input(id="quantity", placeholder="0.00000000", validators=[Number(minimum=0)]))

        # Total cost
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Total Cost (USD):", classes="form-label"))
        row.mount(Input(id="total_cost", placeholder="0.00", validators=[Number(minimum=0)]))

        # Fee
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Fee (BTC):", classes="form-label"))
        row.mount(Input(value="0", id="fee", placeholder="0.00000000", validators=[Number(minimum=0)]))

        # Date
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Date:", classes="form-label"))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row.mount(Input(value=now_str, id="tx_date", placeholder="YYYY-MM-DD HH:MM:SS"))

        # Group
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Group (optional):", classes="form-label"))
        row.mount(Input(id="group", placeholder="Optional group identifier"))

        # Withdraw checkbox
        form_container.mount(Checkbox("Withdraw to cold storage after purchase", id="withdraw-check"))

        # Withdraw fields (initially hidden)
        withdraw_container = Container(id="withdraw-fields")
        form_container.mount(withdraw_container)

    def _show_sell_form(self) -> None:
        """Show the sell transaction form."""
        form_container = self.query_one("#form-container", Container)
        form_container.remove_children()

        # Transfer from wallet checkbox
        form_container.mount(Checkbox("Transfer from wallet to exchange first", id="transfer-check"))

        # Transfer fields container
        transfer_container = Container(id="transfer-fields")
        form_container.mount(transfer_container)

        # Wallet source (shown if transfer checkbox checked)
        # Exchange
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Exchange:", classes="form-label"))
        row.mount(Input(value="Strike", id="exchange", placeholder="Exchange name"))

        # Quantity
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Quantity (BTC):", classes="form-label"))
        row.mount(Input(id="quantity", placeholder="0.00000000", validators=[Number(minimum=0)]))

        # Total proceeds
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Total Proceeds (USD):", classes="form-label"))
        row.mount(Input(id="total_proceeds", placeholder="0.00", validators=[Number(minimum=0)]))

        # Fee
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Fee (USD):", classes="form-label"))
        row.mount(Input(value="0", id="fee", placeholder="0.00", validators=[Number(minimum=0)]))

        # Date
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Sale Date:", classes="form-label"))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row.mount(Input(value=now_str, id="tx_date", placeholder="YYYY-MM-DD HH:MM:SS"))

    def _show_transfer_form(self) -> None:
        """Show the transfer transaction form."""
        form_container = self.query_one("#form-container", Container)
        form_container.remove_children()

        # From wallet
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("From Wallet:", classes="form-label"))
        row.mount(Input(value="Ledger", id="from_wallet", placeholder="Source wallet"))

        # To wallet
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("To Wallet:", classes="form-label"))
        row.mount(Input(value="Coldcard", id="to_wallet", placeholder="Destination wallet"))

        # Amount (received after fee)
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Amount Received:", classes="form-label"))
        row.mount(Input(id="amount", placeholder="0.00000000 (after fee)", validators=[Number(minimum=0)]))

        # Fee
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Fee (BTC):", classes="form-label"))
        row.mount(Input(value="0.00001500", id="fee", placeholder="0.00000000", validators=[Number(minimum=0)]))

        # Date
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Transfer Date:", classes="form-label"))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row.mount(Input(value=now_str, id="tx_date", placeholder="YYYY-MM-DD HH:MM:SS"))

    def _show_interest_form(self) -> None:
        """Show the earn interest transaction form."""
        form_container = self.query_one("#form-container", Container)
        form_container.remove_children()

        # Exchange
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Exchange/Account:", classes="form-label"))
        row.mount(Input(value="River", id="exchange", placeholder="Exchange or account name"))

        # Amount
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Amount:", classes="form-label"))
        row.mount(Input(id="amount", placeholder="0.00000000", validators=[Number(minimum=0)]))

        # Currency
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Currency:", classes="form-label"))
        row.mount(Select([("BTC", "BTC"), ("USD", "USD")], value="BTC", id="currency"))

        # Date
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Date:", classes="form-label"))
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row.mount(Input(value=now_str, id="tx_date", placeholder="YYYY-MM-DD HH:MM:SS"))

        # Group
        row = Horizontal(classes="form-row")
        form_container.mount(row)
        row.mount(Label("Group (optional):", classes="form-label"))
        row.mount(Input(id="group", placeholder="Optional group identifier"))

    def _toggle_withdraw_fields(self, show: bool) -> None:
        """Show/hide withdraw to cold storage fields."""
        withdraw_container = self.query_one("#withdraw-fields", Container)
        withdraw_container.remove_children()

        if show:
            # Withdraw wallet
            row = Horizontal(classes="form-row")
            withdraw_container.mount(row)
            row.mount(Label("Withdraw To:", classes="form-label"))
            row.mount(Input(value="Ledger", id="withdraw_wallet", placeholder="Destination wallet"))

            # Withdraw delay
            row = Horizontal(classes="form-row")
            withdraw_container.mount(row)
            row.mount(Label("Delay (minutes):", classes="form-label"))
            row.mount(Input(value="700", id="withdraw_delay", placeholder="Minutes", validators=[Number(minimum=0)]))

    def _toggle_transfer_fields(self, show: bool) -> None:
        """Show/hide transfer from wallet fields."""
        transfer_container = self.query_one("#transfer-fields", Container)
        transfer_container.remove_children()

        if show:
            # Source wallet
            row = Horizontal(classes="form-row")
            transfer_container.mount(row)
            row.mount(Label("Source Wallet:", classes="form-label"))
            row.mount(Input(value="Coldcard", id="wallet_source", placeholder="Wallet to transfer from"))

    def _update_preview(self) -> None:
        """Update the preview panel with current form values."""
        preview = self.query_one("#preview-content", Label)

        try:
            if self._current_type == "buy":
                exchange = self.query_one("#exchange", Input).value
                quantity = self.query_one("#quantity", Input).value
                total_cost = self.query_one("#total_cost", Input).value
                fee = self.query_one("#fee", Input).value
                tx_date = self.query_one("#tx_date", Input).value

                # Compute price if possible
                price_str = "N/A"
                if quantity and total_cost:
                    try:
                        q = float(quantity)
                        c = float(total_cost)
                        if q > 0:
                            price_str = f"${c/q:,.2f}/BTC"
                    except ValueError:
                        pass

                preview_text = f"Buy {quantity or '?'} BTC at {exchange or '?'}\n"
                preview_text += f"Total Cost: ${total_cost or '0.00'}\n"
                preview_text += f"Price: {price_str}\n"
                preview_text += f"Fee: {fee or '0'} BTC\n"
                preview_text += f"Date: {tx_date}"
                preview.update(preview_text)

            elif self._current_type == "sell":
                exchange = self.query_one("#exchange", Input).value
                quantity = self.query_one("#quantity", Input).value
                total_proceeds = self.query_one("#total_proceeds", Input).value
                fee = self.query_one("#fee", Input).value
                tx_date = self.query_one("#tx_date", Input).value

                # Compute price if possible
                price_str = "N/A"
                if quantity and total_proceeds:
                    try:
                        q = float(quantity)
                        p = float(total_proceeds)
                        if q > 0:
                            price_str = f"${p/q:,.2f}/BTC"
                    except ValueError:
                        pass

                preview_text = f"Sell {quantity or '?'} BTC at {exchange or '?'}\n"
                preview_text += f"Total Proceeds: ${total_proceeds or '0.00'}\n"
                preview_text += f"Price: {price_str}\n"
                preview_text += f"Fee: ${fee or '0'}\n"
                preview_text += f"Date: {tx_date}"
                preview.update(preview_text)

            elif self._current_type == "transfer":
                from_wallet = self.query_one("#from_wallet", Input).value
                to_wallet = self.query_one("#to_wallet", Input).value
                amount = self.query_one("#amount", Input).value
                fee = self.query_one("#fee", Input).value
                tx_date = self.query_one("#tx_date", Input).value

                preview_text = f"Transfer {amount or '?'} BTC\n"
                preview_text += f"From: {from_wallet or '?'}\n"
                preview_text += f"To: {to_wallet or '?'}\n"
                preview_text += f"Fee: {fee or '0'} BTC\n"
                preview_text += f"Date: {tx_date}"
                preview.update(preview_text)

            elif self._current_type == "interest":
                exchange = self.query_one("#exchange", Input).value
                amount = self.query_one("#amount", Input).value
                currency = self.query_one("#currency", Select).value
                tx_date = self.query_one("#tx_date", Input).value

                preview_text = f"Earn Interest: {amount or '?'} {currency or 'BTC'}\n"
                preview_text += f"Account: {exchange or '?'}\n"
                preview_text += f"Date: {tx_date}"
                preview.update(preview_text)
        except Exception:
            # If any widget not found yet, just skip update
            pass

    def _confirm_transaction(self) -> None:
        """Confirm and record the transaction."""
        try:
            if self._current_type == "buy":
                self._record_buy()
            elif self._current_type == "sell":
                self._record_sell()
            elif self._current_type == "transfer":
                self._record_transfer()
            elif self._current_type == "interest":
                self._record_interest()
        except Exception as e:
            self.app.notify(f"Error: {str(e)}", severity="error", timeout=5)

    @work(thread=True)
    def _record_buy(self) -> None:
        """Record a buy transaction."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto = app.crypto

        if crypto is None:
            self.app.call_from_thread(lambda: self.app.notify("No database connection", severity="error", timeout=3))
            return

        try:
            # Get form values
            exchange = self.query_one("#exchange", Input).value
            quantity_str = self.query_one("#quantity", Input).value
            total_cost_str = self.query_one("#total_cost", Input).value
            fee_str = self.query_one("#fee", Input).value or "0"
            tx_date_str = self.query_one("#tx_date", Input).value
            group = self.query_one("#group", Input).value or ""

            # Validate
            if not exchange or not quantity_str or not total_cost_str:
                self.app.call_from_thread(lambda: self.app.notify("Please fill in all required fields", severity="error", timeout=3))
                return

            quantity = float(quantity_str)
            total_cost = float(total_cost_str)
            fee = float(fee_str)
            tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d %H:%M:%S")

            # Step 1: Deposit USD
            crypto.deposit(exchange=exchange, deposit_date=tx_date, buy=total_cost)
            tx_date = tx_date + timedelta(seconds=30)

            # Step 2: Execute trade
            crypto.execute_trade(
                exchange=exchange,
                trade_date=tx_date,
                buy=quantity,
                buy_curr="BTC",
                sell=total_cost,
                sell_curr="USD",
                fee=fee,
                fee_curr="BTC",
                group=group if group else ""
            )
            tx_date = tx_date + timedelta(seconds=30)

            # Step 3: Optional withdraw
            try:
                withdraw_check = self.query_one("#withdraw-check", Checkbox)
                if withdraw_check.value:
                    withdraw_wallet = self.query_one("#withdraw_wallet", Input).value
                    withdraw_delay_str = self.query_one("#withdraw_delay", Input).value or "700"
                    withdraw_delay = int(withdraw_delay_str)
                    withdraw_date = tx_date + timedelta(minutes=withdraw_delay)

                    crypto.transfer_funds(
                        from_account=exchange,
                        to_account=withdraw_wallet,
                        withdraw_date=tx_date,
                        deposit_date=withdraw_date,
                        tx_amount=quantity,
                        tx_coin="BTC"
                    )
            except Exception:
                # Withdraw fields not present or checkbox unchecked
                pass

            # Success
            balance = crypto.get_balance("BTC")
            basis = crypto.get_basis("BTC")
            self.app.call_from_thread(
                lambda: self.app.notify(
                    f"Transaction recorded. Balance: {balance:.8f} BTC @ ${basis:.2f}/BTC",
                    severity="success",
                    timeout=5
                )
            )
            self.app.call_from_thread(self.app.pop_screen)

        except Exception as e:
            self.app.call_from_thread(lambda: self.app.notify(f"Error: {str(e)}", severity="error", timeout=5))

    @work(thread=True)
    def _record_sell(self) -> None:
        """Record a sell transaction."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto = app.crypto

        if crypto is None:
            self.app.call_from_thread(lambda: self.app.notify("No database connection", severity="error", timeout=3))
            return

        try:
            # Get form values
            exchange = self.query_one("#exchange", Input).value
            quantity_str = self.query_one("#quantity", Input).value
            total_proceeds_str = self.query_one("#total_proceeds", Input).value
            fee_str = self.query_one("#fee", Input).value or "0"
            tx_date_str = self.query_one("#tx_date", Input).value

            # Validate
            if not exchange or not quantity_str or not total_proceeds_str:
                self.app.call_from_thread(lambda: self.app.notify("Please fill in all required fields", severity="error", timeout=3))
                return

            quantity = float(quantity_str)
            total_proceeds = float(total_proceeds_str)
            fee = float(fee_str)
            tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d %H:%M:%S")

            # Step 1: Optional transfer to exchange
            try:
                transfer_check = self.query_one("#transfer-check", Checkbox)
                if transfer_check.value:
                    wallet_source = self.query_one("#wallet_source", Input).value
                    if wallet_source and wallet_source != exchange:
                        withdraw_date = tx_date - timedelta(minutes=70)
                        deposit_date = tx_date - timedelta(minutes=10)
                        crypto.transfer_funds(
                            from_account=wallet_source,
                            to_account=exchange,
                            withdraw_date=withdraw_date,
                            deposit_date=deposit_date,
                            tx_amount=quantity,
                            tx_coin="BTC"
                        )
            except Exception:
                # Transfer fields not present or checkbox unchecked
                pass

            # Step 2: Execute trade (BTC -> USD)
            crypto.execute_trade(
                exchange=exchange,
                trade_date=tx_date,
                buy=total_proceeds,
                buy_curr="USD",
                sell=quantity,
                sell_curr="BTC",
                fee=fee,
                fee_curr="USD",
                group=""
            )

            # Success
            balance = crypto.get_balance("BTC")
            basis = crypto.get_basis("BTC")
            self.app.call_from_thread(
                lambda: self.app.notify(
                    f"Transaction recorded. Balance: {balance:.8f} BTC @ ${basis:.2f}/BTC",
                    severity="success",
                    timeout=5
                )
            )
            self.app.call_from_thread(self.app.pop_screen)

        except Exception as e:
            self.app.call_from_thread(lambda: self.app.notify(f"Error: {str(e)}", severity="error", timeout=5))

    @work(thread=True)
    def _record_transfer(self) -> None:
        """Record a transfer transaction."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto = app.crypto

        if crypto is None:
            self.app.call_from_thread(lambda: self.app.notify("No database connection", severity="error", timeout=3))
            return

        try:
            # Get form values
            from_wallet = self.query_one("#from_wallet", Input).value
            to_wallet = self.query_one("#to_wallet", Input).value
            amount_str = self.query_one("#amount", Input).value
            fee_str = self.query_one("#fee", Input).value or "0"
            tx_date_str = self.query_one("#tx_date", Input).value

            # Validate
            if not from_wallet or not to_wallet or not amount_str:
                self.app.call_from_thread(lambda: self.app.notify("Please fill in all required fields", severity="error", timeout=3))
                return

            amount = float(amount_str)
            fee = float(fee_str)
            tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d %H:%M:%S")

            # Record transfer
            crypto.transfer_funds(
                withdraw_date=tx_date,
                deposit_date=None,
                from_account=from_wallet,
                tx_coin="BTC",
                tx_amount=amount,
                to_account=to_wallet,
                fee_coin="BTC",
                fee_amount=fee
            )

            # Success
            from_balance = crypto.get_balance_by_account("BTC", from_wallet)
            to_balance = crypto.get_balance_by_account("BTC", to_wallet)
            self.app.call_from_thread(
                lambda: self.app.notify(
                    f"Transfer recorded. From: {from_balance:.8f}, To: {to_balance:.8f}",
                    severity="success",
                    timeout=5
                )
            )
            self.app.call_from_thread(self.app.pop_screen)

        except Exception as e:
            self.app.call_from_thread(lambda: self.app.notify(f"Error: {str(e)}", severity="error", timeout=5))

    @work(thread=True)
    def _record_interest(self) -> None:
        """Record an interest income transaction."""
        from tui.app import CryptoApp

        app = self.app
        assert isinstance(app, CryptoApp)
        crypto = app.crypto

        if crypto is None:
            self.app.call_from_thread(lambda: self.app.notify("No database connection", severity="error", timeout=3))
            return

        try:
            # Get form values
            exchange = self.query_one("#exchange", Input).value
            amount_str = self.query_one("#amount", Input).value
            currency = str(self.query_one("#currency", Select).value)
            tx_date_str = self.query_one("#tx_date", Input).value
            group = self.query_one("#group", Input).value or ""

            # Validate
            if not exchange or not amount_str:
                self.app.call_from_thread(lambda: self.app.notify("Please fill in all required fields", severity="error", timeout=3))
                return

            amount = float(amount_str)
            tx_date = datetime.strptime(tx_date_str, "%Y-%m-%d %H:%M:%S")

            # Record interest
            crypto.interest(
                interest_date=tx_date,
                buy=amount,
                buy_curr=currency,
                exchange=exchange,
                group=group,
                comment=""
            )

            # Success
            balance = crypto.get_balance(currency)
            self.app.call_from_thread(
                lambda: self.app.notify(
                    f"Interest recorded. Balance: {balance:.8f} {currency}",
                    severity="success",
                    timeout=5
                )
            )
            self.app.call_from_thread(self.app.pop_screen)

        except Exception as e:
            self.app.call_from_thread(lambda: self.app.notify(f"Error: {str(e)}", severity="error", timeout=5))
