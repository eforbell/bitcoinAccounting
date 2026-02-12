"""Visualization screen for generating Bitcoin portfolio charts.

Supports Orange Plot, Balance Chart, Custody Chart, All Charts, and PDF Report
generation with configurable date ranges, DPI, log scale, and cost basis options.
"""

from __future__ import annotations

import platform
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

if TYPE_CHECKING:
    pass


class VisualizationScreen(Screen[None]):
    """Screen for generating Bitcoin portfolio visualizations."""

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back", show=True),
    ]

    CSS = """
    VisualizationScreen {
        align: center top;
        padding: 1 2;
    }

    #viz-container {
        width: 100%;
        height: auto;
    }

    .section-header {
        height: auto;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .form-section {
        height: auto;
        margin-bottom: 2;
        padding: 1;
        background: $surface;
        border: solid $primary;
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

    .checkbox-row {
        height: auto;
        margin-bottom: 1;
        margin-left: 22;
    }

    #custom-dates {
        height: auto;
    }

    #results-section {
        height: auto;
        margin-bottom: 2;
        padding: 1;
        background: $surface;
        border: solid $primary;
    }

    #results-header {
        height: auto;
        margin-bottom: 1;
        color: $accent;
        text-style: bold;
    }

    .result-item {
        height: auto;
        margin-bottom: 0;
    }

    #actions-section {
        height: auto;
        align: center middle;
    }

    #status-message {
        height: auto;
        margin-bottom: 1;
        padding: 1;
        background: $surface-darken-1;
    }

    .success {
        border: solid $success;
        color: $success;
    }

    .error {
        border: solid $error;
        color: $error;
    }

    .info {
        border: solid $accent;
        color: $accent;
    }
    """

    def __init__(self) -> None:
        """Initialize visualization screen."""
        super().__init__()
        self.generated_files: dict[str, Path] = {}

    def compose(self) -> ComposeResult:
        """Compose the visualization screen UI."""
        with VerticalScroll(id="viz-container"):
            yield Label("Visualizations", classes="section-header")

            # Chart type selection
            with Container(classes="form-section"):
                yield Label("Chart Options", classes="section-header")

                # Chart type selector
                with Horizontal(classes="form-row"):
                    yield Label("Chart Type:", classes="form-label")
                    yield Select(
                        options=[
                            ("All Charts", "all"),
                            ("Orange Plot", "orange"),
                            ("Balance Chart", "balance"),
                            ("Custody Chart", "custody"),
                            ("PDF Report", "pdf"),
                        ],
                        value="all",
                        id="select-chart-type",
                        classes="form-input",
                    )

                # Date range preset
                with Horizontal(classes="form-row"):
                    yield Label("Date Range:", classes="form-label")
                    yield Select(
                        options=[
                            ("All Time", "all"),
                            ("Year to Date", "ytd"),
                            ("Last 1 Year", "1y"),
                            ("Last 5 Years", "5y"),
                            ("Custom", "custom"),
                        ],
                        value="all",
                        id="select-date-range",
                        classes="form-input",
                    )

                # Custom date inputs (initially hidden)
                with Container(id="custom-dates"):
                    with Horizontal(classes="form-row"):
                        yield Label("Start Date:", classes="form-label")
                        yield Input(
                            placeholder="YYYY-MM-DD",
                            id="input-start-date",
                            classes="form-input",
                        )
                    with Horizontal(classes="form-row"):
                        yield Label("End Date:", classes="form-label")
                        yield Input(
                            placeholder="YYYY-MM-DD",
                            id="input-end-date",
                            classes="form-input",
                        )

                # DPI selector
                with Horizontal(classes="form-row"):
                    yield Label("DPI:", classes="form-label")
                    yield Select(
                        options=[
                            ("72 (Draft)", 72),
                            ("150 (Standard)", 150),
                            ("300 (High Quality)", 300),
                            ("600 (Print)", 600),
                        ],
                        value=300,
                        id="select-dpi",
                        classes="form-input",
                    )

                # Output directory
                with Horizontal(classes="form-row"):
                    yield Label("Output Dir:", classes="form-label")
                    yield Input(
                        value="output/viz/",
                        id="input-output-dir",
                        classes="form-input",
                    )

                # Checkboxes for options
                with Horizontal(classes="checkbox-row"):
                    yield Checkbox("Include cost basis overlay", value=True, id="cb-cost-basis")

                with Horizontal(classes="checkbox-row"):
                    yield Checkbox("Use log scale", value=False, id="cb-log-scale")

            # Status message
            yield Static("", id="status-message")

            # Results section (initially hidden)
            with Container(id="results-section"):
                yield Label("Generated Files", id="results-header")
                yield Static("", id="results-list")

            # Action buttons
            with Horizontal(id="actions-section"):
                yield Button("Generate", id="btn-generate", variant="primary")
                yield Button("Open Files", id="btn-open", variant="default")
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        """Configure screen after mounting."""
        self.app.sub_title = "Visualizations"
        # Hide custom dates and results initially
        custom_dates = self.query_one("#custom-dates", Container)
        custom_dates.display = False
        results = self.query_one("#results-section", Container)
        results.display = False

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select widget changes."""
        if event.select.id == "select-date-range":
            # Show/hide custom date inputs
            custom_dates = self.query_one("#custom-dates", Container)
            custom_dates.display = (event.value == "custom")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        button_id = event.button.id

        if button_id == "btn-cancel":
            self.app.pop_screen()
        elif button_id == "btn-generate":
            self.start_generation()
        elif button_id == "btn-open":
            self.open_generated_files()

    def start_generation(self) -> None:
        """Validate inputs and start chart generation."""
        # Get form values
        chart_type_select = self.query_one("#select-chart-type", Select)
        date_range_select = self.query_one("#select-date-range", Select)

        chart_type = str(chart_type_select.value) if chart_type_select.value is not None else "all"
        date_range_preset = str(date_range_select.value) if date_range_select.value is not None else "all"

        # Resolve date range
        if date_range_preset == "custom":
            start_input = self.query_one("#input-start-date", Input)
            end_input = self.query_one("#input-end-date", Input)
            start_str = start_input.value.strip()
            end_str = end_input.value.strip()

            if not start_str:
                self._show_error("Start date is required for custom range")
                return

            try:
                start_date = datetime.strptime(start_str, "%Y-%m-%d")
            except ValueError:
                self._show_error("Invalid start date format. Use YYYY-MM-DD")
                return

            if end_str:
                try:
                    end_date = datetime.strptime(end_str, "%Y-%m-%d")
                except ValueError:
                    self._show_error("Invalid end date format. Use YYYY-MM-DD")
                    return
            else:
                end_date = datetime.now()

            if start_date > end_date:
                self._show_error("Start date must be before end date")
                return

            date_range: str | tuple[datetime, datetime] = (start_date, end_date)
        else:
            date_range = date_range_preset

        # Get options
        dpi_select = self.query_one("#select-dpi", Select)
        dpi = int(dpi_select.value) if dpi_select.value is not None else 300

        cost_basis_cb = self.query_one("#cb-cost-basis", Checkbox)
        log_scale_cb = self.query_one("#cb-log-scale", Checkbox)

        output_dir_input = self.query_one("#input-output-dir", Input)
        output_dir = output_dir_input.value.strip() or "output/viz/"

        is_pdf = (chart_type == "pdf")

        # Show generating status
        self._show_info("Generating charts... This may take a moment.")

        # Disable generate button during generation
        gen_btn = self.query_one("#btn-generate", Button)
        gen_btn.disabled = True

        # Start async generation
        self.generate_charts_async(
            chart_type=chart_type,
            date_range=date_range,
            dpi=dpi,
            include_cost_basis=cost_basis_cb.value,
            log_scale=log_scale_cb.value,
            output_dir=output_dir,
            is_pdf=is_pdf,
        )

    @work(thread=True)
    def generate_charts_async(
        self,
        chart_type: str,
        date_range: str | tuple[datetime, datetime],
        dpi: int,
        include_cost_basis: bool,
        log_scale: bool,
        output_dir: str,
        is_pdf: bool,
    ) -> None:
        """Generate charts in background thread."""
        try:
            from tui.app import CryptoApp
            app = self.app
            assert isinstance(app, CryptoApp)

            if app.crypto is None:
                self.app.call_from_thread(
                    self._show_error,
                    "Database not connected"
                )
                self.app.call_from_thread(self._enable_generate)
                return

            backend = app.crypto.backend

            from viz import BalanceChart, CustodyChart, OrangePlot, PDFReport, VizConfig

            output_path = Path(output_dir).expanduser()
            # PDF is not a valid chart_type for VizConfig - use 'all' for PDF reports
            chart_types_list = ["all"] if (chart_type in ("all", "pdf")) else [chart_type]

            config = VizConfig(
                date_range=date_range,
                output_dir=output_path,
                chart_types=chart_types_list,
                include_cost_basis=include_cost_basis,
                log_scale=log_scale,
                dpi=dpi,
            )

            generated: dict[str, Path] = {}
            errors: dict[str, str] = {}

            if is_pdf:
                try:
                    report = PDFReport(backend, config)
                    result_path = report.generate()
                    generated["PDF Report"] = result_path
                except ImportError:
                    errors["PDF Report"] = "reportlab not installed. Install with: pip install reportlab"
                except Exception as e:
                    errors["PDF Report"] = str(e)
            else:
                # Determine which charts to generate
                if chart_type == "all":
                    types_to_gen = ["orange", "balance", "custody"]
                else:
                    types_to_gen = [chart_type]

                for ct in types_to_gen:
                    try:
                        if ct == "orange":
                            chart = OrangePlot(backend, config)
                            result_path = chart.generate()
                            generated["Orange Plot"] = result_path
                        elif ct == "balance":
                            chart_obj = BalanceChart(backend, config)
                            result_path = chart_obj.generate()
                            generated["Balance Chart"] = result_path
                        elif ct == "custody":
                            custody = CustodyChart(backend, config)
                            result_path = custody.generate()
                            generated["Custody Chart"] = result_path
                    except Exception as e:
                        label = {"orange": "Orange Plot", "balance": "Balance Chart", "custody": "Custody Chart"}.get(ct, ct)
                        errors[label] = str(e)

            # Update UI
            self.app.call_from_thread(self._show_results, generated, errors)
            self.app.call_from_thread(self._enable_generate)

        except Exception as e:
            self.app.call_from_thread(
                self._show_error,
                f"Chart generation failed: {str(e)}"
            )
            self.app.call_from_thread(self._enable_generate)

    def _show_results(self, generated: dict[str, Path], errors: dict[str, str]) -> None:
        """Display generation results."""
        self.generated_files = generated

        results_section = self.query_one("#results-section", Container)
        results_list = self.query_one("#results-list", Static)

        if not generated and errors:
            # All failed
            error_lines = "\n".join(f"  [red]{name}:[/red] {err}" for name, err in errors.items())
            self._show_error(f"All charts failed to generate:\n{error_lines}")
            results_section.display = False
            return

        # Build results text
        lines: list[str] = []
        for name, path in generated.items():
            lines.append(f"  [green]{name}:[/green] {path}")

        if errors:
            lines.append("")
            for name, err in errors.items():
                lines.append(f"  [red]{name} (failed):[/red] {err}")

        results_list.update("\n".join(lines))
        results_section.display = True

        # Show success status
        count = len(generated)
        status_text = f"Generated {count} chart{'s' if count != 1 else ''} successfully"
        if errors:
            status_text += f" ({len(errors)} failed)"
        self._show_success(status_text)

        # Notify
        self.app.notify(
            f"Generated {count} chart{'s' if count != 1 else ''}",
            severity="information",
        )

    def _enable_generate(self) -> None:
        """Re-enable the generate button."""
        gen_btn = self.query_one("#btn-generate", Button)
        gen_btn.disabled = False

    def open_generated_files(self) -> None:
        """Open generated files in system viewer."""
        if not self.generated_files:
            self._show_error("No files to open. Generate charts first.")
            return

        system = platform.system()
        for name, file_path in self.generated_files.items():
            try:
                if system == "Darwin":
                    subprocess.Popen(["open", str(file_path)])
                elif system == "Linux":
                    subprocess.Popen(["xdg-open", str(file_path)])
                elif system == "Windows":
                    subprocess.Popen(["start", str(file_path)], shell=True)
            except Exception as e:
                self._show_error(f"Could not open {name}: {e}")
                return

        self._show_info(f"Opened {len(self.generated_files)} file(s) in system viewer")

    def _show_error(self, message: str) -> None:
        """Show error message."""
        status = self.query_one("#status-message", Static)
        status.update(f"[bold]Error:[/bold] {message}")
        status.remove_class("success", "info")
        status.add_class("error")

    def _show_success(self, message: str) -> None:
        """Show success message."""
        status = self.query_one("#status-message", Static)
        status.update(f"[bold]Success![/bold] {message}")
        status.remove_class("error", "info")
        status.add_class("success")

    def _show_info(self, message: str) -> None:
        """Show info message."""
        status = self.query_one("#status-message", Static)
        status.update(f"[bold]Info:[/bold] {message}")
        status.remove_class("error", "success")
        status.add_class("info")
