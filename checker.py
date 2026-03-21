"""
Fetches stock prices and detects weekly drops beyond the threshold.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

import yfinance as yf

from config import DROP_THRESHOLD_PCT

logger = logging.getLogger(__name__)


@dataclass
class StockAlert:
    ticker: str
    company: str
    price_7d_ago: float
    price_now: float
    drop_pct: float
    currency: str = "USD"

    def __str__(self) -> str:
        return (
            f"{self.company} ({self.ticker}): "
            f"{self.price_7d_ago:.2f} → {self.price_now:.2f} {self.currency} "
            f"({self.drop_pct:+.2f}%)"
        )


def _weekly_change(ticker: str) -> tuple[float, float, str]:
    """
    Returns (price_7d_ago, price_now, currency) for *ticker*.
    Raises ValueError if data is insufficient.
    """
    end = datetime.utcnow()
    start = end - timedelta(days=10)  # fetch a bit extra to handle weekends/holidays

    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
    )

    if data is None or len(data) < 2:
        raise ValueError(f"Not enough data for {ticker}")

    # Use the closing price.
    # In newer yfinance versions, data["Close"] for a single ticker is a
    # one-column DataFrame rather than a Series; squeeze() normalises both cases.
    closes = data["Close"].squeeze().dropna()

    price_now = float(closes.iloc[-1])
    # Find the close that is at least 7 calendar days ago
    cutoff = end - timedelta(days=7)
    past_closes = closes[closes.index <= cutoff]
    if past_closes.empty:
        # Fall back to the oldest available close in the window
        price_7d_ago = float(closes.iloc[0])
    else:
        price_7d_ago = float(past_closes.iloc[-1])

    info = yf.Ticker(ticker).fast_info
    currency = getattr(info, "currency", "USD") or "USD"

    return price_7d_ago, price_now, currency


def check_watchlist(watchlist: dict[str, str]) -> list[StockAlert]:
    """
    Checks every ticker in *watchlist* and returns alerts for those whose
    weekly drop exceeds DROP_THRESHOLD_PCT.
    """
    alerts: list[StockAlert] = []

    for ticker, company in watchlist.items():
        try:
            price_7d_ago, price_now, currency = _weekly_change(ticker)
            drop_pct = (price_now - price_7d_ago) / price_7d_ago * 100

            logger.info(
                "%s (%s): %.2f → %.2f (%+.2f%%)",
                company, ticker, price_7d_ago, price_now, drop_pct,
            )

            if drop_pct <= -DROP_THRESHOLD_PCT:
                alerts.append(
                    StockAlert(
                        ticker=ticker,
                        company=company,
                        price_7d_ago=price_7d_ago,
                        price_now=price_now,
                        drop_pct=drop_pct,
                        currency=currency,
                    )
                )
        except Exception as exc:
            logger.warning("Could not fetch data for %s: %s", ticker, exc)

    # Sort by largest drop first
    alerts.sort(key=lambda a: a.drop_pct)
    return alerts
