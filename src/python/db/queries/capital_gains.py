"""Capital gains calculation for cryptocurrency accounting.

This module provides the CapitalGainCalculator class for FIFO-based
capital gains tax reporting and forecasting.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..backend import DatabaseBackend
    from .trades import TradeQuery
    from .income import IncomeQuery
    from ..queries.price import PriceLookup


class CapitalGainCalculator:
    """Calculate capital gains using FIFO (First-In-First-Out) method.

    This class provides methods for:
    - Retrieving purchase lots (trades + interest income)
    - Generating 1099-B data for tax reporting
    - Forecasting capital gains for hypothetical sales
    """

    def __init__(
        self,
        backend: DatabaseBackend,
        trade_query: TradeQuery,
        income_query: IncomeQuery,
        price_lookup: PriceLookup
    ) -> None:
        """Initialize the capital gain calculator.

        Args:
            backend: Database backend for queries
            trade_query: TradeQuery instance for retrieving trade data
            income_query: IncomeQuery instance for retrieving interest income
            price_lookup: PriceLookup instance for price data
        """
        self.backend = backend
        self.trade_query = trade_query
        self.income_query = income_query
        self.price_lookup = price_lookup

    def get_purchase_lots(self, coin: str = 'BTC', wallet: str | None = None) -> list[tuple[Any, ...]]:
        """Get all purchase lots (trades and interest) for a coin, optionally filtered by wallet.

        Returns a list of tuples sorted by date: (date, quantity, unit_cost, total_cost, exchange)

        Args:
            coin: Cryptocurrency symbol
            wallet: Optional wallet filter

        Returns:
            list: Purchase lots as tuples (date, quantity, unit_cost, total_cost, exchange)
        """
        # Get all purchases (trades) with cost basis using TradeQuery
        all_trade_costs = self.trade_query.get_trade_cost(coin, 'USD')

        # Filter to purchases only (quantity > 0) and apply wallet filter
        if wallet:
            trade_purchases = [
                (t['date'], t['quantity'], t['unit_cost'] or 0, t['total_cost'] or 0, t.get('exchange', ''))
                for t in all_trade_costs
                if t['quantity'] > 0 and t.get('exchange') == wallet
            ]
        else:
            trade_purchases = [
                (t['date'], t['quantity'], t['unit_cost'] or 0, t['total_cost'] or 0, t.get('exchange', ''))
                for t in all_trade_costs
                if t['quantity'] > 0
            ]

        # Get interest income using IncomeQuery
        all_interest = self.income_query.get_interest_income(coin, 'USD')

        # Apply wallet filter if specified
        if wallet:
            interest_purchases = [
                (i['date'], i['to_quantity'], i['unit_cost'] or 0, i['total_cost'] or 0, i.get('exchange', ''))
                for i in all_interest
                if i.get('exchange') == wallet
            ]
        else:
            interest_purchases = [
                (i['date'], i['to_quantity'], i['unit_cost'] or 0, i['total_cost'] or 0, i.get('exchange', ''))
                for i in all_interest
            ]

        # Combine and sort all purchases by date
        all_purchases = list(trade_purchases) + list(interest_purchases)
        all_purchases.sort(key=lambda x: x[0])  # Sort by date
        return all_purchases

    def get_1099b_data(
        self,
        coin: str = 'BTC',
        tax_year: int = 2024,
        wallet: str | None = None
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Generate IRS Form 1099-B data for capital gains reporting.

        Uses FIFO (First-In-First-Out) cost basis method to match sales with purchases.
        Splits sales across multiple purchase lots if necessary.

        Args:
            coin: Cryptocurrency symbol (default 'BTC')
            tax_year: Tax year to report (default 2024)
            wallet: Optional wallet filter for per-wallet FIFO (2025+ compliance)

        Returns:
            tuple: (form_8949_entries, worksheet_entries)
                - form_8949_entries: List of Form 8949 entries (one per lot)
                - worksheet_entries: Detailed calculation worksheet
        """
        from datetime import datetime

        tax_year_end = datetime(tax_year, 12, 31, 23, 59, 59)

        # Get all purchases using helper method
        all_purchases = self.get_purchase_lots(coin, wallet)

        if not all_purchases:
            return [], []

        # Get all sales using TradeQuery
        sales_data = self.trade_query.get_sales(coin, wallet=wallet)
        sales = [(s['createddate'], abs(s['quantity']), s['exchange'], s['id']) for s in sales_data]

        # Get trade costs for proceeds calculation
        all_trade_costs = self.trade_query.get_trade_cost(coin, 'USD')

        # Build purchase queue for FIFO matching
        purchase_queue: list[dict[str, Any]] = []
        for lot in all_purchases:
            purchase_date, quantity, unit_cost, total_cost, exchange = lot

            # Parse date if it's a string (from SQLite)
            if isinstance(purchase_date, str):
                purchase_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))

            # unit_cost and total_cost are already calculated
            unit_cost_val = float(unit_cost) if unit_cost else 0.0

            purchase_queue.append({
                'date': purchase_date,
                'quantity_remaining': float(quantity),
                'unit_cost': unit_cost_val,
                'exchange': exchange
            })

        # Process each sale using FIFO
        # We process ALL sales chronologically to properly consume the FIFO queue,
        # but only output 1099-B entries for sales within the specific tax year
        results: list[dict[str, str]] = []
        worksheet: list[dict[str, str]] = []
        tax_year_start = datetime(tax_year, 1, 1, 0, 0, 0)

        for sale in sales:
            sale_date, sale_quantity, sale_exchange, sale_id = sale
            sale_quantity = float(sale_quantity)

            # Parse date if it's a string (from SQLite)
            if isinstance(sale_date, str):
                sale_date = datetime.fromisoformat(sale_date.replace('Z', '+00:00'))

            # Check if this sale is within the tax year we're reporting
            sale_in_tax_year = (sale_date >= tax_year_start and sale_date <= tax_year_end)

            # Get proceeds only if we need to report this sale
            if sale_in_tax_year:
                # Get proceeds (what we sold the coin for in USD) using TradeQuery
                # Find this specific sale in the trade cost data
                sale_found = False
                for t in all_trade_costs:
                    t_date = t['date']
                    if isinstance(t_date, str):
                        t_date = datetime.fromisoformat(t_date.replace('Z', '+00:00'))

                    if t_date == sale_date and t['quantity'] < 0:
                        proceeds_total = abs(float(t['total_cost'])) if t['total_cost'] is not None else 0.0
                        proceeds_per_unit = abs(float(t['unit_cost'])) if t['unit_cost'] is not None else 0.0
                        sale_found = True
                        break

                if not sale_found:
                    # Fallback: use price lookup - convert datetime to string for price lookup
                    price = self.price_lookup.get_price(coin, 'USD', sale_date.isoformat() if isinstance(sale_date, datetime) else sale_date)
                    if price is not None:
                        proceeds_per_unit = price
                        proceeds_total = sale_quantity * proceeds_per_unit
                    else:
                        proceeds_per_unit = 0.0
                        proceeds_total = 0.0

            # Match this sale with purchases using FIFO
            quantity_to_match = sale_quantity
            matched_purchases: list[dict[str, Any]] = []

            for purchase in purchase_queue:
                if quantity_to_match <= 0:
                    break

                if purchase['quantity_remaining'] > 0:
                    # Determine how much of this purchase applies to this sale
                    match_quantity = min(quantity_to_match, purchase['quantity_remaining'])

                    matched_purchases.append({
                        'acquire_date': purchase['date'],
                        'quantity': match_quantity,
                        'unit_cost': purchase['unit_cost'],
                        'cost_basis': match_quantity * purchase['unit_cost']
                    })

                    purchase['quantity_remaining'] -= match_quantity
                    quantity_to_match -= match_quantity

            # Check if there's unmatched quantity (missing basis)
            if quantity_to_match > 0.00000001:  # Allow for floating point precision
                # Add entry for unmatched quantity with $0 basis
                matched_purchases.append({
                    'acquire_date': None,  # Unknown acquisition date
                    'quantity': quantity_to_match,
                    'unit_cost': 0.0,
                    'cost_basis': 0.0
                })

            # Create 1099-B entries (one per purchase lot matched)
            # But only for sales within the tax year we're reporting
            if sale_in_tax_year:
                for match in matched_purchases:
                    # Handle missing basis (no acquisition date)
                    if match['acquire_date'] is None:
                        acquire_date_str = 'UNKNOWN'
                        holding_days = 0
                        term = 'Short'  # Conservative: report as short-term
                    else:
                        acquire_date_str = match['acquire_date'].strftime('%m/%d/%Y')
                        holding_days = (sale_date - match['acquire_date']).days
                        term = 'Long' if holding_days >= 365 else 'Short'

                    # Calculate proportional proceeds for this lot
                    lot_proceeds = (match['quantity'] / sale_quantity) * proceeds_total
                    gain_loss = lot_proceeds - match['cost_basis']

                    # Add to 1099-B form output
                    result = {
                        'Description': f"{match['quantity']:.8f} {coin}",
                        'Date Acquired': acquire_date_str,
                        'Date Sold': sale_date.strftime('%m/%d/%Y'),
                        'Proceeds': f"{lot_proceeds:.2f}",
                        'Cost Basis': f"{match['cost_basis']:.2f}",
                        'Adjustment Code': '',
                        'Adjustment Amount': '',
                        'Wash Sale Loss': '',
                        'Form': '8949',
                        'Term': term
                    }
                    results.append(result)

                    # Add to detailed worksheet
                    worksheet_entry = {
                        'Sale Date': sale_date.strftime('%m/%d/%Y'),
                        'Sale Quantity': f"{sale_quantity:.8f}",
                        'Proceeds': f"{lot_proceeds:.2f}",
                        'Acquire Date': acquire_date_str,
                        'Lot Quantity': f"{match['quantity']:.8f}",
                        'Unit Cost Basis': f"{match['unit_cost']:.2f}",
                        'Total Cost Basis': f"{match['cost_basis']:.2f}",
                        'Holding Days': str(holding_days) if match['acquire_date'] else 'UNKNOWN',
                        'Term': term,
                        'Gain/Loss': f"{gain_loss:.2f}"
                    }
                    worksheet.append(worksheet_entry)

        return results, worksheet

    def forecast_sale(
        self,
        coin: str = 'BTC',
        quantity: float = 1.0,
        sale_price_usd: float | None = None,
        wallet: str | None = None
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Forecast capital gains for a hypothetical sale using FIFO basis.

        Does not record any transactions - for planning purposes only.

        Args:
            coin: The cryptocurrency to simulate selling
            quantity: How much to sell
            sale_price_usd: Sale price per unit in USD (if None, uses current market)
            wallet: Optional wallet filter for per-wallet FIFO (2025+ compliance)

        Returns:
            tuple: (lots_list, summary_dict)
                - lots_list: List of lots that would be sold (FIFO order)
                - summary_dict: Summary statistics (totals, short/long breakdown)
        """
        from datetime import datetime

        # Get all purchases using helper method
        all_purchases = self.get_purchase_lots(coin, wallet)

        if not all_purchases:
            return [], {}

        # Get all historical sales using TradeQuery
        sales_data = self.trade_query.get_sales(coin, wallet=wallet)
        historical_sales = [(s['createddate'], s['quantity'], s['exchange'], s['id']) for s in sales_data]

        # Build purchase queue
        purchase_queue: list[dict[str, Any]] = []
        for lot in all_purchases:
            purchase_date, qty, unit_cost, total_cost, exchange = lot

            # Parse date if it's a string (from SQLite)
            if isinstance(purchase_date, str):
                purchase_date = datetime.fromisoformat(purchase_date.replace('Z', '+00:00'))

            unit_cost_val = float(unit_cost) if unit_cost else 0.0

            purchase_queue.append({
                'date': purchase_date,
                'quantity_remaining': float(qty),
                'unit_cost': unit_cost_val,
                'exchange': exchange
            })

        # Process historical sales to consume the queue
        for sale in historical_sales:
            sale_date, sale_quantity, sale_exchange, sale_id = sale
            sale_quantity = float(sale_quantity)
            quantity_to_match = sale_quantity

            for purchase in purchase_queue:
                if quantity_to_match <= 0:
                    break

                if purchase['quantity_remaining'] > 0:
                    match_quantity = min(quantity_to_match, purchase['quantity_remaining'])
                    purchase['quantity_remaining'] -= match_quantity
                    quantity_to_match -= match_quantity

        # Now simulate the hypothetical sale
        sale_date = datetime.now()
        quantity_to_sell = float(quantity)
        quantity_remaining = quantity_to_sell
        lots: list[dict[str, Any]] = []

        for purchase in purchase_queue:
            if quantity_remaining <= 0:
                break

            if purchase['quantity_remaining'] > 0:
                match_quantity = min(quantity_remaining, purchase['quantity_remaining'])
                holding_days = (sale_date - purchase['date']).days
                term = 'Long' if holding_days >= 365 else 'Short'

                lots.append({
                    'acquire_date': purchase['date'],
                    'quantity': match_quantity,
                    'unit_cost': purchase['unit_cost'],
                    'cost_basis': match_quantity * purchase['unit_cost'],
                    'holding_days': holding_days,
                    'term': term
                })

                quantity_remaining -= match_quantity

        # Handle missing basis
        if quantity_remaining > 0.00000001:
            lots.append({
                'acquire_date': None,
                'quantity': quantity_remaining,
                'unit_cost': 0.0,
                'cost_basis': 0.0,
                'holding_days': 0,
                'term': 'Short'
            })

        # Calculate summary statistics
        total_cost_basis = sum(lot['cost_basis'] for lot in lots)
        total_quantity = sum(lot['quantity'] for lot in lots)

        short_term_lots = [lot for lot in lots if lot['term'] == 'Short']
        long_term_lots = [lot for lot in lots if lot['term'] == 'Long']
        missing_basis_lots = [lot for lot in lots if lot['acquire_date'] is None]

        short_term_quantity = sum(lot['quantity'] for lot in short_term_lots)
        long_term_quantity = sum(lot['quantity'] for lot in long_term_lots)
        missing_basis_quantity = sum(lot['quantity'] for lot in missing_basis_lots)

        short_term_cost = sum(lot['cost_basis'] for lot in short_term_lots)
        long_term_cost = sum(lot['cost_basis'] for lot in long_term_lots)

        # Calculate proportional proceeds
        if sale_price_usd:
            total_proceeds = quantity_to_sell * sale_price_usd
            short_term_proceeds = short_term_quantity * sale_price_usd
            long_term_proceeds = long_term_quantity * sale_price_usd
        else:
            total_proceeds = 0
            short_term_proceeds = 0
            long_term_proceeds = 0

        summary = {
            'total_quantity': total_quantity,
            'total_cost_basis': total_cost_basis,
            'total_proceeds': total_proceeds,
            'short_term_count': len(short_term_lots),
            'short_term_quantity': short_term_quantity,
            'short_term_cost': short_term_cost,
            'short_term_proceeds': short_term_proceeds,
            'long_term_count': len(long_term_lots),
            'long_term_quantity': long_term_quantity,
            'long_term_cost': long_term_cost,
            'long_term_proceeds': long_term_proceeds,
            'missing_basis_count': len(missing_basis_lots),
            'missing_basis_quantity': missing_basis_quantity
        }

        return lots, summary
