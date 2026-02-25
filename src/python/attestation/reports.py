"""Attestation PDF/report formatting (TAM-002).

Generates an optional PDF attestation summary from an
:class:`~attestation.generator.AttestationBundle`.  The report renders the
treasury health score, sub-score breakdown, optional score trend (when a
backend with historical snapshots is supplied), top findings, and a
remediation checklist.

The PDF dependency (``reportlab``) is treated as optional.  Callers should
check :data:`REPORTLAB_AVAILABLE` before requesting generation, or catch
:class:`PDFNotAvailableError` if they want to degrade gracefully at runtime.

Usage::

    from attestation.reports import AttestationReportFormatter, REPORTLAB_AVAILABLE

    if REPORTLAB_AVAILABLE:
        formatter = AttestationReportFormatter()
        path = formatter.generate_pdf(bundle, "/tmp/attestation-2024-12.pdf")
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from db.backend import DatabaseBackend
    from attestation.generator import AttestationBundle

# ---------------------------------------------------------------------------
# Optional reportlab import
# ---------------------------------------------------------------------------

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas as rl_canvas

    REPORTLAB_AVAILABLE: bool = True
except ImportError:  # pragma: no cover
    REPORTLAB_AVAILABLE = False


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class PDFNotAvailableError(ImportError):
    """Raised when PDF generation is attempted without reportlab installed."""

    def __init__(self) -> None:
        super().__init__(
            "reportlab is required for PDF generation. "
            "Install with: pip install reportlab"
        )


# ---------------------------------------------------------------------------
# Colour / style constants (values safe to reference even without reportlab)
# ---------------------------------------------------------------------------

_TIER_COLORS: dict[str, tuple[float, float, float]] = {
    "healthy": (0.18, 0.68, 0.34),   # green
    "warning": (0.95, 0.61, 0.07),   # amber
    "critical": (0.82, 0.18, 0.18),  # red
}

_PAGE_WIDTH, _PAGE_HEIGHT = 612.0, 792.0  # letter size in points
_MARGIN = 54.0  # 0.75 inch
_BODY_WIDTH = _PAGE_WIDTH - 2 * _MARGIN
_LINE_HEIGHT = 14.0


# ---------------------------------------------------------------------------
# AttestationReportFormatter
# ---------------------------------------------------------------------------


class AttestationReportFormatter:
    """Generate PDF attestation reports from :class:`AttestationBundle` objects.

    Args:
        backend: Optional database backend used to load historical health
            score snapshots for trend rendering.  When ``None``, the trend
            section is omitted.
        trend_limit: Number of most-recent historical snapshots to include
            in the trend table (default 6).

    Raises:
        PDFNotAvailableError: On construction when ``reportlab`` is not
            installed.
    """

    def __init__(
        self,
        backend: DatabaseBackend | None = None,
        trend_limit: int = 6,
    ) -> None:
        if not REPORTLAB_AVAILABLE:
            raise PDFNotAvailableError()
        self._backend = backend
        self._trend_limit = trend_limit

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_pdf(
        self,
        bundle: AttestationBundle,
        output_path: str | os.PathLike[str],
    ) -> Path:
        """Generate a PDF attestation report and write it to *output_path*.

        The report includes:
        * Header with period label and attestation run ID.
        * Health score summary and tier badge.
        * Sub-score breakdown table.
        * Score trend table (if a backend with snapshots was provided).
        * Top unresolved findings (up to 10).
        * Remediation checklist derived from finding categories.

        Args:
            bundle: :class:`AttestationBundle` to report on.
            output_path: Destination file path.  Parent directory must exist.

        Returns:
            :class:`~pathlib.Path` pointing to the written PDF.
        """
        path = Path(output_path)
        c = rl_canvas.Canvas(str(path), pagesize=letter)
        y = _PAGE_HEIGHT - _MARGIN

        y = self._draw_header(c, bundle, y)
        y = self._draw_score_summary(c, bundle, y)
        y = self._draw_sub_scores(c, bundle, y)
        y = self._draw_trend(c, y)
        y = self._draw_findings(c, bundle, y)
        self._draw_remediation_checklist(c, bundle, y)

        c.save()
        return path

    # ------------------------------------------------------------------
    # Section renderers
    # ------------------------------------------------------------------

    def _draw_header(
        self,
        c: Any,
        bundle: AttestationBundle,
        y: float,
    ) -> float:
        m = bundle.metadata

        # Title
        c.setFont("Helvetica-Bold", 18)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.drawString(_MARGIN, y, "Treasury Attestation Report")
        y -= 22

        # Period subtitle
        c.setFont("Helvetica", 11)
        c.setFillColorRGB(0.35, 0.35, 0.35)
        c.drawString(_MARGIN, y, f"Period: {m.period_start}  –  {m.period_end}")
        y -= _LINE_HEIGHT

        # Attestation run ID
        c.setFont("Helvetica", 9)
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.drawString(_MARGIN, y, f"Attestation ID: {m.run_id}")
        y -= _LINE_HEIGHT
        c.drawString(_MARGIN, y, f"Generated: {m.generated_at}")
        y -= _LINE_HEIGHT

        filters = []
        if m.coin:
            filters.append(f"coin={m.coin}")
        if m.wallet:
            filters.append(f"wallet={m.wallet}")
        if filters:
            c.drawString(_MARGIN, y, "Filters: " + ", ".join(filters))
            y -= _LINE_HEIGHT

        # Horizontal rule
        y -= 6
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, _PAGE_WIDTH - _MARGIN, y)
        y -= 12
        return y

    def _draw_score_summary(
        self,
        c: Any,
        bundle: AttestationBundle,
        y: float,
    ) -> float:
        result = bundle.report.health_snap.result
        tier = result.tier.value
        score = result.overall_score
        color = _TIER_COLORS.get(tier, (0.5, 0.5, 0.5))

        c.setFont("Helvetica-Bold", 13)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.drawString(_MARGIN, y, "Health Score")
        y -= 18

        # Score badge
        badge_w, badge_h = 120.0, 36.0
        c.setFillColorRGB(*color)
        c.roundRect(_MARGIN, y - badge_h + 10, badge_w, badge_h, 6, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(_MARGIN + badge_w / 2, y - badge_h + 20, f"{score:.1f}")
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(_MARGIN + badge_w / 2, y - badge_h + 10, tier.upper())

        # Unresolved count alongside badge
        finding_count = len(bundle.unresolved_findings)
        c.setFont("Helvetica", 10)
        c.setFillColorRGB(0.3, 0.3, 0.3)
        c.drawString(_MARGIN + badge_w + 16, y - 10, f"Unresolved findings: {finding_count}")

        y -= badge_h + 4
        y -= 8
        # Rule
        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, _PAGE_WIDTH - _MARGIN, y)
        y -= 10
        return y

    def _draw_sub_scores(
        self,
        c: Any,
        bundle: AttestationBundle,
        y: float,
    ) -> float:
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.drawString(_MARGIN, y, "Sub-score Breakdown")
        y -= 16

        sub_scores = bundle.report.health_snap.result.sub_scores
        col_w = _BODY_WIDTH / 3

        # Column headers
        c.setFont("Helvetica-Bold", 9)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        headers = ["Component", "Score", "Weight"]
        for i, h in enumerate(headers):
            c.drawString(_MARGIN + i * col_w, y, h)
        y -= 12

        c.setFont("Helvetica", 9)
        for sub in sub_scores:
            c.setFillColorRGB(0.15, 0.15, 0.15)
            label = sub.name.replace("_", " ").title()
            c.drawString(_MARGIN, y, label)
            c.drawString(_MARGIN + col_w, y, f"{sub.value:.1f}")
            c.drawString(_MARGIN + 2 * col_w, y, f"{sub.weight * 100:.0f}%")
            y -= _LINE_HEIGHT

        y -= 6
        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, _PAGE_WIDTH - _MARGIN, y)
        y -= 10
        return y

    def _draw_trend(self, c: Any, y: float) -> float:
        if self._backend is None:
            return y

        from integrity.health_score import TreasuryHealthScorer

        scorer = TreasuryHealthScorer(backend=self._backend)
        snapshots = scorer.load_snapshots(limit=self._trend_limit)
        if not snapshots:
            return y

        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.drawString(_MARGIN, y, "Score Trend (most recent)")
        y -= 16

        cols = ["Timestamp", "Score", "Tier", "Recon", "Transfer", "Basis"]
        col_widths = [130.0, 50.0, 60.0, 50.0, 60.0, 50.0]

        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0.45, 0.45, 0.45)
        x = _MARGIN
        for col, cw in zip(cols, col_widths):
            c.drawString(x, y, col)
            x += cw
        y -= 12

        c.setFont("Helvetica", 8)
        for row in snapshots:
            color = _TIER_COLORS.get(str(row.get("tier", "")), (0.3, 0.3, 0.3))
            x = _MARGIN
            values = [
                str(row.get("timestamp", ""))[:19],
                f"{row.get('overall_score', 0):.1f}",
                str(row.get("tier", "")).upper(),
                f"{row.get('recon_score', 0):.1f}",
                f"{row.get('transfer_score', 0):.1f}",
                f"{row.get('basis_score', 0):.1f}",
            ]
            for vi, (val, cw) in enumerate(zip(values, col_widths)):
                if vi == 2:  # tier column
                    c.setFillColorRGB(*color)
                else:
                    c.setFillColorRGB(0.15, 0.15, 0.15)
                c.drawString(x, y, val)
                x += cw
            y -= _LINE_HEIGHT
            if y < _MARGIN + 80:
                c.showPage()
                y = _PAGE_HEIGHT - _MARGIN

        y -= 6
        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, _PAGE_WIDTH - _MARGIN, y)
        y -= 10
        return y

    def _draw_findings(
        self,
        c: Any,
        bundle: AttestationBundle,
        y: float,
    ) -> float:
        findings = bundle.unresolved_findings[:10]

        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        total = len(bundle.unresolved_findings)
        shown = len(findings)
        c.drawString(_MARGIN, y, f"Top Findings ({shown} of {total} shown)")
        y -= 16

        if not findings:
            c.setFont("Helvetica", 9)
            c.setFillColorRGB(0.18, 0.68, 0.34)
            c.drawString(_MARGIN, y, "No unresolved findings — treasury is clean.")
            y -= _LINE_HEIGHT * 2
        else:
            sev_colors = {
                "critical": (0.82, 0.18, 0.18),
                "warning": (0.85, 0.55, 0.0),
                "info": (0.2, 0.45, 0.75),
            }
            c.setFont("Helvetica", 9)
            for f in findings:
                if y < _MARGIN + 60:
                    c.showPage()
                    y = _PAGE_HEIGHT - _MARGIN
                sev = str(f.get("severity", "info")).lower()
                sev_color = sev_colors.get(sev, (0.4, 0.4, 0.4))
                # Severity badge
                c.setFillColorRGB(*sev_color)
                c.setFont("Helvetica-Bold", 7)
                c.drawString(_MARGIN, y, f"[{sev.upper()}]")
                c.setFont("Helvetica", 9)
                c.setFillColorRGB(0.2, 0.2, 0.2)
                source = f.get("source", "")
                category = f.get("category", "")
                label = f"{source}/{category}"
                c.drawString(_MARGIN + 52, y, label)
                y -= _LINE_HEIGHT - 2

                # Description (word-wrapped to body width)
                desc = str(f.get("description", ""))
                y = _draw_wrapped(c, desc, _MARGIN + 8, y, _BODY_WIDTH - 8, 9)
                y -= _LINE_HEIGHT

        c.setStrokeColorRGB(0.88, 0.88, 0.88)
        c.setLineWidth(0.5)
        c.line(_MARGIN, y, _PAGE_WIDTH - _MARGIN, y)
        y -= 10
        return y

    def _draw_remediation_checklist(
        self,
        c: Any,
        bundle: AttestationBundle,
        y: float,
    ) -> None:
        if y < _MARGIN + 120:
            c.showPage()
            y = _PAGE_HEIGHT - _MARGIN

        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0.12, 0.12, 0.12)
        c.drawString(_MARGIN, y, "Remediation Checklist")
        y -= 16

        checklist = _build_remediation_checklist(bundle)
        c.setFont("Helvetica", 9)
        for item in checklist:
            if y < _MARGIN + 20:
                c.showPage()
                y = _PAGE_HEIGHT - _MARGIN
            # Checkbox square
            c.setStrokeColorRGB(0.5, 0.5, 0.5)
            c.setFillColorRGB(1, 1, 1)
            c.rect(_MARGIN, y - 2, 8, 8, fill=1, stroke=1)
            c.setFillColorRGB(0.15, 0.15, 0.15)
            c.drawString(_MARGIN + 14, y, item)
            y -= _LINE_HEIGHT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _draw_wrapped(
    c: Any,
    text: str,
    x: float,
    y: float,
    max_width: float,
    font_size: float,
) -> float:
    """Draw text with simple word-wrapping at max_width points.

    Returns:
        Updated y position after the last line drawn.
    """
    line_height = font_size * 1.4
    c.setFont("Helvetica", font_size)
    c.setFillColorRGB(0.35, 0.35, 0.35)
    words = text.split()
    line: list[str] = []
    for word in words:
        candidate = " ".join(line + [word])
        if c.stringWidth(candidate, "Helvetica", font_size) > max_width and line:
            c.drawString(x, y, " ".join(line))
            y -= line_height
            line = [word]
        else:
            line.append(word)
    if line:
        c.drawString(x, y, " ".join(line))
        y -= line_height
    return y


def _build_remediation_checklist(bundle: AttestationBundle) -> list[str]:
    """Build a de-duplicated, human-readable remediation checklist.

    Groups findings by category and returns one action item per unique
    (source, category) pair.

    Args:
        bundle: :class:`AttestationBundle` to inspect.

    Returns:
        List of actionable strings for the checklist.
    """
    seen: set[tuple[str, str]] = set()
    items: list[str] = []

    _category_actions: dict[str, str] = {
        "one_sided_send": "Locate the matching receive record or mark send as external withdrawal",
        "one_sided_receive": "Locate the matching send record or mark receive as external deposit",
        "amount_mismatch": "Reconcile send/receive amounts and update the smaller record",
        "fee_anomaly": "Review fee amount; correct if data-entry error",
        "missing_cost": "Add cost-basis price (sell_curr/sell) for Buy/Trade transactions",
        "ambiguous_source": "Record acquisition price or document tax treatment for Deposit/Mining/Reward",
        "coverage_gap": "Import historical purchase records to close the cost-basis gap",
        "discrepancy": "Reconcile ledger totals against wallet balances",
        "negative_balance": "Identify unrecorded deposits or incorrectly typed send amounts",
    }

    for f in bundle.unresolved_findings:
        source = str(f.get("source", ""))
        category = str(f.get("category", ""))
        key = (source, category)
        if key in seen:
            continue
        seen.add(key)
        action = _category_actions.get(
            category,
            f"Review and resolve {source}/{category} findings",
        )
        items.append(action)

    if not items:
        items.append("No remediation required — all integrity checks passed.")

    return items
