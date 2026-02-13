"""Wallet Management screen for creating, editing, renaming, and merging wallets."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Button, DataTable, Footer, Header, Input, Label, Select

if TYPE_CHECKING:
    from tui.app import CryptoApp


class CreateWalletModal(ModalScreen[bool]):
    """Modal dialog for creating a new wallet."""

    CSS = """
    CreateWalletModal {
        align: center middle;
    }

    #create-wallet-container {
        width: 70;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #modal-title {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .form-row {
        height: auto;
        min-height: 4;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    .form-label {
        width: 15;
        padding-right: 1;
        color: $text-muted;
    }

    CreateWalletModal Input {
        width: 45;
    }

    CreateWalletModal Select {
        width: 45;
    }

    #button-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #button-row Button {
        margin: 0 1;
        min-width: 12;
    }

    .error-message {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self) -> None:
        """Initialize the create wallet modal."""
        super().__init__()
        self._error_message: str = ""

    def compose(self) -> ComposeResult:
        """Compose the create wallet form."""
        with Container(id="create-wallet-container"):
            yield Label("Create New Wallet", id="modal-title")

            # Error message placeholder (initially empty)
            yield Label("", id="error-msg", classes="error-message")

            # Name field (required)
            with Horizontal(classes="form-row"):
                yield Label("Name:", classes="form-label")
                yield Input(
                    placeholder="Enter wallet name",
                    id="wallet-name-input"
                )

            # Type field (Select)
            with Horizontal(classes="form-row"):
                yield Label("Type:", classes="form-label")
                yield Select(
                    options=[
                        ("Exchange", "exchange"),
                        ("Hardware Wallet", "hardware"),
                        ("Software Wallet", "software"),
                        ("Mobile Wallet", "mobile"),
                        ("Paper Wallet", "paper"),
                        ("Other", "other"),
                    ],
                    value="hardware",
                    id="wallet-type-select"
                )

            # Custody field (Select)
            with Horizontal(classes="form-row"):
                yield Label("Custody:", classes="form-label")
                yield Select(
                    options=[
                        ("Self-Custodied", "self-custodied"),
                        ("Custodial", "custodial"),
                        ("Multisig", "multisig"),
                    ],
                    value="self-custodied",
                    id="wallet-custody-select"
                )

            # Description field (optional)
            with Horizontal(classes="form-row"):
                yield Label("Description:", classes="form-label")
                yield Input(
                    placeholder="Optional description",
                    id="wallet-description-input"
                )

            # Notes field (optional)
            with Horizontal(classes="form-row"):
                yield Label("Notes:", classes="form-label")
                yield Input(
                    placeholder="Optional notes",
                    id="wallet-notes-input"
                )

            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Create", variant="primary", id="create-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "create-btn":
            self._validate_and_create()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel and dismiss the modal."""
        self.dismiss(False)

    def _validate_and_create(self) -> None:
        """Validate inputs and create wallet."""
        # Get form values
        name_input = self.query_one("#wallet-name-input", Input)
        type_select = self.query_one("#wallet-type-select", Select)
        custody_select = self.query_one("#wallet-custody-select", Select)
        description_input = self.query_one("#wallet-description-input", Input)
        notes_input = self.query_one("#wallet-notes-input", Input)
        error_label = self.query_one("#error-msg", Label)

        wallet_name = name_input.value.strip()
        wallet_type = str(type_select.value)
        custody = str(custody_select.value)
        description = description_input.value.strip() or None
        notes = notes_input.value.strip() or None

        # Validation: name must not be empty
        if not wallet_name:
            error_label.update("Error: Wallet name is required")
            name_input.focus()
            return

        # Validation: check if wallet already exists
        app: CryptoApp = self.app  # type: ignore
        try:
            existing_wallets = app.crypto.wallet_query.get_wallets()
            existing_names = {w['wallet_id'] for w in existing_wallets}

            if wallet_name in existing_names:
                error_label.update(f"Error: Wallet '{wallet_name}' already exists")
                name_input.focus()
                return

            # Create the wallet
            app.crypto.wallet_query.add_wallet(
                wallet_id=wallet_name,
                wallet_type=wallet_type,
                custody=custody,
                description=description,
                notes=notes
            )

            # Success - dismiss modal with success status
            self.dismiss(True)

        except Exception as e:
            error_label.update(f"Error: {str(e)}")


class EditWalletModal(ModalScreen[bool]):
    """Modal dialog for editing an existing wallet."""

    CSS = """
    EditWalletModal {
        align: center middle;
    }

    #edit-wallet-container {
        width: 70;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #modal-title {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .form-row {
        height: auto;
        min-height: 4;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    .form-label {
        width: 15;
        padding-right: 1;
        color: $text-muted;
    }

    EditWalletModal Input {
        width: 45;
    }

    EditWalletModal Select {
        width: 45;
    }

    EditWalletModal .readonly-value {
        width: 45;
        color: $text;
    }

    #button-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #button-row Button {
        margin: 0 1;
        min-width: 12;
    }

    .error-message {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, wallet: dict[str, Any]) -> None:
        """Initialize the edit wallet modal.

        Args:
            wallet: Dictionary with keys: wallet_id, type, custody, description, active
        """
        super().__init__()
        self._wallet = wallet
        self._error_message: str = ""

    def compose(self) -> ComposeResult:
        """Compose the edit wallet form."""
        with Container(id="edit-wallet-container"):
            yield Label(f"Edit Wallet: {self._wallet['wallet_id']}", id="modal-title")

            # Error message placeholder (initially empty)
            yield Label("", id="error-msg", classes="error-message")

            # Name field (read-only)
            with Horizontal(classes="form-row"):
                yield Label("Name:", classes="form-label")
                yield Label(self._wallet['wallet_id'], classes="readonly-value")

            # Type field (Select)
            with Horizontal(classes="form-row"):
                yield Label("Type:", classes="form-label")
                yield Select(
                    options=[
                        ("Exchange", "exchange"),
                        ("Hardware Wallet", "hardware"),
                        ("Software Wallet", "software"),
                        ("Mobile Wallet", "mobile"),
                        ("Paper Wallet", "paper"),
                        ("Other", "other"),
                    ],
                    value=self._wallet['type'],
                    id="wallet-type-select"
                )

            # Custody field (Select)
            with Horizontal(classes="form-row"):
                yield Label("Custody:", classes="form-label")
                yield Select(
                    options=[
                        ("Self-Custodied", "self-custodied"),
                        ("Custodial", "custodial"),
                        ("Multisig", "multisig"),
                    ],
                    value=self._wallet['custody'],
                    id="wallet-custody-select"
                )

            # Description field (optional)
            with Horizontal(classes="form-row"):
                yield Label("Description:", classes="form-label")
                yield Input(
                    placeholder="Optional description",
                    value=self._wallet.get('description') or "",
                    id="wallet-description-input"
                )

            # Notes field (optional) - only show if notes exist in wallet dict
            # Note: notes field might not be in all wallet queries, so we check for it
            if 'notes' in self._wallet:
                with Horizontal(classes="form-row"):
                    yield Label("Notes:", classes="form-label")
                    yield Input(
                        placeholder="Optional notes",
                        value=self._wallet.get('notes') or "",
                        id="wallet-notes-input"
                    )

            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Save", variant="primary", id="save-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save-btn":
            self._validate_and_save()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel and dismiss the modal."""
        self.dismiss(False)

    def _validate_and_save(self) -> None:
        """Validate inputs and save wallet updates."""
        # Get form values
        type_select = self.query_one("#wallet-type-select", Select)
        custody_select = self.query_one("#wallet-custody-select", Select)
        description_input = self.query_one("#wallet-description-input", Input)
        error_label = self.query_one("#error-msg", Label)

        wallet_type = str(type_select.value)
        custody = str(custody_select.value)
        description = description_input.value.strip() or None

        # Check if notes input exists (might not be present)
        notes = None
        try:
            notes_input = self.query_one("#wallet-notes-input", Input)
            notes = notes_input.value.strip() or None
        except Exception:
            pass  # Notes field not present, that's ok

        # Build update dict with only changed fields
        updates: dict[str, Any] = {}

        if wallet_type != self._wallet['type']:
            updates['wallet_type'] = wallet_type

        if custody != self._wallet['custody']:
            updates['custody'] = custody

        if description != (self._wallet.get('description') or None):
            updates['description'] = description

        if notes is not None and 'notes' in self._wallet:
            if notes != (self._wallet.get('notes') or None):
                updates['notes'] = notes

        # If no changes, just dismiss
        if not updates:
            self.dismiss(False)
            return

        # Update the wallet
        app: CryptoApp = self.app  # type: ignore
        try:
            app.crypto.wallet_query.update_wallet(
                self._wallet['wallet_id'],
                **updates
            )

            # Success - dismiss modal with success status
            self.dismiss(True)

        except Exception as e:
            error_label.update(f"Error: {str(e)}")


class RenameWalletModal(ModalScreen[bool]):
    """Modal dialog for renaming a wallet with confirmation."""

    CSS = """
    RenameWalletModal {
        align: center middle;
    }

    #rename-wallet-container {
        width: 70;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #modal-title {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .warning-message {
        color: $warning;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }

    .info-message {
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    .form-row {
        height: auto;
        min-height: 4;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    .form-label {
        width: 20;
        padding-right: 1;
        color: $text-muted;
    }

    RenameWalletModal Input {
        width: 40;
    }

    #button-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #button-row Button {
        margin: 0 1;
        min-width: 12;
    }

    .error-message {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, wallet_id: str, transaction_count: int) -> None:
        """Initialize the rename wallet modal.

        Args:
            wallet_id: Current wallet identifier
            transaction_count: Number of ledger transactions that reference this wallet
        """
        super().__init__()
        self._wallet_id = wallet_id
        self._transaction_count = transaction_count

    def compose(self) -> ComposeResult:
        """Compose the rename wallet form."""
        with Container(id="rename-wallet-container"):
            yield Label(f"Rename Wallet: {self._wallet_id}", id="modal-title")

            # Warning about transaction updates
            if self._transaction_count > 0:
                yield Label(
                    f"⚠ This will update {self._transaction_count} transaction(s) in the ledger",
                    classes="warning-message"
                )
            else:
                yield Label(
                    "This wallet has no transactions in the ledger",
                    classes="info-message"
                )

            # Error message placeholder (initially empty)
            yield Label("", id="error-msg", classes="error-message")

            # Current name (read-only)
            with Horizontal(classes="form-row"):
                yield Label("Current Name:", classes="form-label")
                yield Label(self._wallet_id, classes="readonly-value")

            # New name input
            with Horizontal(classes="form-row"):
                yield Label("New Name:", classes="form-label")
                yield Input(
                    placeholder="Enter new wallet name",
                    id="new-name-input"
                )

            # Confirm new name input
            with Horizontal(classes="form-row"):
                yield Label("Confirm New Name:", classes="form-label")
                yield Input(
                    placeholder="Type new name again",
                    id="confirm-name-input"
                )

            # Buttons
            with Horizontal(id="button-row"):
                yield Button("Rename", variant="warning", id="rename-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "rename-btn":
            self._validate_and_rename()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel and dismiss the modal."""
        self.dismiss(False)

    def _validate_and_rename(self) -> None:
        """Validate inputs and rename wallet."""
        # Get form values
        new_name_input = self.query_one("#new-name-input", Input)
        confirm_name_input = self.query_one("#confirm-name-input", Input)
        error_label = self.query_one("#error-msg", Label)

        new_name = new_name_input.value.strip()
        confirm_name = confirm_name_input.value.strip()

        # Validation: new name must not be empty
        if not new_name:
            error_label.update("Error: New wallet name is required")
            new_name_input.focus()
            return

        # Validation: new name must not be the same as current name
        if new_name == self._wallet_id:
            error_label.update("Error: New name must be different from current name")
            new_name_input.focus()
            return

        # Validation: names must match
        if new_name != confirm_name:
            error_label.update("Error: Names do not match. Please type the new name twice.")
            confirm_name_input.focus()
            return

        # Validation: check if new name already exists
        app: CryptoApp = self.app  # type: ignore
        try:
            existing_wallets = app.crypto.wallet_query.get_wallets()
            existing_names = {w['wallet_id'] for w in existing_wallets}

            if new_name in existing_names:
                error_label.update(f"Error: Wallet '{new_name}' already exists")
                new_name_input.focus()
                return

            # Perform the rename
            app.crypto.wallet_query.rename_wallet(self._wallet_id, new_name)

            # Success - dismiss modal with success status
            self.dismiss(True)

        except Exception as e:
            error_label.update(f"Error: {str(e)}")


class MergeWalletsModal(ModalScreen[bool]):
    """Modal dialog for merging a wallet into another with confirmation."""

    CSS = """
    MergeWalletsModal {
        align: center middle;
    }

    #merge-wallet-container {
        width: 70;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #modal-title {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .warning-message {
        color: $warning;
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }

    .info-message {
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    .form-row {
        height: auto;
        min-height: 4;
        layout: horizontal;
        align: left middle;
        margin-bottom: 1;
    }

    .form-label {
        width: 20;
        padding-right: 1;
        color: $text-muted;
    }

    MergeWalletsModal Select {
        width: 40;
    }

    MergeWalletsModal .readonly-value {
        width: 40;
        color: $text;
    }

    #button-row {
        height: auto;
        layout: horizontal;
        align: center middle;
        margin-top: 1;
    }

    #button-row Button {
        margin: 0 1;
        min-width: 12;
    }

    .error-message {
        color: $error;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        source_wallet_id: str,
        transaction_count: int,
        available_targets: list[dict[str, Any]]
    ) -> None:
        """Initialize the merge wallets modal.

        Args:
            source_wallet_id: Wallet to merge from (will be deleted)
            transaction_count: Number of transactions in source wallet
            available_targets: List of wallet dicts that can be merge targets
        """
        super().__init__()
        self._source_wallet_id = source_wallet_id
        self._transaction_count = transaction_count
        self._available_targets = available_targets

    def compose(self) -> ComposeResult:
        """Compose the merge wallets form."""
        with Container(id="merge-wallet-container"):
            yield Label("Merge Wallets", id="modal-title")

            # Warning about merge operation
            if self._transaction_count > 0:
                yield Label(
                    f"⚠ This will merge {self._transaction_count} transaction(s)",
                    classes="warning-message"
                )
            else:
                yield Label(
                    "This wallet has no transactions in the ledger",
                    classes="info-message"
                )

            yield Label(
                "The source wallet will be deleted after merge",
                classes="info-message"
            )

            # Error message placeholder (initially empty)
            yield Label("", id="error-msg", classes="error-message")

            # Source wallet (read-only)
            with Horizontal(classes="form-row"):
                yield Label("Merge From:", classes="form-label")
                yield Label(self._source_wallet_id, classes="readonly-value")

            # Target wallet selector
            with Horizontal(classes="form-row"):
                yield Label("Merge Into:", classes="form-label")
                if self._available_targets:
                    # Build options from available targets
                    options = [
                        (f"{w['wallet_id']} ({w['type']})", w['wallet_id'])
                        for w in self._available_targets
                    ]
                    yield Select(
                        options=options,
                        prompt="Select target wallet",
                        id="target-wallet-select"
                    )
                else:
                    yield Label("No other wallets available", classes="readonly-value")

            # Buttons
            with Horizontal(id="button-row"):
                if self._available_targets:
                    yield Button("Merge", variant="warning", id="merge-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "merge-btn":
            self._validate_and_merge()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_cancel(self) -> None:
        """Cancel and dismiss the modal."""
        self.dismiss(False)

    def _validate_and_merge(self) -> None:
        """Validate selection and perform merge."""
        # Get form values
        target_select = self.query_one("#target-wallet-select", Select)
        error_label = self.query_one("#error-msg", Label)

        # Check if a target is selected
        if target_select.value == Select.BLANK:
            error_label.update("Error: Please select a target wallet")
            target_select.focus()
            return

        target_id = str(target_select.value)

        # Perform the merge
        app: CryptoApp = self.app  # type: ignore
        try:
            app.crypto.wallet_query.merge_wallets(self._source_wallet_id, target_id)

            # Success - dismiss modal with success status
            self.dismiss(True)

        except Exception as e:
            error_label.update(f"Error: {str(e)}")


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
            AND (deleted = 0 OR deleted IS NULL)
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
            self.app.call_from_thread(self._handle_wallet_data, wallets)

        except Exception as e:
            self.app.call_from_thread(self._show_error, str(e))

    def _handle_wallet_data(self, wallets: list[dict[str, Any]]) -> None:
        """Handle wallet data loaded from background thread."""
        self._wallets = wallets

        if not wallets:
            self._show_empty()
        else:
            self._show_wallet_table()

    def action_new_wallet(self) -> None:
        """Show modal to create a new wallet."""
        def handle_result(success: bool) -> None:
            if success:
                self.notify("Wallet created successfully", severity="information")
                # Refresh wallet list
                self._show_loading()
                self.load_wallet_data()

        self.app.push_screen(CreateWalletModal(), handle_result)

    def action_edit_wallet(self) -> None:
        """Show modal to edit selected wallet."""
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to edit", severity="warning")
            return

        # Get the selected wallet ID from the table row key
        wallet_id = str(table.get_row_at(table.cursor_row)[0])  # First column is wallet_id

        # Find the wallet in our cached list
        wallet = next((w for w in self._wallets if w['wallet_id'] == wallet_id), None)
        if wallet is None:
            self.notify(f"Wallet '{wallet_id}' not found", severity="error")
            return

        def handle_result(success: bool) -> None:
            if success:
                self.notify("Wallet updated successfully", severity="information")
            # Always refresh wallet list (even if cancelled, to ensure consistency)
            self._show_loading()
            self.load_wallet_data()

        self.app.push_screen(EditWalletModal(wallet), handle_result)

    def action_toggle_active(self) -> None:
        """Toggle active/inactive status for selected wallet."""
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to toggle", severity="warning")
            return

        # Get the selected wallet ID from the table row key
        wallet_id = str(table.get_row_at(table.cursor_row)[0])  # First column is wallet_id

        # Find the wallet in our cached list to get current active status
        wallet = next((w for w in self._wallets if w['wallet_id'] == wallet_id), None)
        if wallet is None:
            self.notify(f"Wallet '{wallet_id}' not found", severity="error")
            return

        # Get current active status (handle both bool and int representations)
        current_active = wallet['active']
        if isinstance(current_active, int):
            current_active = bool(current_active)

        # Toggle the status
        new_active = not current_active

        # Update the wallet
        app: CryptoApp = self.app  # type: ignore
        try:
            app.crypto.wallet_query.update_wallet(wallet_id, active=new_active)

            # Show appropriate notification
            status_text = "activated" if new_active else "deactivated"
            self.notify(f"Wallet '{wallet_id}' {status_text}", severity="information")

            # Refresh wallet list
            self._show_loading()
            self.load_wallet_data()

        except Exception as e:
            self.notify(f"Error toggling wallet status: {str(e)}", severity="error")

    def action_rename_wallet(self) -> None:
        """Show modal to rename selected wallet."""
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to rename", severity="warning")
            return

        # Get the selected wallet ID from the table row key
        wallet_id = str(table.get_row_at(table.cursor_row)[0])  # First column is wallet_id

        # Get transaction count for this wallet
        app: CryptoApp = self.app  # type: ignore
        query = "SELECT COUNT(*) FROM ledger WHERE exchange = :wallet_id AND (deleted = 0 OR deleted IS NULL)"
        tx_count = app.crypto.backend.execute_scalar(query, {"wallet_id": wallet_id}) or 0

        def handle_result(success: bool) -> None:
            if success:
                self.notify("Wallet renamed successfully", severity="information")
            # Refresh wallet list
            self._show_loading()
            self.load_wallet_data()

        self.app.push_screen(RenameWalletModal(wallet_id, tx_count), handle_result)

    def action_merge_wallets(self) -> None:
        """Show modal to merge selected wallet into another."""
        table = self.query_one("#wallet-table", DataTable)
        if table.cursor_row is None:
            self.notify("Please select a wallet to merge", severity="warning")
            return

        # Get the selected wallet ID (source wallet)
        source_wallet_id = str(table.get_row_at(table.cursor_row)[0])

        # Get transaction count for source wallet
        app: CryptoApp = self.app  # type: ignore
        query = "SELECT COUNT(*) FROM ledger WHERE exchange = :wallet_id AND (deleted = 0 OR deleted IS NULL)"
        tx_count = app.crypto.backend.execute_scalar(query, {"wallet_id": source_wallet_id}) or 0

        # Get all other wallets as potential merge targets (exclude source)
        available_targets = [w for w in self._wallets if w['wallet_id'] != source_wallet_id]

        if not available_targets:
            self.notify("No other wallets available to merge into", severity="warning")
            return

        def handle_result(success: bool) -> None:
            if success:
                self.notify(
                    f"Wallet '{source_wallet_id}' merged successfully",
                    severity="information"
                )
            # Refresh wallet list
            self._show_loading()
            self.load_wallet_data()

        self.app.push_screen(
            MergeWalletsModal(source_wallet_id, tx_count, available_targets),
            handle_result
        )
