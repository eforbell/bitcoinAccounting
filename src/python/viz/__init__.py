"""Bitcoin portfolio visualization package.

This package provides tools for generating visual insights into Bitcoin
accumulation strategies, including the personal "orange plot" showing
purchases against BTC-USD price history.
"""

from __future__ import annotations

from .config import VizConfig
from .data_fetcher import PriceDataFetcher

__all__ = [
    'VizConfig',
    'PriceDataFetcher',
]
