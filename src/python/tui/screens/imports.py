"""Import wizard screen for importing transaction CSV files.

Three-step wizard:
1. File selection + format detection
2. Configuration (wallet-name, withdraw-to, dry-run)
3. Preview + Execute + Results
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    DirectoryTree,
    Input,
    Label,
    Select,
    Static,
)

if TYPE_CHECKING:
    from textual.worker import Worker

from tui.screens.record_transaction import NEW_WALLET_SENTINEL

# Map select_id -> (new-wallet-row-id, new-wallet-input-id) for the wizard.
_WIZARD_WALLET_MAP: dict[str, tuple[str, str]] = {
    "select-withdraw-to": ("new-withdraw-to-row", "new-withdraw-to-input"),
    "select-wallet-name": ("new-wallet-name-row", "new-wallet-name-input"),
}


class FilteredDirectoryTree(DirectoryTree):
    """DirectoryTree that only shows directories and CSV/TXT files."""

    def filter_paths(self, paths: list[Path]) -> list[Path]:
        """Filter to only show directories and .csv/.txt files."""
        return [
            p for p in paths
            if p.is_dir() or p.suffix.lower() in (".csv", ".txt")
        ]


class FilePickerModal(ModalScreen[Path | None]):
    """Modal dialog for browsing and selecting a CSV file."""

    CSS = """
    FilePickerModal {
        align: center middle;
    }

    #file-picker-container {
        width: 80%;
        height: 80%;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #file-picker-title {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    #file-picker-tree {
        height: 1fr;
        margin-bottom: 1;
        border: solid $primary;
    }

    #file-picker-selected {
        height: auto;
        margin-bottom: 1;
        color: $text-muted;
    }

    #file-picker-actions {
        height: auto;
        align: center middle;
    }
    """

    def __init__(self) -> None:
        """Initialize the file picker modal."""
        super().__init__()
        self.selected_path: Path | None = None

    def compose(self) -> ComposeResult:
        """Compose the file picker UI."""
        with Container(id="file-picker-container"):
            yield Label("Select a CSV File", id="file-picker-title")
            yield FilteredDirectoryTree(Path.home(), id="file-picker-tree")
            yield Label("No file selected", id="file-picker-selected")
            with Horizontal(id="file-picker-actions"):
                yield Button("Select", id="btn-fp-select", variant="primary", disabled=True)
                yield Button("Cancel", id="btn-fp-cancel", variant="default")

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection in the directory tree."""
        self.selected_path = event.path
        self.query_one("#file-picker-selected", Label).update(
            f"Selected: [cyan]{event.path}[/cyan]"
        )
        self.query_one("#btn-fp-select", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-fp-select":
            self.dismiss(self.selected_path)
        elif event.button.id == "btn-fp-cancel":
            self.dismiss(None)


class ImportWizardScreen(Screen[None]):
    """Multi-step wizard for importing CSV transaction files."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
        Binding("i", "focus_file_input", "Select File", show=False),
    ]

    CSS = """
    ImportWizardScreen {
        align: center middle;
    }

    #wizard-container {
        width: 90%;
        max-width: 120;
        height: auto;
        background: $surface;
        border: solid $accent;
        padding: 1 2;
    }

    #wizard-header {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $accent;
    }

    #wizard-steps {
        height: auto;
        text-align: center;
        margin-bottom: 1;
        color: $text-muted;
    }

    #wizard-content {
        height: auto;
        min-height: 20;
        max-height: 35;
        overflow-y: auto;
    }

    #wizard-actions {
        height: auto;
        margin-top: 1;
        align: center middle;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .form-label {
        width: 20;
        height: auto;
        content-align: right middle;
        margin-right: 2;
    }

    .form-input {
        width: 1fr;
    }

    #detection-result {
        height: auto;
        margin-top: 1;
        padding: 1;
        background: $surface-darken-1;
        border: solid $primary;
    }

    #preview-table {
        height: auto;
        min-height: 10;
        max-height: 20;
        margin-top: 1;
    }

    #results-panel {
        height: auto;
        padding: 1;
        margin-top: 1;
        background: $surface-darken-1;
        border: solid $success;
    }

    #error-panel {
        height: auto;
        padding: 1;
        margin-top: 1;
        background: $surface-darken-1;
        border: solid $error;
        color: $error;
    }

    """

    def __init__(self) -> None:
        """Initialize import wizard."""
        super().__init__()
        self.current_step = 1
        self.file_path: str | None = None
        self.parser: Any = None  # BaseImporter instance
        self.parsed_transactions: list[dict[str, Any]] = []
        self.wallet_names: list[str] = []
        self.dry_run_enabled = True  # Store dry-run state (default True for safety)

    def compose(self) -> ComposeResult:
        """Compose the import wizard UI."""
        with Container(id="wizard-container"):
            yield Label("Import Transactions", id="wizard-header")
            yield Label("Step 1 of 3: File Selection", id="wizard-steps")

            with Vertical(id="wizard-content"):
                yield Label("Loading...", id="content-placeholder")

            with Horizontal(id="wizard-actions"):
                yield Button("Back", id="btn-back", variant="default", disabled=True)
                yield Button("Next", id="btn-next", variant="primary", disabled=True)
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        """Load initial step after mounting."""
        self.load_wallets()
        self.show_step_1()

    @work(thread=True)
    def load_wallets(self) -> None:
        """Load wallet names from database in background."""
        try:
            from tui.app import CryptoApp
            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                return

            # Get wallet names
            wallets = app.crypto.get_wallets(active_only=False)
            wallet_names = [w['wallet_id'] for w in wallets if w.get('wallet_id')]

            # Update UI from thread
            app.call_from_thread(self._update_wallet_list, wallet_names)
        except Exception as e:
            self.log.error(f"Failed to load wallets: {e}")

    def _update_wallet_list(self, wallet_names: list[str]) -> None:
        """Update wallet list (called from thread)."""
        self.wallet_names = wallet_names

    def _load_wallet_choices(self) -> list[tuple[str, str]]:
        """Build (label, value) choices from loaded wallet names + sentinel."""
        choices: list[tuple[str, str]] = [
            (name, name) for name in self.wallet_names
        ]
        choices.append(("+ New Wallet...", NEW_WALLET_SENTINEL))
        return choices

    def show_step_1(self) -> None:
        """Show step 1: File selection."""
        self.current_step = 1
        steps_label = self.query_one("#wizard-steps", Label)
        steps_label.update("Step 1 of 3: File Selection")

        content = self.query_one("#wizard-content", Vertical)
        content.remove_children()

        # File path input with Browse button
        row = Horizontal(classes="form-row")
        content.mount(row)
        row.mount(Label("File Path:", classes="form-label"))
        row.mount(Input(
            placeholder="/path/to/export.csv",
            id="input-file-path",
            classes="form-input"
        ))
        row.mount(Button("Browse", id="btn-browse", variant="default"))

        # Detect button
        row2 = Horizontal(classes="form-row")
        content.mount(row2)
        row2.mount(Label("", classes="form-label"))  # Spacer
        row2.mount(Button("Detect Format", id="btn-detect", variant="primary"))

        # Detection result container (initially empty)
        content.mount(Container(id="detection-result"))

        # Update action buttons
        self.query_one("#btn-back", Button).disabled = True
        self.query_one("#btn-next", Button).disabled = True

    def _mount_wizard_wallet_selector(
        self,
        container: Vertical,
        label_text: str,
        select_id: str,
        *,
        allow_blank: bool = False,
    ) -> None:
        """Mount a wallet Select dropdown with '+ New Wallet...' fallback Input.

        Uses the same show/hide pattern as RecordTransactionScreen.
        """
        row_id, input_id = _WIZARD_WALLET_MAP[select_id]
        choices = self._load_wallet_choices()
        has_wallets = len(choices) > 1  # more than just the sentinel

        if allow_blank:
            default_value = Select.BLANK
        else:
            default_value = choices[0][1] if has_wallets else NEW_WALLET_SENTINEL

        row = Horizontal(classes="form-row")
        container.mount(row)
        row.mount(Label(label_text, classes="form-label"))
        row.mount(Select(choices, value=default_value, id=select_id,
                         allow_blank=allow_blank))

        placeholder = (
            "No wallets yet - type a name below"
            if not has_wallets
            else "Enter wallet name"
        )
        new_row = Horizontal(classes="form-row new-wallet-row", id=row_id)
        container.mount(new_row)
        new_row.mount(Label("New Wallet:", classes="form-label"))
        new_row.mount(Input(id=input_id, placeholder=placeholder))

        # Hide by default, show only when sentinel is the default (DB empty).
        new_row.display = (default_value == NEW_WALLET_SENTINEL)

    def show_step_2(self) -> None:
        """Show step 2: Configuration."""
        self.current_step = 2
        steps_label = self.query_one("#wizard-steps", Label)
        steps_label.update("Step 2 of 3: Configuration")

        content = self.query_one("#wizard-content", Vertical)
        content.remove_children()

        # Show detected parser info
        if self.parser:
            info = Static(
                f"[cyan]Format:[/cyan] {self.parser.name}\n"
                f"[cyan]Type:[/cyan] {self.parser.source_type}\n"
                f"[cyan]Transactions:[/cyan] {len(self.parsed_transactions)}"
            )
            content.mount(info)

        # Wallet name selector (required for wallet imports)
        if self.parser and self.parser.source_type == 'wallet':
            self._mount_wizard_wallet_selector(
                content, "Wallet Name: *", "select-wallet-name"
            )

        # Withdraw-to selector (optional for all imports)
        self._mount_wizard_wallet_selector(
            content, "Withdraw To:", "select-withdraw-to", allow_blank=True
        )

        # Dry-run checkbox (checked by default for safety)
        row4 = Horizontal(classes="form-row")
        content.mount(row4)
        row4.mount(Label("Dry Run:", classes="form-label"))
        row4.mount(Checkbox(
            "Preview only (don't import)",
            id="checkbox-dry-run",
            value=True
        ))

        # Update action buttons
        self.query_one("#btn-back", Button).disabled = False
        self.query_one("#btn-next", Button).disabled = False

    def on_select_changed(self, event: Select.Changed) -> None:
        """Toggle new-wallet input row visibility on Select change."""
        select_id = event.select.id
        if select_id in _WIZARD_WALLET_MAP:
            row_id, _ = _WIZARD_WALLET_MAP[select_id]
            try:
                new_row = self.query_one(f"#{row_id}", Horizontal)
                if event.value == NEW_WALLET_SENTINEL:
                    new_row.display = True
                elif event.value is not Select.BLANK:
                    new_row.display = False
            except Exception:
                pass

    def _get_wizard_wallet_value(self, select_id: str) -> str | None:
        """Read the effective wallet name from a wizard wallet selector.

        Returns stripped name from the Select, or from the fallback Input
        if '+ New Wallet...' is selected.  Returns None if blank.
        """
        _, input_id = _WIZARD_WALLET_MAP[select_id]
        try:
            sel = self.query_one(f"#{select_id}", Select)
            val = sel.value
            if val == NEW_WALLET_SENTINEL or val is Select.BLANK:
                inp = self.query_one(f"#{input_id}", Input)
                text = inp.value.strip()
                return text if text else None
            return str(val).strip() or None
        except Exception:
            return None

    def show_step_3(self) -> None:
        """Show step 3: Preview and execute."""
        self.current_step = 3
        steps_label = self.query_one("#wizard-steps", Label)
        steps_label.update("Step 3 of 3: Preview & Import")

        content = self.query_one("#wizard-content", Vertical)
        content.remove_children()

        # Show preview table with first 10 transactions
        preview_txs = self.parsed_transactions[:10]

        table: DataTable[str] = DataTable(id="preview-table")
        content.mount(table)

        # Add columns
        table.add_column("Type", key="type")
        table.add_column("Date", key="date")
        table.add_column("Amount", key="amount")
        table.add_column("Currency", key="currency")
        table.add_column("Exchange", key="exchange")
        table.add_column("Fee", key="fee")

        # Add rows
        for tx in preview_txs:
            trans_type = tx.get('trans_type', '')
            date = tx.get('created_date', '')

            # Determine amount and currency
            if tx.get('buy'):
                amount = f"{tx['buy']:.8f}"
                curr = tx.get('buy_curr', '')
            else:
                amount = f"{tx.get('sell', 0):.8f}"
                curr = tx.get('sell_curr', '')

            exchange = tx.get('exchange', '')
            fee = f"{tx.get('fee', 0):.4f}" if tx.get('fee') else ""

            table.add_row(trans_type, date, amount, curr, exchange, fee)

        # Show count info
        if len(self.parsed_transactions) > 10:
            content.mount(Label(
                f"Showing first 10 of {len(self.parsed_transactions)} transactions"
            ))
        else:
            content.mount(Label(f"{len(self.parsed_transactions)} transactions ready to import"))

        # Update action buttons
        self.query_one("#btn-back", Button).disabled = False
        next_btn = self.query_one("#btn-next", Button)
        next_btn.label = "Import"
        next_btn.disabled = False

    def show_results(self, result: dict[str, int], is_dry_run: bool) -> None:
        """Show import results."""
        steps_label = self.query_one("#wizard-steps", Label)
        steps_label.update("Import Complete")

        content = self.query_one("#wizard-content", Vertical)
        content.remove_children()

        # Results panel
        if is_dry_run:
            results_text = (
                f"[cyan]Dry Run Complete[/cyan]\n\n"
                f"Would import: {result['imported']} transactions\n"
                f"Would skip: {result.get('skipped', 0)} transactions"
            )
        else:
            results_text = (
                f"[green]Import Successful[/green]\n\n"
                f"Imported: {result['imported']} transactions\n"
                f"Skipped: {result.get('skipped', 0)} transactions"
            )

        results_panel = Static(results_text, id="results-panel")
        content.mount(results_panel)

        # Update action buttons
        self.query_one("#btn-back", Button).disabled = True
        self.query_one("#btn-next", Button).disabled = True

        # Change Cancel to Close
        cancel_btn = self.query_one("#btn-cancel", Button)
        cancel_btn.label = "Close"

    def show_error(self, message: str) -> None:
        """Show error message in content area."""
        content = self.query_one("#wizard-content", Vertical)

        # Check if error panel already exists
        try:
            error_panel = content.query_one("#error-panel")
            error_panel.remove()
        except Exception:
            pass

        error_panel = Static(f"[bold]Error:[/bold] {message}", id="error-panel")
        content.mount(error_panel)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press."""
        button_id = event.button.id

        if button_id == "btn-cancel":
            if self.current_step >= 4:  # Results shown
                self.app.pop_screen()
            else:
                self.app.pop_screen()

        elif button_id == "btn-back":
            if self.current_step == 2:
                self.show_step_1()
            elif self.current_step == 3:
                self.show_step_2()

        elif button_id == "btn-next":
            if self.current_step == 1:
                # Step 1 -> 2: show configuration
                self.show_step_2()
            elif self.current_step == 2:
                # Step 2 -> 3: validate and show preview
                self.prepare_preview()
            elif self.current_step == 3:
                # Step 3 -> Import: execute import
                self.execute_import()

        elif button_id == "btn-browse":
            self.app.push_screen(FilePickerModal(), callback=self._on_file_selected)

        elif button_id == "btn-detect":
            self.detect_format()

    def _on_file_selected(self, path: Path | None) -> None:
        """Handle file selection from the file picker modal."""
        if path is not None:
            try:
                file_input = self.query_one("#input-file-path", Input)
                file_input.value = str(path)
            except Exception:
                pass

    def detect_format(self) -> None:
        """Detect file format and parse transactions."""
        file_input = self.query_one("#input-file-path", Input)
        file_path = file_input.value.strip()

        if not file_path:
            self.show_error("Please enter a file path")
            return

        # Expand ~ to home directory
        file_path = str(Path(file_path).expanduser())

        if not Path(file_path).exists():
            self.show_error(f"File not found: {file_path}")
            return

        self.file_path = file_path

        # Detect parser
        self.detect_parser_async()

    @work(thread=True)
    def detect_parser_async(self) -> None:
        """Detect parser and parse file in background."""
        try:
            from imports import detect_parser

            assert self.file_path is not None

            parser = detect_parser(self.file_path)
            if parser is None:
                self.app.call_from_thread(
                    self.show_error,
                    "Could not detect file format. Please check the file and try again."
                )
                return

            # Parse file
            colnames, transactions = parser.parse(self.file_path, None, None)

            if not transactions:
                self.app.call_from_thread(
                    self.show_error,
                    "No transactions found in file"
                )
                return

            # Update UI from thread
            self.app.call_from_thread(
                self._show_detection_result,
                parser,
                len(transactions)
            )

            # Store parsed data
            self.parser = parser
            self.parsed_transactions = transactions

        except Exception as e:
            self.log.error(f"Detection failed: {e}")
            self.app.call_from_thread(
                self.show_error,
                f"Failed to parse file: {str(e)}"
            )

    def _show_detection_result(self, parser: Any, tx_count: int) -> None:
        """Show detection result in UI (called from thread)."""
        result_container = self.query_one("#detection-result", Container)
        result_container.remove_children()

        result_text = (
            f"[green]✓[/green] Detected format: [cyan]{parser.name}[/cyan]\n"
            f"Type: {parser.source_type}\n"
            f"Transactions found: {tx_count}"
        )
        result_container.mount(Static(result_text))

        # Enable Next button
        self.query_one("#btn-next", Button).disabled = False

    def prepare_preview(self) -> None:
        """Validate configuration and prepare preview."""
        # Store dry-run state before leaving step 2
        dry_run_checkbox = self.query_one("#checkbox-dry-run", Checkbox)
        self.dry_run_enabled = dry_run_checkbox.value

        # Validate wallet-name for wallet imports
        wallet_name = None
        if self.parser and self.parser.source_type == 'wallet':
            wallet_name = self._get_wizard_wallet_value("select-wallet-name")
            if not wallet_name:
                self.show_error("Wallet imports require a wallet name")
                return

        # Get withdraw-to value
        withdraw_to = self._get_wizard_wallet_value("select-withdraw-to")

        # Re-parse with configuration
        self.reparse_with_config(wallet_name, withdraw_to)

    @work(thread=True)
    def reparse_with_config(self, wallet_name: str | None, withdraw_to: str | None) -> None:
        """Re-parse file with configuration applied."""
        try:
            assert self.parser is not None
            assert self.file_path is not None

            # Parse with configuration
            colnames, transactions = self.parser.parse(self.file_path, wallet_name, withdraw_to)

            self.parsed_transactions = transactions

            # Show preview
            self.app.call_from_thread(self.show_step_3)

        except Exception as e:
            self.log.error(f"Re-parse failed: {e}")
            self.app.call_from_thread(
                self.show_error,
                f"Failed to parse with configuration: {str(e)}"
            )

    @work(thread=True)
    def execute_import(self) -> None:
        """Execute the import in background."""
        try:
            from tui.app import CryptoApp
            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self.show_error,
                    "Database not connected"
                )
                return

            # Use stored dry-run state (captured in prepare_preview from step 2)
            is_dry_run = self.dry_run_enabled

            if is_dry_run:
                # Just show preview results
                result = {
                    'imported': len(self.parsed_transactions),
                    'skipped': 0
                }
                self.app.call_from_thread(self.show_results, result, True)
            else:
                # Actually import
                result = app.crypto.import_transactions(self.parsed_transactions)
                self.app.call_from_thread(self.show_results, result, False)

                # Notify parent to refresh
                self.app.call_from_thread(
                    lambda: app.notify(
                        f"Imported {result['imported']} transactions successfully",
                        severity="success"
                    )
                )

        except Exception as e:
            self.log.error(f"Import failed: {e}")
            self.app.call_from_thread(
                self.show_error,
                f"Import failed: {str(e)}"
            )

    def action_focus_file_input(self) -> None:
        """Focus the file input field."""
        try:
            file_input = self.query_one("#input-file-path", Input)
            file_input.focus()
        except Exception:
            pass
