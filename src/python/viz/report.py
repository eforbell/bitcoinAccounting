"""PDF Report Generator - Combine all Bitcoin visualizations into a single PDF."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from reportlab.pdfgen.canvas import Canvas

try:
    # When imported from tests
    from src.python.db.backend import DatabaseBackend
    from src.python.viz.config import VizConfig
    from src.python.viz.orange_plot import OrangePlot
    from src.python.viz.balance_chart import BalanceChart
    from src.python.viz.custody_chart import CustodyChart
    from src.python.db.queries import TradeQuery, BalanceCalculator
except ModuleNotFoundError:
    # When running from CLI with sys.path manipulation
    from db.backend import DatabaseBackend  # type: ignore[import]
    from viz.config import VizConfig  # type: ignore[import]
    from viz.orange_plot import OrangePlot  # type: ignore[import]
    from viz.balance_chart import BalanceChart  # type: ignore[import]
    from viz.custody_chart import CustodyChart  # type: ignore[import]
    from db.queries import TradeQuery, BalanceCalculator  # type: ignore[import]

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
        self.trade_query = TradeQuery(backend)
        self.balance_calc = BalanceCalculator(backend)

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
        balance = self.balance_calc.get_balance("BTC")
        trades = self.trade_query.get_trade_cost("BTC", "USD")
        purchases = [t for t in trades if t["quantity"] > 0]
        sales = [t for t in trades if t["quantity"] < 0]

        # Generate insights text
        insights = []

        if purchases:
            insights.append(
                f"• You have made {len(purchases)} Bitcoin purchases, "
                f"building a stack of {balance:.8f} BTC."
            )

        if sales:
            insights.append(
                f"• You have sold Bitcoin {len(sales)} time(s). "
                f"Consider the long-term value of HODLing."
            )

        # Calculate self-sovereignty if custody data available
        # Note: multisig is considered self-custody (an even stronger form!)
        try:
            start_date, end_date = self._get_date_range()
            custody_data = self.custody_chart._get_custody_balances(start_date, end_date)
            if custody_data:
                last_snapshot = custody_data[-1]
                # Self-custody includes both single-sig and multisig
                self_custodied = last_snapshot.get("self-custodied", 0)
                multisig = last_snapshot.get("multisig", 0)
                total_self_custody = self_custodied + multisig

                total = sum([
                    last_snapshot.get("self-custodied", 0),
                    last_snapshot.get("custodial", 0),
                    last_snapshot.get("multisig", 0),
                    last_snapshot.get("unknown", 0),
                ])
                if total > 0:
                    pct = (total_self_custody / total) * 100
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
        except Exception:
            pass  # Skip custody insight if data unavailable

        # DCA insight
        if len(purchases) >= 3:
            insights.append(
                f"• Dollar-cost averaging works! Your {len(purchases)} purchases "
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

    def _get_date_range(self) -> tuple[datetime, datetime]:
        """Get the date range for the report.

        Returns:
            Tuple of (start_date, end_date)
        """
        if isinstance(self.config.date_range, tuple):
            return self.config.date_range

        # Use orange_plot's date range resolution
        return self.orange_plot._resolve_date_range()

    def _get_summary_stats(self) -> dict[str, str]:
        """Calculate summary statistics for cover page.

        Returns:
            Dictionary of stat labels to formatted values
        """
        stats: dict[str, str] = {}

        # Current balance
        balance = self.balance_calc.get_balance("BTC")
        stats["Total BTC Holdings"] = f"{balance:.8f} BTC"

        # Transaction counts
        trades = self.trade_query.get_trades("BTC")
        purchases = [t for t in trades if t["to_quantity"] > 0]
        sales = [t for t in trades if t["to_quantity"] < 0]
        stats["Purchases"] = str(len(purchases))
        stats["Sales"] = str(len(sales))

        # Cost basis (if available)
        trade_cost = self.trade_query.get_trade_cost("BTC", "USD")
        purchase_cost = [t for t in trade_cost if t["quantity"] > 0 and t["total_cost"] is not None]
        if purchase_cost:
            total_invested = sum(t["total_cost"] for t in purchase_cost)
            stats["Total Invested (USD)"] = f"${total_invested:,.2f}"

        return stats

    def _get_output_path(self) -> Path:
        """Get output file path for PDF report.

        Returns:
            Path to output PDF file
        """
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"btc_report_{today}.pdf"
        return self.config.output_dir / filename
