"""
Portfolio Reporter Module

Generates formatted reports of Kalshi portfolio data including
balance, positions, and performance metrics.
"""

from dataclasses import dataclass
from typing import Optional

from tabulate import tabulate

from kalshi_client import KalshiClient


@dataclass
class Position:
    """Represents a market position."""

    ticker: str
    market_title: str
    position: int  # Positive = Yes contracts, Negative = No contracts
    market_exposure: int  # Value at risk in cents
    resting_orders_count: int
    total_cost: int  # Total cost basis in cents
    realized_pnl: int  # Realized P&L in cents


@dataclass
class PortfolioSummary:
    """Summary of portfolio metrics."""

    available_balance: int  # In cents
    portfolio_value: int  # In cents
    total_value: int  # available_balance + portfolio_value
    positions: list[Position]


class PortfolioReporter:
    """Generates portfolio reports from Kalshi data."""

    def __init__(self, client: KalshiClient):
        """
        Initialize the reporter.

        Args:
            client: Authenticated KalshiClient instance
        """
        self.client = client
        self._market_cache: dict = {}

    def _cents_to_dollars(self, cents: int) -> float:
        """Convert cents to dollars."""
        return cents / 100.0

    def _format_currency(self, cents: int) -> str:
        """Format cents as a dollar string."""
        dollars = self._cents_to_dollars(cents)
        return f"${dollars:,.2f}"

    def _format_pnl(self, cents: int) -> str:
        """Format P&L with color indicator."""
        dollars = self._cents_to_dollars(cents)
        if cents >= 0:
            return f"+${dollars:,.2f}"
        return f"-${abs(dollars):,.2f}"

    def _get_market_title(self, ticker: str) -> str:
        """Get market title, using cache when possible."""
        if ticker not in self._market_cache:
            try:
                market_data = self.client.get_market(ticker)
                self._market_cache[ticker] = market_data.get("market", {}).get(
                    "title", ticker
                )
            except Exception:
                self._market_cache[ticker] = ticker
        return self._market_cache[ticker]

    def get_portfolio_summary(self) -> PortfolioSummary:
        """
        Fetch and compile portfolio summary.

        Returns:
            PortfolioSummary with all portfolio data
        """
        # Get balance
        balance_data = self.client.get_balance()
        available_balance = balance_data.get("balance", 0)
        portfolio_value = balance_data.get("portfolio_value", 0)

        # Get positions
        positions_data = self.client.get_positions()
        positions = []

        for pos in positions_data.get("market_positions", []):
            ticker = pos.get("ticker", "")
            market_title = self._get_market_title(ticker)

            positions.append(
                Position(
                    ticker=ticker,
                    market_title=market_title,
                    position=pos.get("position", 0),
                    market_exposure=pos.get("market_exposure", 0),
                    resting_orders_count=pos.get("resting_orders_count", 0),
                    total_cost=pos.get("total_traded", 0),
                    realized_pnl=pos.get("realized_pnl", 0),
                )
            )

        return PortfolioSummary(
            available_balance=available_balance,
            portfolio_value=portfolio_value,
            total_value=available_balance + portfolio_value,
            positions=positions,
        )

    def generate_report(self, include_positions: bool = True) -> str:
        """
        Generate a formatted portfolio report.

        Args:
            include_positions: Whether to include position details

        Returns:
            Formatted report string
        """
        summary = self.get_portfolio_summary()

        lines = []
        lines.append("=" * 60)
        lines.append("           KALSHI PORTFOLIO REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Balance section
        lines.append("ACCOUNT BALANCE")
        lines.append("-" * 40)
        balance_table = [
            ["Available Balance", self._format_currency(summary.available_balance)],
            ["Portfolio Value", self._format_currency(summary.portfolio_value)],
            ["Total Value", self._format_currency(summary.total_value)],
        ]
        lines.append(tabulate(balance_table, tablefmt="plain"))
        lines.append("")

        # Positions section
        if include_positions and summary.positions:
            lines.append(f"OPEN POSITIONS ({len(summary.positions)})")
            lines.append("-" * 40)

            position_table = []
            for pos in summary.positions:
                position_type = "YES" if pos.position > 0 else "NO"
                contracts = abs(pos.position)

                # Truncate long market titles
                title = pos.market_title
                if len(title) > 35:
                    title = title[:32] + "..."

                position_table.append(
                    [
                        title,
                        f"{contracts} {position_type}",
                        self._format_currency(pos.market_exposure),
                        self._format_pnl(pos.realized_pnl),
                    ]
                )

            headers = ["Market", "Position", "Exposure", "Realized P&L"]
            lines.append(tabulate(position_table, headers=headers, tablefmt="simple"))
            lines.append("")

        elif include_positions:
            lines.append("OPEN POSITIONS")
            lines.append("-" * 40)
            lines.append("No open positions")
            lines.append("")

        lines.append("=" * 60)

        return "\n".join(lines)

    def generate_json_report(self) -> dict:
        """
        Generate portfolio report as JSON-serializable dict.

        Returns:
            Dict containing all portfolio data
        """
        summary = self.get_portfolio_summary()

        return {
            "balance": {
                "available_balance_cents": summary.available_balance,
                "available_balance_dollars": self._cents_to_dollars(
                    summary.available_balance
                ),
                "portfolio_value_cents": summary.portfolio_value,
                "portfolio_value_dollars": self._cents_to_dollars(
                    summary.portfolio_value
                ),
                "total_value_cents": summary.total_value,
                "total_value_dollars": self._cents_to_dollars(summary.total_value),
            },
            "positions": [
                {
                    "ticker": pos.ticker,
                    "market_title": pos.market_title,
                    "position": pos.position,
                    "position_type": "YES" if pos.position > 0 else "NO",
                    "contracts": abs(pos.position),
                    "market_exposure_cents": pos.market_exposure,
                    "market_exposure_dollars": self._cents_to_dollars(
                        pos.market_exposure
                    ),
                    "realized_pnl_cents": pos.realized_pnl,
                    "realized_pnl_dollars": self._cents_to_dollars(pos.realized_pnl),
                }
                for pos in summary.positions
            ],
            "position_count": len(summary.positions),
        }
