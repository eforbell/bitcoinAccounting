"""Wallet Management screen for creating, editing, renaming, and merging wallets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label

if TYPE_CHECKING:
    from tui.app import CryptoApp


class WalletManagementScreen(Screen[None]):
    """Wallet Management screen with wallet list and CRUD operations."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("n", "new_wallet", "New", show=True),
        Binding("e", "edit_wallet", "Edit", show=True),
        Binding("d", "toggle_active", "Deactivate", show=True),
        Binding("r", "rename_wallet", "Rename", show=False),
        Binding("m", "merge_wallets", "Merge", show=False),
    ]

    CSS = """
    WalletManagementScreen {
        background: #1a1a2e;
    }
    #wallet-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #loading-message {
        color: #f7931a;
        text-align: center;
        margin-top: 10;
    }
    #error-message {
        color: red;
        text-align: center;
        margin-top: 10;
    }
    #empty-message {
        color: #888888;
        text-align: center;
        margin-top: 10;
    }
    DataTable {
        height: 1fr;
    }
    /* Color-coding for custody types */
    .custody-self {
        color: #00ff00;
    }
    .custody-custodial {
        color: #ffff00;
    }
    .custody-multisig {
        color: #00ffff;
    }
    .custody-unknown {
        color: #888888;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._state: str = "empty"  # empty | loading | success | error
        self._wallets: list[dict[str, Any]] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(id="wallet-container")
        yield Footer()

    def on_mount(self) -> None:
        """Load wallet data when screen mounts."""
        self.app.sub_title = "Wallet Management"
        self._show_loading()
        self.load_wallet_data()

    def _show_loading(self) -> None:
        """Display loading state."""
        self._state = "loading"
        container = self.query_one("#wallet-container", Container)
        container.remove_children()
        container.mount(Label("Loading wallet data...", id="loading-message"))

    def _show_empty(self) -> None:
        """Display empty state."""
        self._state = "empty"
        container = self.query_one("#wallet-container", Container)
        container.remove_children()
        container.mount(
            Label("No wallets found. Syncing wallets from ledger...", id="empty-message")
        )

    def _show_error(self, message: str) -> None:
        """Display error state."""
        self._state = "error"
        container = self.query_one("#wallet-container", Container)
        container.remove_children()
        container.mount(Label(f"Error: {message}", id="error-message"))

    def _show_wallet_table(self) -> None:
        """Display wallet data in a DataTable."""
        self._state = "success"
        container = self.query_one("#wallet-container", Container)
        container.remove_children()

        # Create DataTable
        table = DataTable(id="wallet-table", cursor_type="row")
        table.add_columns("Name", "Type", "Custody", "Description", "Active", "Tx Count")

        # Get transaction counts for each wallet
        app: CryptoApp = self.app  # type: ignore
        tx_counts: dict[str, int] = {}

        # Query ledger for transaction counts per wallet
        query = """
            SELECT exchange, COUNT(*) as tx_count
            FROM ledger
            WHERE exchange IS NOT NULL
            GROUP BY exchange
        """
        try:
            rows = app.crypto.backend.execute(query)
            tx_counts = {row['exchange']: row['tx_count'] for row in rows}
        except Exception:
            pass  # If query fails, tx_counts will be empty dict

        # Add rows with color-coding by custody type
        for wallet in self._wallets:
            wallet_id = wallet['wallet_id']
            wallet_type = wallet['type']
            custody = wallet['custody']
            description = wallet.get('description') or ''
            active = "Yes" if wallet['active'] else "No"
            tx_count = tx_counts.get(wallet_id, 0)

            # Determine custody class for color-coding
            custody_class = f"custody-{custody.replace('-', '')}"

            # Add styled row
            table.add_row(
                wallet_id,
                wallet_type,
                custody,
                description,
                active,
                str(tx_count),
                key=wallet_id
            )

        container.mount(table)

        # Focus the table for keyboard navigation
        table.focus()

    @work(thread=True)
    def load_wallet_data(self) -> None:
        """Load wallet data in background thread."""
        try:
            app: CryptoApp = self.app  # type: ignore
            wallet_query = app.crypto.wallet_query

            # Sync wallets from ledger to ensure all transaction-referenced wallets exist
            wallet_query.sync_wallets_from_ledger()

            # Get all wallets
            wallets = wallet_query.get_wallets()

            # Update UI on main thread
            self.call_from_thread(self._handle_wallet_data, wallets)

        except Exception as e:
            self.call_from_thread(self._show_error, str(e))

    def _handle_wallet_data(self, wallets: list[dict[str, Any]]) -> None:
        """Handle wallet data loaded from background thread."""
        self._wallets = wallets

        if not wallets:
            self._show_empty()
        else:
            self._show_wallet_table()

    def action_new_wallet(self) -> None:
        """Show modal to create a new wallet."""
        # TODO: WM-003 - Implement CreateWalletModal
        self.notify("Create wallet feature coming in WM-003", severity="information")

    def action_edit_wallet(self) -> None:
        """Show modal to edit selected wallet."""
        # TODO: WM-004 - Implement EditWalletModal
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to edit", severity="warning")
            return
        self.notify("Edit wallet feature coming in WM-004", severity="information")

    def action_toggle_active(self) -> None:
        """Toggle active/inactive status for selected wallet."""
        # TODO: Implement toggle active
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to deactivate", severity="warning")
            return
        self.notify("Toggle active feature coming soon", severity="information")

    def action_rename_wallet(self) -> None:
        """Show modal to rename selected wallet."""
        # TODO: WM-005 - Implement RenameWalletModal
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to rename", severity="warning")
            return
        self.notify("Rename wallet feature coming in WM-005", severity="information")

    def action_merge_wallets(self) -> None:
        """Show modal to merge selected wallet into another."""
        # TODO: WM-006 - Implement MergeWalletsModal
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to merge", severity="warning")
            return
        self.notify("Merge wallets feature coming in WM-006", severity="information")
