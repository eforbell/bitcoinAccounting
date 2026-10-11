"""Chart data series shared by the matplotlib charts, the PDF report and the web.

Every number a report shows is computed here; the chart classes only draw.
Keeping the math in one place lets a browser-rendered chart and the
server-rendered PDF agree on the same holdings, basis and valuation.

Conventions:
- All datetimes are timezone-naive (SQLite stores TEXT, PostgreSQL returns
  datetime objects, yfinance returns UTC-aware timestamps).
- Holdings follow ``BalanceCalculator.get_balance()``: every non-deleted BTC
  ledger row counts, except the buy side of ``Stake`` rows.
- Cost basis is the running average cost of USD-priced purchases. Sales do not
  move the average; they shrink the position the average applies to.
"""

from __future__ import annotations

import bisect
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal

from db.queries import TradeQuery

if TYPE_CHECKING:
    from db.backend import DatabaseBackend
    from viz.data_fetcher import PriceDataFetcher

DATE_RANGE_PRESETS = ("all", "5y", "1y", "ytd")

# Bottom-to-top stacking order for custody charts.
CUSTODY_TYPES = ("self-custodied", "multisig", "custodial", "unknown")

_CUSTODY_ALIASES = {
    "self-custodied": "self-custodied",
    "self": "self-custodied",
    "cold": "self-custodied",
    "hardware": "self-custodied",
    "hot": "self-custodied",
    "custodial": "custodial",
    "exchange": "custodial",
    "third-party": "custodial",
    "multisig": "multisig",
    "multi-sig": "multisig",
    "collaborative": "multisig",
}

# Balances within this distance of zero are floating point noise.
BTC_EPSILON = 1e-8


def to_naive_datetime(value: Any) -> datetime:
    """Normalize a ledger, price feed or config date to a naive datetime."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    elif hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    elif isinstance(value, date) and not isinstance(value, datetime):
        value = datetime(value.year, value.month, value.day)
    if not isinstance(value, datetime):
        raise TypeError(f"Cannot interpret {value!r} as a datetime")
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value


# ── Date window ──


@dataclass(frozen=True)
class DateWindow:
    """Inclusive reporting window."""

    start: datetime
    end: datetime

    def contains(self, when: datetime) -> bool:
        return self.start <= when <= self.end


def _years_before(moment: datetime, years: int) -> datetime:
    try:
        return moment.replace(year=moment.year - years)
    except ValueError:
        # Feb 29 has no counterpart in a non-leap year.
        return moment.replace(year=moment.year - years, day=28)


def _first_btc_activity(backend: DatabaseBackend) -> datetime | None:
    # Take the minimum after parsing: SQLite stores createddate as TEXT, and
    # MIN() would sort "2024-01-01T09:00" after "2024-01-01 10:00".
    rows = backend.execute(
        """
        SELECT DISTINCT createddate
        FROM ledger
        WHERE (buy_curr = 'BTC' OR sell_curr = 'BTC')
          AND (deleted = 0 OR deleted IS NULL)
          AND createddate IS NOT NULL
        """
    )
    dates = [to_naive_datetime(row["createddate"]) for row in rows if row.get("createddate")]
    return min(dates) if dates else None


def resolve_window(
    backend: DatabaseBackend,
    date_range: str | tuple[Any, Any],
    *,
    now: datetime | None = None,
) -> DateWindow:
    """Resolve a preset (``all``/``5y``/``1y``/``ytd``) or explicit tuple.

    ``all`` starts at the first BTC ledger row of any type; with no BTC
    activity it falls back to Jan 1 of last year so callers still get a
    usable window.
    """
    if isinstance(date_range, tuple):
        start, end = date_range
        return DateWindow(to_naive_datetime(start), to_naive_datetime(end))

    now = now or datetime.now()
    if date_range == "ytd":
        return DateWindow(datetime(now.year, 1, 1), now)
    if date_range == "1y":
        return DateWindow(_years_before(now, 1), now)
    if date_range == "5y":
        return DateWindow(_years_before(now, 5), now)
    if date_range == "all":
        first = _first_btc_activity(backend)
        if first is None:
            return DateWindow(datetime(now.year - 1, 1, 1), now)
        return DateWindow(min(first, now), now)
    raise ValueError(f"Unknown date range: {date_range!r}")


# ── Holdings by custody ──


def normalize_custody(value: str | None) -> str:
    """Map a wallet's custody label onto one of ``CUSTODY_TYPES``."""
    if not value:
        return "unknown"
    return _CUSTODY_ALIASES.get(value.strip().lower(), "unknown")


def wallet_custody_map(backend: DatabaseBackend) -> dict[str, str]:
    """Return ``wallet_id -> custody type`` from the wallets table."""
    try:
        rows = backend.execute("SELECT wallet_id, custody FROM wallets")
    except Exception:
        # Wallets table missing on very old databases.
        return {}
    return {row["wallet_id"]: normalize_custody(row["custody"]) for row in rows}


@dataclass(frozen=True)
class HoldingsPoint:
    """End-of-day BTC holdings, split by custody type."""

    when: datetime
    by_custody: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return sum(self.by_custody.values())


@dataclass(frozen=True)
class HoldingsSeries:
    """BTC holdings over a window, opening balance included."""

    window: DateWindow
    points: list[HoldingsPoint]
    has_transactions: bool

    @property
    def latest(self) -> HoldingsPoint:
        return self.points[-1]

    def self_custody_pct(self) -> float | None:
        """Share of holdings in self custody, counting multisig as self custody."""
        latest = self.latest
        total = latest.total
        if total <= BTC_EPSILON:
            return None
        sovereign = latest.by_custody["self-custodied"] + latest.by_custody["multisig"]
        return sovereign / total * 100


def holdings_series(backend: DatabaseBackend, window: DateWindow) -> HoldingsSeries:
    """BTC holdings by custody type, one point per day with activity.

    Rows before the window fold into the opening point so narrow ranges start
    from what was actually held. Grouping by day keeps an exchange withdrawal
    and its matching wallet deposit from drawing a dip in the total.
    """
    # The buy predicate matches BalanceCalculator.get_balance(), NULL included:
    # a buy with a NULL trans_type fails the Stake check there, so it isn't
    # counted here either.
    rows = backend.execute(
        """
        SELECT
            createddate AS date,
            exchange,
            COALESCE(CASE WHEN buy_curr = 'BTC'
                          AND trans_type <> 'Stake'
                          THEN buy END, 0)
            - COALESCE(CASE WHEN sell_curr = 'BTC' THEN sell END, 0) AS btc_change
        FROM ledger
        WHERE (buy_curr = 'BTC' OR sell_curr = 'BTC')
          AND (deleted = 0 OR deleted IS NULL)
        ORDER BY createddate ASC, id ASC
        """
    )
    custody_of = wallet_custody_map(backend)

    running = {custody: 0.0 for custody in CUSTODY_TYPES}
    daily: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        when = to_naive_datetime(row["date"])
        if when > window.end:
            continue
        custody = custody_of.get(row["exchange"], "unknown")
        change = float(row["btc_change"] or 0.0)
        if when < window.start:
            running[custody] += change
        else:
            daily[when.date()][custody] += change

    points = [HoldingsPoint(window.start, dict(running))]
    for day in sorted(daily):
        for custody, change in daily[day].items():
            running[custody] += change
        # A 1Y window starts mid-day; keep its first day from plotting
        # before the opening point.
        when = max(datetime(day.year, day.month, day.day), window.start)
        points.append(HoldingsPoint(when, dict(running)))
    points.append(HoldingsPoint(window.end, dict(running)))

    return HoldingsSeries(window=window, points=points, has_transactions=bool(rows))


# ── Accumulation: trades, cost basis, valuation ──


@dataclass(frozen=True)
class TradePoint:
    """A BTC purchase or sale, priced in USD where the ledger allows."""

    when: datetime
    side: Literal["buy", "sell"]
    btc: float
    unit_price_usd: float | None
    total_usd: float | None
    wallet: str | None
    ledger_id: int | None


@dataclass(frozen=True)
class BasisPoint:
    when: datetime
    average_cost_usd: float


@dataclass(frozen=True)
class Valuation:
    """Holdings valued at a price. Cost and gain are None when no purchase has a USD cost."""

    price_usd: float
    current_value_usd: float
    position_cost_usd: float | None
    unrealized_gain_usd: float | None
    unrealized_gain_pct: float | None


@dataclass(frozen=True)
class AccumulationSummary:
    """Trade totals through the window end.

    ``invested_usd`` counts every USD-priced purchase up to the window end, not
    only those inside it, because it pairs with the value of the whole
    position. ``invested_in_window_usd`` is the in-window slice.
    """

    purchase_count: int
    sale_count: int
    btc_purchased: float
    btc_sold: float
    invested_usd: float
    invested_in_window_usd: float
    average_cost_usd: float | None
    purchases_missing_cost: int

    @property
    def net_btc(self) -> float:
        return self.btc_purchased - self.btc_sold

    def valuation(self, price_usd: float, holdings_btc: float) -> Valuation:
        """Value ``holdings_btc`` (the actual balance) at ``price_usd``.

        Valuing the balance rather than ``net_btc`` keeps Current Value in step
        with Holdings: spends, mining, income and transfer fees all count. The
        holdings are costed at the average purchase cost; with no USD-priced
        purchase the cost is unknown, so cost and gain are None rather than a
        gain measured against zero.
        """
        # Round to whole sats: that drops float dust from summing rows but keeps
        # a real one-sat balance. A negative balance has nothing to value.
        position = max(round(holdings_btc, 8), 0.0)
        current_value = position * price_usd
        if self.average_cost_usd is None:
            return Valuation(price_usd, current_value, None, None, None)
        position_cost = position * self.average_cost_usd
        gain = current_value - position_cost
        pct = gain / position_cost * 100 if position_cost > 0 else None
        return Valuation(price_usd, current_value, position_cost, gain, pct)


@dataclass(frozen=True)
class AccumulationSeries:
    window: DateWindow
    purchases: list[TradePoint]
    sales: list[TradePoint]
    basis: list[BasisPoint]
    summary: AccumulationSummary
    has_trades: bool


def _trade_point(row: dict[str, Any]) -> TradePoint:
    quantity = float(row["quantity"])
    unit = row["unit_cost"]
    total = row["total_cost"]
    return TradePoint(
        when=to_naive_datetime(row["date"]),
        side="buy" if quantity > 0 else "sell",
        btc=abs(quantity),
        unit_price_usd=abs(float(unit)) if unit is not None else None,
        total_usd=abs(float(total)) if total is not None else None,
        wallet=row.get("exchange"),
        ledger_id=row.get("id"),
    )


def accumulation_series(
    backend: DatabaseBackend,
    window: DateWindow,
    trade_query: TradeQuery | None = None,
) -> AccumulationSeries:
    """BTC trades in the window plus the running average cost basis.

    Purchases before the window seed the basis, so a 1Y view continues the
    lifetime average instead of restarting from the first in-window buy.
    """
    trade_query = trade_query or TradeQuery(backend)
    trades = sorted(
        (_trade_point(row) for row in trade_query.get_trade_cost("BTC", "USD")),
        key=lambda t: (t.when, t.ledger_id or 0),
    )

    purchases: list[TradePoint] = []
    sales: list[TradePoint] = []
    basis: list[BasisPoint] = []
    cost_sum = 0.0
    costed_btc = 0.0
    btc_purchased = 0.0
    btc_sold = 0.0
    purchase_count = 0
    sale_count = 0
    invested_in_window = 0.0
    missing_cost = 0

    for trade in trades:
        if trade.when > window.end:
            break
        in_window = trade.when >= window.start

        if trade.side == "sell":
            sale_count += 1
            btc_sold += trade.btc
            if in_window:
                sales.append(trade)
            continue

        purchase_count += 1
        btc_purchased += trade.btc
        if in_window:
            purchases.append(trade)
        if trade.unit_price_usd is None:
            missing_cost += 1
            continue

        cost_sum += trade.unit_price_usd * trade.btc
        costed_btc += trade.btc
        if in_window:
            invested_in_window += trade.unit_price_usd * trade.btc
            if not basis and costed_btc > trade.btc:
                # Opening point carries the pre-window average into view.
                prior = (cost_sum - trade.unit_price_usd * trade.btc) / (costed_btc - trade.btc)
                basis.append(BasisPoint(window.start, prior))
            basis.append(BasisPoint(trade.when, cost_sum / costed_btc))

    average_cost = cost_sum / costed_btc if costed_btc > 0 else None
    if average_cost is not None:
        if not basis:
            # Every costed purchase predates the window: flat line across it.
            basis.append(BasisPoint(window.start, average_cost))
        if basis[-1].when < window.end:
            basis.append(BasisPoint(window.end, average_cost))

    summary = AccumulationSummary(
        purchase_count=purchase_count,
        sale_count=sale_count,
        btc_purchased=btc_purchased,
        btc_sold=btc_sold,
        invested_usd=cost_sum,
        invested_in_window_usd=invested_in_window,
        average_cost_usd=average_cost,
        purchases_missing_cost=missing_cost,
    )
    return AccumulationSeries(
        window=window,
        purchases=purchases,
        sales=sales,
        basis=basis,
        summary=summary,
        has_trades=bool(trades),
    )


# ── Market price ──


@dataclass(frozen=True)
class PricePoint:
    when: datetime
    close_usd: float


def price_series(fetcher: PriceDataFetcher, window: DateWindow) -> list[PricePoint]:
    """Daily BTC-USD closes for the window, oldest first.

    Raises:
        RuntimeError: The feed returned no rows for the window.
    """
    # Daily closes are stamped at midnight; start from the window's first day so
    # a window opening mid-day (first trade, 1Y) still gets that day's close.
    first_day = window.start.replace(hour=0, minute=0, second=0, microsecond=0)
    frame = fetcher.fetch_btc_price_history(first_day, window.end)
    if frame.empty:
        raise RuntimeError(
            f"No BTC-USD price data available for range {window.start} to {window.end}"
        )
    points = [
        PricePoint(to_naive_datetime(when), float(close))
        for when, close in frame["close"].items()
    ]
    # The fetcher may hand back cached rows beyond the window.
    points = sorted(
        (p for p in points if first_day <= p.when <= window.end), key=lambda p: p.when
    )
    if not points:
        raise RuntimeError(
            f"No BTC-USD price data available for range {window.start} to {window.end}"
        )
    return points


def nearest_price(prices: list[PricePoint], when: datetime) -> float:
    """Close of the price point nearest ``when``; ``prices`` must be sorted."""
    if not prices:
        return 0.0
    index = bisect.bisect_left([p.when for p in prices], when)
    candidates = prices[max(index - 1, 0): index + 1]
    return min(candidates, key=lambda p: abs(p.when - when)).close_usd
