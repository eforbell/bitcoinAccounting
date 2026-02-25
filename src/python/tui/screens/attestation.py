"""TUI monitoring: treasury integrity panel and attestation drill-down (TAM-003)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, Static

if TYPE_CHECKING:
    from tui.app import CryptoApp
    from db.backend import DatabaseBackend


# ---------------------------------------------------------------------------
# TreasuryIntegrityPanel — embedded in DashboardScreen
# ---------------------------------------------------------------------------


class TreasuryIntegrityPanel(Static):
    """Dashboard panel showing the latest treasury health score and delta.

    Reads the most-recent persisted health snapshots via
    :class:`~integrity.health_score.TreasuryHealthScorer`.  Shows a
    colour-coded score badge, a delta versus the previous run, and an
    unresolved finding count.  Clicking *View Details* opens
    :class:`AttestationScreen`.

    If no snapshots exist the panel prompts the operator to run
    ``bitcoin-integrity --persist``.
    """

    DEFAULT_CSS = """
    TreasuryIntegrityPanel {
        width: 100%;
        height: auto;
        max-height: 10;
        border: solid #444444;
        background: #16213e;
        padding: 1;
        margin-top: 1;
    }
    TreasuryIntegrityPanel .panel-header {
        width: 100%;
        height: auto;
    }
    TreasuryIntegrityPanel .panel-title {
        color: #f7931a;
        text-style: bold;
        width: 1fr;
    }
    TreasuryIntegrityPanel .score-healthy { color: #2fae56; text-style: bold; }
    TreasuryIntegrityPanel .score-warning { color: #e89c11; text-style: bold; }
    TreasuryIntegrityPanel .score-critical { color: #d12e2e; text-style: bold; }
    TreasuryIntegrityPanel .score-unknown  { color: #888888; text-style: bold; }
    TreasuryIntegrityPanel .meta-line { color: #888888; }
    TreasuryIntegrityPanel #btn-integrity-details {
        width: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="treasury-integrity-panel")
        self._latest: dict[str, Any] | None = None
        self._previous: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        with Horizontal(classes="panel-header"):
            yield Label("Treasury Health", classes="panel-title")
            yield Button("View Details →", id="btn-integrity-details")
        yield Container(id="integrity-content")

    def on_mount(self) -> None:
        self.set_timer(0.05, self._load_data)

    def _load_data(self) -> None:
        self._fetch_snapshots()

    @work(thread=True)
    def _fetch_snapshots(self) -> None:
        from tui.app import CryptoApp
        from integrity.health_score import TreasuryHealthScorer  # absolute — runs in thread

        app = self.app
        assert isinstance(app, CryptoApp)
        if app.crypto is None:
            self.app.call_from_thread(self._render_error, "Database unavailable")
            return
        backend = app.crypto.backend
        try:
            scorer = TreasuryHealthScorer(backend=backend)
            rows = scorer.load_snapshots(limit=2)
            if rows:
                self._latest = dict(rows[0])
                self._previous = dict(rows[1]) if len(rows) > 1 else None
            self.app.call_from_thread(self._render_data)
        except Exception as exc:
            self.app.call_from_thread(self._render_error, str(exc))

    def _render_data(self) -> None:
        try:
            container = self.query_one("#integrity-content", Container)
        except Exception:
            return
        container.remove_children()

        if self._latest is None:
            container.mount(Label(
                "[dim]No integrity data — run:[/dim] bitcoin-integrity --persist",
                classes="meta-line",
            ))
            return

        score = float(self._latest.get("overall_score", 0))
        tier = str(self._latest.get("tier", "unknown")).lower()
        ts = str(self._latest.get("timestamp", ""))[:16].replace("T", " ")
        css_cls = f"score-{tier if tier in ('healthy', 'warning', 'critical') else 'unknown'}"

        delta_txt = ""
        if self._previous is not None:
            prev_score = float(self._previous.get("overall_score", 0))
            delta = score - prev_score
            sign = "+" if delta >= 0 else ""
            delta_txt = f"  ({sign}{delta:.1f} vs prev)"

        container.mount(Label(
            f"Score: [{css_cls}]{score:.1f}  [{tier.upper()}][/{css_cls}]{delta_txt}",
        ))
        recon = float(self._latest.get("recon_score", 0))
        xfer = float(self._latest.get("transfer_score", 0))
        basis = float(self._latest.get("basis_score", 0))
        container.mount(Label(
            f"  Recon {recon:.0f}  Transfer {xfer:.0f}  Basis {basis:.0f}",
            classes="meta-line",
        ))
        container.mount(Label(f"  Last run: {ts}", classes="meta-line"))

    def _render_error(self, error: str) -> None:
        try:
            container = self.query_one("#integrity-content", Container)
        except Exception:
            return
        container.remove_children()
        container.mount(Label(f"[dim]Error loading integrity data: {error}[/dim]",
                              classes="meta-line"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-integrity-details":
            self.app.push_screen(AttestationScreen())


# ---------------------------------------------------------------------------
# AttestationScreen — full drill-down
# ---------------------------------------------------------------------------

_COLUMNS = ["Source", "Severity", "Category", "Coin", "Wallet", "Description"]

_SOURCE_LABELS = [
    ("All", "all"),
    ("Transfer", "transfer_integrity"),
    ("Basis", "basis_continuity"),
    ("Recon", "reconciliation"),
]

_SEV_LABELS = [
    ("All", "all"),
    ("Critical", "critical"),
    ("Warning", "warning"),
    ("Info", "info"),
]


class AttestationScreen(Screen[None]):
    """Treasury integrity drill-down screen.

    Runs a full integrity check, displays all unresolved findings in a
    :class:`~textual.widgets.DataTable`, and exposes source/severity
    filters.  Quick actions allow exporting the current findings to JSON
    or CSV in a temporary file whose path is shown via a notification.
    """

    CSS = """
    AttestationScreen {
        background: #1a1a2e;
    }
    #attest-container {
        width: 100%;
        height: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    #filter-bar {
        width: 100%;
        height: auto;
        margin-bottom: 1;
    }
    #filter-bar Button {
        width: auto;
        min-width: 10;
        margin-right: 1;
    }
    #filter-bar .filter-label {
        color: #888888;
        width: auto;
        padding: 0 1;
    }
    #findings-table {
        width: 100%;
        height: 1fr;
    }
    #action-bar {
        width: 100%;
        height: auto;
        margin-top: 1;
    }
    #action-bar Button {
        width: auto;
        margin-right: 1;
    }
    #status-line {
        color: #888888;
        height: auto;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Close"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._all_findings: list[dict[str, Any]] = []
        self._source_filter: str = "all"
        self._sev_filter: str = "all"
        self._loaded: bool = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Vertical(
                Horizontal(
                    Label("Source:", classes="filter-label"),
                    *[
                        Button(lbl, id=f"src-{val}", variant="default")
                        for lbl, val in _SOURCE_LABELS
                    ],
                    Label("  Severity:", classes="filter-label"),
                    *[
                        Button(lbl, id=f"sev-{val}", variant="default")
                        for lbl, val in _SEV_LABELS
                    ],
                    id="filter-bar",
                ),
                DataTable(id="findings-table"),
                Horizontal(
                    Button("Export JSON", id="btn-export-json"),
                    Button("Export CSV", id="btn-export-csv"),
                    Button("Close [Esc]", id="btn-close"),
                    id="action-bar",
                ),
                Label("", id="status-line"),
            ),
            id="attest-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.app.sub_title = "Treasury Integrity"
        self._init_table()
        self._set_filter_active("src-all", "sev-all")
        self._load_findings()

    def _init_table(self) -> None:
        table = self.query_one("#findings-table", DataTable)
        for col in _COLUMNS:
            table.add_column(col, key=col)

    @work(thread=True)
    def _load_findings(self) -> None:
        from tui.app import CryptoApp
        from integrity.cli import run_integrity_check  # absolute — runs in thread
        from attestation.generator import _extract_unresolved  # absolute — runs in thread

        app = self.app
        assert isinstance(app, CryptoApp)
        if app.crypto is None:
            self.app.call_from_thread(self._show_status, "Database unavailable", error=True)
            return
        backend = app.crypto.backend
        try:
            report = run_integrity_check(backend)
            self._all_findings = _extract_unresolved(report)
            self._loaded = True
            self.app.call_from_thread(self._refresh_table)
        except Exception as exc:
            self.app.call_from_thread(self._show_status, f"Error: {exc}", error=True)

    def _filtered(self) -> list[dict[str, Any]]:
        findings = self._all_findings
        if self._source_filter != "all":
            findings = [f for f in findings if f.get("source") == self._source_filter]
        if self._sev_filter != "all":
            findings = [f for f in findings if f.get("severity") == self._sev_filter]
        return findings

    def _refresh_table(self) -> None:
        table = self.query_one("#findings-table", DataTable)
        table.clear()
        findings = self._filtered()
        for f in findings:
            table.add_row(
                f.get("source", ""),
                f.get("severity", ""),
                f.get("category", ""),
                f.get("coin", "") or "",
                f.get("wallet", "") or "",
                (f.get("description", "") or "")[:80],
            )
        total = len(self._all_findings)
        shown = len(findings)
        self._show_status(
            f"{shown} finding(s) shown  (total: {total})"
            if self._loaded
            else "Loading…"
        )

    def _show_status(self, msg: str, error: bool = False) -> None:
        try:
            lbl = self.query_one("#status-line", Label)
            color = "red" if error else "dim"
            lbl.update(f"[{color}]{msg}[/{color}]")
        except Exception:
            pass

    def _set_filter_active(self, src_id: str, sev_id: str) -> None:
        """Highlight the active filter buttons."""
        for _, val in _SOURCE_LABELS:
            btn_id = f"src-{val}"
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                btn.variant = "primary" if btn_id == src_id else "default"
            except Exception:
                pass
        for _, val in _SEV_LABELS:
            btn_id = f"sev-{val}"
            try:
                btn = self.query_one(f"#{btn_id}", Button)
                btn.variant = "primary" if btn_id == sev_id else "default"
            except Exception:
                pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""

        if btn_id.startswith("src-"):
            self._source_filter = btn_id[4:]
            self._set_filter_active(btn_id, f"sev-{self._sev_filter}")
            self._refresh_table()

        elif btn_id.startswith("sev-"):
            self._sev_filter = btn_id[4:]
            self._set_filter_active(f"src-{self._source_filter}", btn_id)
            self._refresh_table()

        elif btn_id == "btn-export-json":
            self._export("json")

        elif btn_id == "btn-export-csv":
            self._export("csv")

        elif btn_id == "btn-close":
            self.action_dismiss_screen()

    def _export(self, fmt: str) -> None:
        """Export current findings (all, unfiltered) to a temp file."""
        import csv
        import io
        import json

        if not self._loaded:
            self.notify("Findings not yet loaded", severity="warning", timeout=4)
            return

        try:
            if fmt == "json":
                content = json.dumps(self._all_findings, indent=2, default=str)
                suffix = ".json"
            else:
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(
                    ["source", "severity", "category", "coin", "wallet", "tx_id", "description"]
                )
                for f in self._all_findings:
                    writer.writerow(
                        [
                            f.get("source", ""),
                            f.get("severity", ""),
                            f.get("category", ""),
                            f.get("coin", "") or "",
                            f.get("wallet", "") or "",
                            f.get("tx_id", "") or "",
                            f.get("description", "") or "",
                        ]
                    )
                content = buf.getvalue()
                suffix = ".csv"

            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=suffix,
                prefix="bitcoin_attestation_",
                delete=False,
                encoding="utf-8",
            ) as fh:
                fh.write(content)
                path = fh.name

            self.notify(f"Exported to: {path}", title="Export complete", timeout=8)
        except Exception as exc:
            self.notify(f"Export failed: {exc}", title="Error", severity="error", timeout=8)

    def action_dismiss_screen(self) -> None:
        self.app.pop_screen()
