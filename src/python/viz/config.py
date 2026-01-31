"""Configuration dataclass for Bitcoin visualizations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Tuple


@dataclass
class VizConfig:
    """Configuration for Bitcoin visualization generation.

    Attributes:
        date_range: Either a preset string ('ytd', '1y', '5y', 'all') or
                   a tuple of (start_date, end_date) as datetime objects
        output_dir: Directory path where charts will be saved
        chart_types: List of chart types to generate:
                    'orange', 'balance', 'custody', or 'all'
        include_cost_basis: Whether to include cost basis overlay on orange plot
        log_scale: Whether to use logarithmic Y-axis for price charts
        dpi: Resolution in dots per inch for output images (72-600)
    """

    date_range: str | Tuple[datetime, datetime] = 'all'
    output_dir: Path = field(default_factory=lambda: Path('output/viz'))
    chart_types: list[str] = field(default_factory=lambda: ['all'])
    include_cost_basis: bool = True
    log_scale: bool = False
    dpi: int = 300

    def __post_init__(self) -> None:
        """Validate configuration after initialization."""
        # Ensure output_dir is a Path object
        if not isinstance(self.output_dir, Path):
            self.output_dir = Path(self.output_dir)

        # Validate DPI range
        if not (72 <= self.dpi <= 600):
            raise ValueError(f"DPI must be between 72 and 600, got {self.dpi}")

        # Validate chart_types
        valid_types = {'orange', 'balance', 'custody', 'all'}
        for chart_type in self.chart_types:
            if chart_type not in valid_types:
                raise ValueError(
                    f"Invalid chart type '{chart_type}'. "
                    f"Must be one of: {', '.join(sorted(valid_types))}"
                )

        # Validate date_range if it's a tuple
        if isinstance(self.date_range, tuple):
            if len(self.date_range) != 2:
                raise ValueError(
                    f"date_range tuple must have exactly 2 elements, got {len(self.date_range)}"
                )
