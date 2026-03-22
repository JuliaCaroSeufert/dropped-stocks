"""
Fetches stock prices, detects weekly drops beyond the threshold,
and enriches each alert with quality metrics + a buy-candidate score.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import yfinance as yf

from config import DROP_THRESHOLD_PCT

logger = logging.getLogger(__name__)

# Maps yfinance sector names → SPDR sector ETF ticker
_SECTOR_ETFS: dict[str, str] = {
    "Technology":             "XLK",
    "Financial Services":     "XLF",
    "Healthcare":             "XLV",
    "Consumer Cyclical":      "XLY",
    "Consumer Defensive":     "XLP",
    "Energy":                 "XLE",
    "Industrials":            "XLI",
    "Basic Materials":        "XLB",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Communication Services": "XLC",
}

# Cache sector ETF weekly changes so we only fetch each ETF once per run
_sector_cache: dict[str, float] = {}


@dataclass
class StockAlert:
    # ── Price movement ────────────────────────────────────────────────────
    ticker:        str
    company:       str
    price_7d_ago:  float
    price_now:     float
    drop_pct:      float
    currency:      str = "USD"

    # ── Quality fundamentals ──────────────────────────────────────────────
    roe:              float | None = None   # Return on Equity  (e.g. 0.18 = 18%)
    debt_to_equity:   float | None = None   # Debt/Equity ratio
    free_cash_flow:   float | None = None   # Annual FCF in reporting currency
    trailing_pe:      float | None = None   # Trailing P/E
    forward_pe:       float | None = None   # Forward P/E
    dividend_yield:   float | None = None   # e.g. 0.03 = 3%
    beta:             float | None = None   # Market beta
    gross_margins:    float | None = None   # Gross margin (e.g. 0.42 = 42%)
    recommendation:   str   | None = None   # Analyst consensus key
    sector:           str   | None = None   # e.g. "Technology"

    # ── Context ───────────────────────────────────────────────────────────
    week_high_52:     float | None = None   # 52-week high
    rsi:              float | None = None   # 14-day RSI
    sector_drop_pct:  float | None = None   # Same-week % change of sector ETF

    # ── Derived ───────────────────────────────────────────────────────────
    score:            int  = 0    # 0-100 buy-candidate score
    is_buy_candidate: bool = False

    def __str__(self) -> str:
        return (
            f"{self.company} ({self.ticker}): "
            f"{self.price_7d_ago:.2f} → {self.price_now:.2f} {self.currency} "
            f"({self.drop_pct:+.2f}%)  Score: {self.score}/100"
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rsi(closes, period: int = 14) -> float | None:
    """Wilder's RSI from a price series."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    rs = gain.iloc[-1] / loss.iloc[-1]
    return round(100 - (100 / (1 + rs)), 1)


def _weekly_change(ticker: str) -> tuple[float, float, str, object]:
    """
    Returns (price_7d_ago, price_now, currency, closes_series).
    Fetches 30 days so RSI has enough data points.
    Raises ValueError if data is insufficient.
    """
    end   = datetime.utcnow()
    start = end - timedelta(days=30)

    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
    )

    if data is None or len(data) < 2:
        raise ValueError(f"Not enough data for {ticker}")

    closes = data["Close"].squeeze().dropna()

    price_now  = float(closes.iloc[-1])
    cutoff     = end - timedelta(days=7)
    past       = closes[closes.index <= cutoff]
    price_7d_ago = float(past.iloc[-1]) if not past.empty else float(closes.iloc[0])

    info     = yf.Ticker(ticker).fast_info
    currency = getattr(info, "currency", "USD") or "USD"

    return price_7d_ago, price_now, currency, closes


def _fetch_fundamentals(ticker: str) -> dict:
    """
    Fetches quality metrics from yfinance .info for a single ticker.
    Returns a dict; missing fields are None.
    """
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return {}

    def get(key):
        v = info.get(key)
        return v if v not in (None, "N/A", "") else None

    return {
        "roe":            get("returnOnEquity"),
        "debt_to_equity": get("debtToEquity"),
        "free_cash_flow": get("freeCashflow"),
        "trailing_pe":    get("trailingPE"),
        "forward_pe":     get("forwardPE"),
        "dividend_yield": get("dividendYield"),
        "beta":           get("beta"),
        "gross_margins":  get("grossMargins"),
        "recommendation": get("recommendationKey"),
        "sector":         get("sector"),
        "week_high_52":   get("fiftyTwoWeekHigh"),
    }


def _sector_weekly_change(sector: str | None) -> float | None:
    """Returns the weekly % change of the sector ETF, with per-run caching."""
    if sector is None:
        return None
    etf = _SECTOR_ETFS.get(sector)
    if etf is None:
        return None
    if etf in _sector_cache:
        return _sector_cache[etf]
    try:
        p7, pnow, _, _ = _weekly_change(etf)
        pct = (pnow - p7) / p7 * 100
    except Exception:
        pct = None
    _sector_cache[etf] = pct
    return pct


def _compute_score(a: StockAlert) -> int:
    """
    Scores a beaten-down stock as a buy candidate (0–100).
    Higher = more likely to be a quality company in a temporary dip.
    """
    score = 0

    # ── ROE (up to 20 pts) ────────────────────────────────────────────────
    if a.roe is not None:
        if   a.roe >= 0.25: score += 20
        elif a.roe >= 0.20: score += 16
        elif a.roe >= 0.15: score += 12
        elif a.roe >= 0.10: score += 6
        elif a.roe > 0:     score += 2

    # ── Debt/Equity (up to 20 pts) ────────────────────────────────────────
    if a.debt_to_equity is not None:
        if   a.debt_to_equity < 30:  score += 20   # yfinance returns % form
        elif a.debt_to_equity < 80:  score += 14
        elif a.debt_to_equity < 150: score += 8
        elif a.debt_to_equity < 250: score += 3
    else:
        score += 8  # unknown → neutral assumption

    # ── Free Cash Flow (up to 15 pts) ─────────────────────────────────────
    if a.free_cash_flow is not None:
        if a.free_cash_flow > 0: score += 15

    # ── Macro drop — sector fell too (up to 15 pts) ───────────────────────
    # If the whole sector dropped, the cause is external, not company-specific
    if a.sector_drop_pct is not None:
        if   a.sector_drop_pct <= -5:  score += 15
        elif a.sector_drop_pct <= -3:  score += 10
        elif a.sector_drop_pct <= -1:  score += 5

    # ── Analyst consensus (up to 10 pts) ──────────────────────────────────
    rec = (a.recommendation or "").lower()
    if   rec in ("buy", "strong_buy", "outperform"): score += 10
    elif rec in ("hold", "neutral", "market_perform"): score += 4

    # ── RSI oversold (up to 10 pts) ───────────────────────────────────────
    if a.rsi is not None:
        if   a.rsi < 25: score += 10
        elif a.rsi < 30: score += 7
        elif a.rsi < 40: score += 3

    # ── Dividend (up to 5 pts) ────────────────────────────────────────────
    if a.dividend_yield and a.dividend_yield > 0:
        score += 5

    # ── Beta stability (up to 5 pts) ──────────────────────────────────────
    if a.beta is not None and 0 < a.beta < 1:
        score += 5

    return min(score, 100)


# ── Main entry point ──────────────────────────────────────────────────────────

def check_watchlist(watchlist: dict[str, str]) -> list[StockAlert]:
    """
    Checks every ticker, enriches qualifying drops with quality data,
    scores them, and returns sorted alerts (largest drop first).
    """
    _sector_cache.clear()
    alerts: list[StockAlert] = []

    for ticker, company in watchlist.items():
        try:
            price_7d_ago, price_now, currency, closes = _weekly_change(ticker)
            drop_pct = (price_now - price_7d_ago) / price_7d_ago * 100

            if drop_pct > -DROP_THRESHOLD_PCT:
                continue

            # ── Fetch quality data only for stocks that actually dropped ──
            fund = _fetch_fundamentals(ticker)
            rsi  = _rsi(closes)

            alert = StockAlert(
                ticker       = ticker,
                company      = company,
                price_7d_ago = price_7d_ago,
                price_now    = price_now,
                drop_pct     = drop_pct,
                currency     = currency,
                rsi          = rsi,
                **fund,
            )
            alert.sector_drop_pct = _sector_weekly_change(alert.sector)
            alert.score           = _compute_score(alert)
            alert.is_buy_candidate = alert.score >= 50

            alerts.append(alert)

        except Exception:
            pass

    alerts.sort(key=lambda a: a.drop_pct)
    return alerts
