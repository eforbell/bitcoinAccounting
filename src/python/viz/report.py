"""PDF Report Generator - Combine all Bitcoin visualizations into a single PDF."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas

from db.backend import DatabaseBackend
from viz.config import VizConfig
from viz.orange_plot import OrangePlot
from viz.balance_chart import BalanceChart
from viz.custody_chart import CustodyChart
from viz.series import (
    AccumulationSeries,
    DateWindow,
    HoldingsSeries,
    accumulation_series,
    holdings_series,
    resolve_window,
)

# Optional dependencies - only needed when actually generating PDFs
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas
    from reportlab.lib.utils import ImageReader
except ImportError:
    letter = None  # type: ignore[assignment]
    inch = None  # type: ignore[assignment]
    canvas = None  # type: ignore[assignment]
    ImageReader = None  # type: ignore[assignment]


class PDFReport:
    """Generate multi-page PDF report combining all Bitcoin visualizations."""

    def __init__(self, backend: DatabaseBackend, config: VizConfig) -> None:
        """Initialize PDF report generator.

        Args:
            backend: Database backend for querying transaction data
            config: Visualization configuration

        Raises:
            ImportError: If reportlab is not installed
        """
        if canvas is None or letter is None or inch is None or ImageReader is None:
            raise ImportError(
                "reportlab is required for PDF generation. "
                "Install with: pip install reportlab"
            )

        self.backend = backend
        self.config = config
        self.orange_plot = OrangePlot(backend, config)
        self.balance_chart = BalanceChart(backend, config)
        self.custody_chart = CustodyChart(backend, config)
        self._window: DateWindow | None = None
        self._accumulation: AccumulationSeries | None = None
        self._holdings: HoldingsSeries | None = None

    def generate(self) -> Path:
        """Generate PDF report and save to file.

        Returns:
            Path to generated PDF file

        Raises:
            ValueError: If no transaction data available
            RuntimeError: If report generation fails
        """
        # Generate all chart PNGs first
        try:
            orange_path = self.orange_plot.generate()
        except ValueError:
            raise ValueError(
                "No Bitcoin transactions found. Start stacking sats!"
            )

        try:
            balance_path = self.balance_chart.generate()
        except Exception:
            balance_path = None

        try:
            custody_path = self.custody_chart.generate()
        except Exception:
            custody_path = None

        # Create PDF
        output_path = self._get_output_path()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Create canvas
        c = canvas.Canvas(str(output_path), pagesize=letter)
        page_width, page_height = letter

        # Page 1: Cover page with summary stats
        self._draw_cover_page(c, page_width, page_height)

        # Page 2: Orange plot (full page)
        c.showPage()
        self._draw_chart_page(c, page_width, page_height, orange_path, "Orange Plot")

        # Page 3: Balance and custody charts (half page each)
        if balance_path and custody_path:
            c.showPage()
            self._draw_dual_chart_page(
                c, page_width, page_height, balance_path, custody_path
            )
        elif balance_path:
            c.showPage()
            self._draw_chart_page(c, page_width, page_height, balance_path, "Balance Chart")
        elif custody_path:
            c.showPage()
            self._draw_chart_page(c, page_width, page_height, custody_path, "Custody Chart")

        # Page 4: Text summary
        c.showPage()
        self._draw_summary_page(c, page_width, page_height)

        # Save PDF
        c.save()

        return output_path

    def _draw_cover_page(self, c: Canvas, width: float, height: float) -> None:
        """Draw cover page with title and summary statistics.

        Args:
            c: ReportLab canvas
            width: Page width
            height: Page height
        """
        # Title
        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(width / 2, height - 2 * inch, "Bitcoin Portfolio Report")

        # Date range
        start_date, end_date = self._get_date_range()
        c.setFont("Helvetica", 14)
        date_str = f"{start_date.strftime('%B %d, %Y')} - {end_date.strftime('%B %d, %Y')}"
        c.drawCentredString(width / 2, height - 2.5 * inch, date_str)

        # Summary statistics
        stats = self._get_summary_stats()

        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, height - 3.5 * inch, "Summary Statistics")

        c.setFont("Helvetica", 12)
        y_pos = height - 4.2 * inch
        line_height = 0.3 * inch

        for key, value in stats.items():
            c.drawString(2 * inch, y_pos, f"{key}:")
            c.drawRightString(width - 2 * inch, y_pos, value)
            y_pos -= line_height

        # Footer
        c.setFont("Helvetica-Oblique", 10)
        c.drawCentredString(
            width / 2,
            1 * inch,
            f"Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        )

    def _draw_chart_page(
        self, c: Canvas, width: float, height: float, image_path: Path, title: str
    ) -> None:
        """Draw a full-page chart.

        Args:
            c: ReportLab canvas
            width: Page width
            height: Page height
            image_path: Path to chart PNG
            title: Chart title
        """
        # Title
        c.setFont("Helvetica-Bold", 16)
        c.drawCentredString(width / 2, height - 0.75 * inch, title)

        # Image (centered, scaled to fit)
        img = ImageReader(str(image_path))
        img_width, img_height = img.getSize()

        # Calculate scaling to fit page (leave margins)
        max_width = width - 2 * inch
        max_height = height - 2.5 * inch
        scale = min(max_width / img_width, max_height / img_height)

        scaled_width = img_width * scale
        scaled_height = img_height * scale

        x = (width - scaled_width) / 2
        y = (height - scaled_height - inch) / 2

        c.drawImage(str(image_path), x, y, scaled_width, scaled_height)

    def _draw_dual_chart_page(
        self,
        c: Canvas,
        width: float,
        height: float,
        top_image: Path,
        bottom_image: Path,
    ) -> None:
        """Draw two charts on one page (stacked vertically).

        Args:
            c: ReportLab canvas
            width: Page width
            height: Page height
            top_image: Path to top chart PNG
            bottom_image: Path to bottom chart PNG
        """
        # Top chart
        img1 = ImageReader(str(top_image))
        img1_width, img1_height = img1.getSize()

        max_width = width - 2 * inch
        max_height = (height / 2) - 1.5 * inch
        scale1 = min(max_width / img1_width, max_height / img1_height)

        scaled_width1 = img1_width * scale1
        scaled_height1 = img1_height * scale1

        x1 = (width - scaled_width1) / 2
        y1 = height - scaled_height1 - inch

        c.drawImage(str(top_image), x1, y1, scaled_width1, scaled_height1)

        # Bottom chart
        img2 = ImageReader(str(bottom_image))
        img2_width, img2_height = img2.getSize()

        scale2 = min(max_width / img2_width, max_height / img2_height)

        scaled_width2 = img2_width * scale2
        scaled_height2 = img2_height * scale2

        x2 = (width - scaled_width2) / 2
        y2 = (height / 2) - scaled_height2 - 0.5 * inch

        c.drawImage(str(bottom_image), x2, y2, scaled_width2, scaled_height2)

    def _draw_summary_page(self, c: Canvas, width: float, height: float) -> None:
        """Draw text summary and insights page.

        Args:
            c: ReportLab canvas
            width: Page width
            height: Page height
        """
        c.setFont("Helvetica-Bold", 18)
        c.drawCentredString(width / 2, height - 1.5 * inch, "Key Insights")

        # Get data for insights
        summary = self._get_accumulation().summary
        holdings = self._get_holdings()
        balance = holdings.latest.total

        # Generate insights text
        insights = []

        if summary.purchase_count:
            insights.append(
                f"• You have made {summary.purchase_count} Bitcoin purchases, "
                f"building a stack of {balance:.8f} BTC."
            )

        if summary.sale_count:
            insights.append(
                f"• You have sold Bitcoin {summary.sale_count} time(s). "
                f"Consider the long-term value of HODLing."
            )

        # Note: multisig is considered self-custody (an even stronger form!)
        pct = holdings.self_custody_pct()
        if pct is not None:
            if pct >= 80:
                insights.append(
                    f"• Excellent self-sovereignty! {pct:.1f}% of your Bitcoin "
                    f"is in self-custodied wallets (including multisig)."
                )
            elif pct >= 50:
                insights.append(
                    f"• {pct:.1f}% of your Bitcoin is self-custodied (including multisig). "
                    f"Consider moving more from exchanges to cold storage for maximum security."
                )
            else:
                insights.append(
                    f"• Only {pct:.1f}% of your Bitcoin is self-custodied (including multisig). "
                    f"Not your keys, not your coins!"
                )

        # DCA insight
        if summary.purchase_count >= 3:
            insights.append(
                f"• Dollar-cost averaging works! Your {summary.purchase_count} purchases "
                f"help smooth out Bitcoin's volatility."
            )

        # Draw insights
        c.setFont("Helvetica", 12)
        y_pos = height - 2.5 * inch
        line_height = 0.4 * inch

        for insight in insights:
            # Word wrap long lines
            words = insight.split()
            line = ""
            for word in words:
                test_line = line + word + " "
                if c.stringWidth(test_line, "Helvetica", 12) < (width - 3 * inch):
                    line = test_line
                else:
                    c.drawString(1.5 * inch, y_pos, line)
                    y_pos -= line_height
                    line = word + " "
            if line:
                c.drawString(1.5 * inch, y_pos, line)
                y_pos -= line_height

            y_pos -= 0.2 * inch  # Extra space between insights

        # Motivational quote
        c.setFont("Helvetica-BoldOblique", 14)
        y_pos -= 0.5 * inch
        c.drawCentredString(
            width / 2,
            y_pos,
            '"Study Bitcoin. Stack Sats. Stay Humble."'
        )

    def _get_window(self) -> DateWindow:
        if self._window is None:
            self._window = resolve_window(self.backend, self.config.date_range)
        return self._window

    def _get_accumulation(self) -> AccumulationSeries:
        if self._accumulation is None:
            self._accumulation = accumulation_series(self.backend, self._get_window())
        return self._accumulation

    def _get_holdings(self) -> HoldingsSeries:
        if self._holdings is None:
            self._holdings = holdings_series(self.backend, self._get_window())
        return self._holdings

    def _get_date_range(self) -> tuple[datetime, datetime]:
        """Get the date range for the report.

        Returns:
            Tuple of (start_date, end_date)
        """
        window = self._get_window()
        return window.start, window.end

    def _get_summary_stats(self) -> dict[str, str]:
        """Calculate summary statistics for cover page, as of the window end.

        Returns:
            Dictionary of stat labels to formatted values
        """
        summary = self._get_accumulation().summary
        stats: dict[str, str] = {
            "Total BTC Holdings": f"{self._get_holdings().latest.total:.8f} BTC",
            "Purchases": str(summary.purchase_count),
            "Sales": str(summary.sale_count),
        }
        if summary.invested_usd > 0:
            stats["Total Invested (USD)"] = f"${summary.invested_usd:,.2f}"
        if summary.average_cost_usd is not None:
            stats["Average Cost (USD/BTC)"] = f"${summary.average_cost_usd:,.2f}"
        return stats

    def _get_output_path(self) -> Path:
        """Get output file path for PDF report.

        Returns:
            Path to output PDF file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"btc_report_{today}.pdf"
        return self.config.output_dir / filename
