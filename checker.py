"""
Fetches stock prices, detects weekly drops beyond the threshold,
and enriches each alert with quality metrics, a buy-candidate score,
and a technical trend prediction (bottom reached vs. downtrend continues).
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import yfinance as yf

from config import DROP_THRESHOLD_PCT, RISE_THRESHOLD_PCT

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

_sector_cache: dict[str, float] = {}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class TrendPrediction:
    verdict:      str          # "BOTTOM_LIKELY" | "MIXED" | "DOWNTREND"
    confidence:   int          # 0–100
    bull_signals: list[str] = field(default_factory=list)
    bear_signals: list[str] = field(default_factory=list)


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
    roe:              float | None = None
    debt_to_equity:   float | None = None
    free_cash_flow:   float | None = None
    trailing_pe:      float | None = None
    forward_pe:       float | None = None
    dividend_yield:   float | None = None
    beta:             float | None = None
    gross_margins:    float | None = None
    recommendation:   str   | None = None
    sector:           str   | None = None

    # ── Context ───────────────────────────────────────────────────────────
    week_high_52:     float | None = None
    week_low_52:      float | None = None
    rsi:              float | None = None
    sector_drop_pct:  float | None = None

    # ── Quality score ─────────────────────────────────────────────────────
    score:            int  = 0
    is_buy_candidate: bool = False

    # ── Rise detection ────────────────────────────────────────────────────
    is_rise:       bool = False   # True  → triggered by weekly gain ≥ RISE_THRESHOLD_PCT
    momentum_days: int  = 0       # number of up-days in the last 5 trading days

    # ── Trend / Momentum prediction ───────────────────────────────────────
    trend: TrendPrediction | None = None

    # ── News / Mögliche Gründe ────────────────────────────────────────────
    news_headlines: list[str] = field(default_factory=list)  # deutsche Schlagzeilen
    news_urls:      list[str] = field(default_factory=list)  # zugehörige URLs
    news_reason:    str | None = None                         # ein-Satz-Einordnung

    def __str__(self) -> str:
        verdict = self.trend.verdict if self.trend else "?"
        return (
            f"{self.company} ({self.ticker}): "
            f"{self.price_7d_ago:.2f} → {self.price_now:.2f} {self.currency} "
            f"({self.drop_pct:+.2f}%)  Score: {self.score}/100  Trend: {verdict}"
        )


# ── Technical indicator helpers ───────────────────────────────────────────────

def _rsi(closes, period: int = 14) -> float | None:
    """Wilder's RSI."""
    if len(closes) < period + 1:
        return None
    delta = closes.diff().dropna()
    gain  = delta.clip(lower=0).rolling(period).mean()
    loss  = (-delta.clip(upper=0)).rolling(period).mean()
    if loss.iloc[-1] == 0:
        return 100.0
    return round(100 - (100 / (1 + gain.iloc[-1] / loss.iloc[-1])), 1)


def _macd(closes, fast: int = 12, slow: int = 26, signal: int = 9):
    """Returns (macd_line, signal_line, histogram) as Series."""
    ema_fast   = closes.ewm(span=fast,   adjust=False).mean()
    ema_slow   = closes.ewm(span=slow,   adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line, macd_line - signal_line


def _bollinger(closes, period: int = 20, n_std: float = 2.0):
    """Returns (upper, middle, lower) Bollinger Bands."""
    ma  = closes.rolling(period).mean()
    std = closes.rolling(period).std()
    return ma + n_std * std, ma, ma - n_std * std


# ── Trend prediction ──────────────────────────────────────────────────────────

def _trend_prediction(closes, volumes=None, week_low_52: float | None = None) -> TrendPrediction:
    """
    Analyses 7 technical signals and returns a TrendPrediction.
    score > 0  → bullish (bottom likely)
    score < 0  → bearish (downtrend continues)
    """
    bull: list[str] = []
    bear: list[str] = []
    score = 0
    price_now = float(closes.iloc[-1])

    # ── 1. RSI level & direction ──────────────────────────────────────────
    rsi_now = _rsi(closes)
    if rsi_now is not None:
        if rsi_now < 25:
            score += 25
            bull.append(f"RSI extrem überverkauft ({rsi_now:.0f}) — starkes Rebound-Signal")
        elif rsi_now < 30:
            score += 15
            bull.append(f"RSI überverkauft ({rsi_now:.0f}) — Gegenbewegung wahrscheinlich")
        elif rsi_now < 40:
            score += 5
            bull.append(f"RSI im niedrigen Bereich ({rsi_now:.0f})")
        elif rsi_now > 50:
            score -= 10
            bear.append(f"RSI noch neutral ({rsi_now:.0f}) — kein Überverkauf-Signal")

        # RSI direction: compare to 3 days ago
        if len(closes) >= 20:
            rsi_prev = _rsi(closes.iloc[:-3])
            if rsi_prev is not None:
                if rsi_now > rsi_prev and rsi_now < 45:
                    score += 15
                    bull.append(
                        f"RSI dreht nach oben ({rsi_prev:.0f} → {rsi_now:.0f}) — Momentum kehrt um"
                    )
                elif rsi_now < rsi_prev and rsi_now < 35:
                    score -= 8
                    bear.append(
                        f"RSI fällt trotz Überverkauf weiter ({rsi_prev:.0f} → {rsi_now:.0f})"
                    )

    # ── 2. MACD ───────────────────────────────────────────────────────────
    if len(closes) >= 26:
        macd_line, sig_line, histogram = _macd(closes)
        hist_now  = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-4]) if len(histogram) >= 4 else hist_now

        if float(macd_line.iloc[-1]) > float(sig_line.iloc[-1]):
            score += 15
            bull.append("MACD über Signallinie — kurzfristiger Aufwärtsimpuls bestätigt")
        else:
            # Histogram shrinking = weakening downward momentum
            if hist_now > hist_prev:
                score += 10
                bull.append("MACD-Histogramm schrumpft — Abwärtsdruck lässt nach")
            else:
                score -= 12
                bear.append("MACD-Histogramm wächst — Abwärtsdruck nimmt zu")

    # ── 3. Bollinger Bands ────────────────────────────────────────────────
    if len(closes) >= 20:
        upper, ma_bb, lower = _bollinger(closes)
        lower_val = float(lower.iloc[-1])
        ma_val    = float(ma_bb.iloc[-1])

        if price_now < lower_val:
            score += 15
            bull.append(
                f"Kurs unter unterem Bollinger-Band ({lower_val:.2f}) — statistisch überverkauft"
            )
        elif price_now > ma_val:
            score += 8
            bull.append("Kurs über Bollinger-Mittellinie — kurzfristige Stärke")
        else:
            # Below middle: check if recovering toward it
            if len(closes) >= 3 and float(closes.iloc[-1]) > float(closes.iloc[-3]):
                score += 3
                bull.append("Kurs erholt sich in Richtung Bollinger-Mittellinie")
            else:
                score -= 6
                bear.append("Kurs unter Bollinger-Mittellinie ohne Erholungszeichen")

    # ── 4. Momentum deceleration ──────────────────────────────────────────
    if len(closes) >= 7:
        def pct_chg(s):
            return (float(s.iloc[-1]) - float(s.iloc[0])) / float(s.iloc[0]) * 100

        recent = pct_chg(closes.iloc[-4:])   # last 3 trading days
        prev   = pct_chg(closes.iloc[-7:-3])  # 3 trading days before that

        if recent > 0:
            score += 12
            bull.append(
                f"Kurzfristige Gegenbewegung: +{recent:.1f}% in den letzten 3 Tagen"
            )
        elif prev < 0 and recent > prev:
            score += 10
            bull.append(
                f"Rückgang verlangsamt sich ({prev:+.1f}% → {recent:+.1f}%) — Verkaufsdruck ebbt ab"
            )
        elif prev < 0 and recent < prev:
            score -= 15
            bear.append(
                f"Rückgang beschleunigt sich ({prev:+.1f}% → {recent:+.1f}%) — Abwärtstrend verstärkt"
            )

    # ── 5. Short-term moving average cross ────────────────────────────────
    if len(closes) >= 10:
        ma5  = float(closes.rolling(5).mean().iloc[-1])
        ma10 = float(closes.rolling(10).mean().iloc[-1])

        if price_now > ma5:
            score += 10
            bull.append("Kurs über 5-Tage-Durchschnitt — kurzfristige Trendwende sichtbar")
        else:
            score -= 5
            bear.append("Kurs unter 5-Tage-Durchschnitt — kurzfristiger Trend noch negativ")

        if ma5 > ma10:
            score += 5
            bull.append("5-Tage-MA über 10-Tage-MA — Momentum dreht kurzfristig positiv")
        else:
            score -= 3
            bear.append("5-Tage-MA unter 10-Tage-MA — kurzfristiges Momentum noch negativ")

    # ── 6. Volume analysis ────────────────────────────────────────────────
    if volumes is not None and len(volumes) >= 5:
        vols   = volumes.squeeze().iloc[-5:]
        prices = closes.iloc[-5:]
        up_vol = down_vol = 0.0
        for i in range(1, len(prices)):
            v = float(vols.iloc[i])
            if float(prices.iloc[i]) > float(prices.iloc[i - 1]):
                up_vol += v
            elif float(prices.iloc[i]) < float(prices.iloc[i - 1]):
                down_vol += v

        if up_vol > down_vol * 1.2:
            score += 10
            bull.append("Höheres Volumen an Aufwärtstagen — Akkumulation sichtbar")
        elif down_vol > up_vol * 1.5:
            score -= 10
            bear.append("Deutlich höheres Volumen an Abwärtstagen — anhaltender Verkaufsdruck")

    # ── 7. 52-Wochen-Tief ─────────────────────────────────────────────────
    if week_low_52 is not None and week_low_52 > 0:
        dist_pct = (price_now - week_low_52) / week_low_52 * 100
        if price_now <= week_low_52 * 1.01:
            score -= 18
            bear.append(
                f"Kurs auf/unter 52-Wochen-Tief ({week_low_52:.2f}) — neues Jahrestief, "
                f"kein Boden in Sicht"
            )
        elif dist_pct < 8:
            score -= 8
            bear.append(
                f"Kurs nur {dist_pct:.0f}% über 52-Wochen-Tief ({week_low_52:.2f}) — "
                f"Unterstützungszone wird getestet"
            )
        elif dist_pct > 30:
            score += 8
            bull.append(
                f"Kurs {dist_pct:.0f}% über 52-Wochen-Tief ({week_low_52:.2f}) — "
                f"noch deutlicher Puffer nach unten"
            )

    # ── Verdict ───────────────────────────────────────────────────────────
    confidence = min(abs(score) * 2, 100)
    if score >= 30:
        verdict = "BOTTOM_LIKELY"
    elif score <= -20:
        verdict = "DOWNTREND"
    else:
        verdict = "MIXED"

    return TrendPrediction(
        verdict=verdict,
        confidence=confidence,
        bull_signals=bull,
        bear_signals=bear,
    )


# ── Momentum prediction (for rising stocks) ──────────────────────────────────

def _momentum_prediction(closes, volumes=None, week_high_52: float | None = None) -> TrendPrediction:
    """
    Analyses 7 signals to estimate whether the current uptrend is sustainable
    or whether the stock has become overextended.
    score > 0  → momentum intact (MOMENTUM_STARK)
    score near 0 → mixed (GEMISCHT)
    score < 0  → overheated / reversal risk (ÜBERHITZT)
    """
    bull: list[str] = []
    bear: list[str] = []
    score = 0
    price_now = float(closes.iloc[-1])

    # ── 1. RSI — ideal zone vs overbought ────────────────────────────────
    rsi_now = _rsi(closes)
    if rsi_now is not None:
        if rsi_now > 80:
            score -= 20
            bear.append(f"RSI extrem überkauft ({rsi_now:.0f}) — Korrekturrisiko sehr hoch")
        elif rsi_now > 72:
            score -= 10
            bear.append(f"RSI überkauft ({rsi_now:.0f}) — kurzfristige Erschöpfung möglich")
        elif 55 <= rsi_now <= 72:
            score += 20
            bull.append(f"RSI in gesunder Stärke-Zone ({rsi_now:.0f}) — Momentum ohne Überhitzung")
        elif 45 <= rsi_now < 55:
            score += 8
            bull.append(f"RSI neutral ({rsi_now:.0f}) — Aufwärtstrend noch früh")
        else:
            score -= 5
            bear.append(f"RSI schwach ({rsi_now:.0f}) trotz Kursanstieg — Divergenz, Vorsicht")

        if len(closes) >= 20:
            rsi_prev = _rsi(closes.iloc[:-3])
            if rsi_prev is not None and rsi_now > rsi_prev:
                score += 8
                bull.append(f"RSI steigt weiter ({rsi_prev:.0f} → {rsi_now:.0f}) — Momentum beschleunigt")

    # ── 2. MACD ───────────────────────────────────────────────────────────
    if len(closes) >= 26:
        macd_line, sig_line, histogram = _macd(closes)
        hist_now  = float(histogram.iloc[-1])
        hist_prev = float(histogram.iloc[-4]) if len(histogram) >= 4 else hist_now

        if float(macd_line.iloc[-1]) > float(sig_line.iloc[-1]):
            score += 15
            bull.append("MACD über Signallinie — Aufwärtsimpuls bestätigt")
            if hist_now > hist_prev:
                score += 8
                bull.append("MACD-Histogramm wächst — Momentum nimmt zu")
        else:
            score -= 12
            bear.append("MACD unter Signallinie — Aufwärtstrend verliert Kraft")

    # ── 3. Bollinger Bands ────────────────────────────────────────────────
    if len(closes) >= 20:
        upper, ma_bb, lower = _bollinger(closes)
        upper_val = float(upper.iloc[-1])
        ma_val    = float(ma_bb.iloc[-1])

        if price_now > upper_val:
            score -= 12
            bear.append(
                f"Kurs über oberem Bollinger-Band ({upper_val:.2f}) — kurzfristig überdehnt"
            )
        elif price_now > ma_val:
            score += 12
            bull.append("Kurs oberhalb Bollinger-Mittellinie — Aufwärtsstruktur intakt")
        else:
            score -= 5
            bear.append("Kurs unter Bollinger-Mittellinie trotz Wochenanstieg — kurzfristig schwächer")

    # ── 4. Short-term moving averages ─────────────────────────────────────
    if len(closes) >= 10:
        ma5  = float(closes.rolling(5).mean().iloc[-1])
        ma10 = float(closes.rolling(10).mean().iloc[-1])

        if price_now > ma5 > ma10:
            score += 15
            bull.append("Kurs > 5-Tage-MA > 10-Tage-MA — bullische MA-Staffelung")
        elif price_now > ma5:
            score += 8
            bull.append("Kurs über 5-Tage-Durchschnitt — kurzfristiger Aufwärtstrend")
        else:
            score -= 8
            bear.append("Kurs unter 5-Tage-MA — Wochenanstieg durch Einzeltag getrieben")

    # ── 5. Momentum consistency (last 3 trading days) ────────────────────
    if len(closes) >= 4:
        def pct_chg(s):
            return (float(s.iloc[-1]) - float(s.iloc[0])) / float(s.iloc[0]) * 100

        recent = pct_chg(closes.iloc[-4:])   # last 3 days
        prev   = pct_chg(closes.iloc[-7:-3]) if len(closes) >= 7 else 0.0

        if recent > 0 and prev > 0:
            score += 12
            bull.append(f"Anstieg hält an: +{prev:.1f}% Vorwoche → +{recent:.1f}% diese Woche")
        elif recent > 0:
            score += 6
            bull.append(f"Letzte 3 Tage positiv (+{recent:.1f}%)")
        else:
            score -= 10
            bear.append(f"Letzte 3 Tage rückläufig ({recent:+.1f}%) — Schwung lässt nach")

    # ── 6. Volume analysis ────────────────────────────────────────────────
    if volumes is not None and len(volumes) >= 5:
        vols   = volumes.squeeze().iloc[-5:]
        prices = closes.iloc[-5:]
        up_vol = down_vol = 0.0
        for i in range(1, len(prices)):
            v = float(vols.iloc[i])
            if float(prices.iloc[i]) > float(prices.iloc[i - 1]):
                up_vol += v
            elif float(prices.iloc[i]) < float(prices.iloc[i - 1]):
                down_vol += v

        if up_vol > down_vol * 1.3:
            score += 12
            bull.append("Deutlich höheres Volumen an Aufwärtstagen — institutionelle Nachfrage")
        elif down_vol > up_vol * 1.2:
            score -= 10
            bear.append("Höheres Volumen an Abwärtstagen — Anstieg ohne Überzeugung")

    # ── 7. 52-Wochen-Hoch proximity ──────────────────────────────────────
    if week_high_52 is not None and week_high_52 > 0:
        dist_pct = (week_high_52 - price_now) / week_high_52 * 100
        if dist_pct < 3:
            score -= 15
            bear.append(
                f"Kurs nahe 52-Wochen-Hoch ({week_high_52:.2f}) — starker charttechnischer Widerstand"
            )
        elif dist_pct < 10:
            score -= 5
            bear.append(
                f"Noch {dist_pct:.0f}% bis 52-Wochen-Hoch ({week_high_52:.2f}) — Widerstandszone in Sicht"
            )
        elif dist_pct > 30:
            score += 10
            bull.append(
                f"Noch {dist_pct:.0f}% bis 52-Wochen-Hoch — viel Luft nach oben"
            )

    # ── Verdict ───────────────────────────────────────────────────────────
    confidence = min(abs(score) * 2, 100)
    if score >= 30:
        verdict = "MOMENTUM_STARK"
    elif score <= -20:
        verdict = "ÜBERHITZT"
    else:
        verdict = "GEMISCHT"

    return TrendPrediction(
        verdict=verdict,
        confidence=confidence,
        bull_signals=bull,
        bear_signals=bear,
    )


# ── Price + volume fetch ──────────────────────────────────────────────────────

def _weekly_change(ticker: str):
    """
    Returns (price_7d_ago, price_now, currency, closes, volumes).
    Fetches 60 days for MACD (needs 26) and reliable MAs.
    """
    end   = datetime.utcnow()
    start = end - timedelta(days=60)

    data = yf.download(
        ticker,
        start=start.strftime("%Y-%m-%d"),
        end=end.strftime("%Y-%m-%d"),
        progress=False,
        auto_adjust=True,
    )

    if data is None or len(data) < 2:
        raise ValueError(f"Not enough data for {ticker}")

    closes  = data["Close"].squeeze().dropna()
    volumes = data["Volume"] if "Volume" in data.columns else None

    price_now    = float(closes.iloc[-1])
    cutoff       = end - timedelta(days=7)
    past         = closes[closes.index <= cutoff]
    price_7d_ago = float(past.iloc[-1]) if not past.empty else float(closes.iloc[0])

    info     = yf.Ticker(ticker).fast_info
    currency = getattr(info, "currency", "USD") or "USD"

    return price_7d_ago, price_now, currency, closes, volumes


def _fetch_fundamentals(ticker: str) -> dict:
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
        "week_low_52":    get("fiftyTwoWeekLow"),
    }


def _fetch_news(ticker: str, max_items: int = 4) -> tuple[list[str], list[str]]:
    """
    Fetches recent news for a ticker via yfinance.
    Returns (headlines, urls) — parallel lists, always same length.
    Every URL is guaranteed non-empty: falls back to a Google News search
    for the exact headline title if no direct URL is available.
    """
    try:
        from urllib.parse import quote_plus
        raw = yf.Ticker(ticker).news or []
        headlines, urls = [], []
        for item in raw[:max_items]:
            content = item.get("content", item)
            title = content.get("title") or item.get("title", "")
            source = (
                (content.get("provider") or {}).get("displayName")
                or item.get("publisher", "")
            )
            url = (
                (content.get("canonicalUrl") or {}).get("url")
                or content.get("url")
                or item.get("link", "")
            )
            if not url and title:
                url = f"https://news.google.com/search?q={quote_plus(title)}"
            if title:
                headlines.append(f"{title}{f'  ({source})' if source else ''}")
                urls.append(url)
        return headlines, urls
    except Exception:
        return [], []


# ── Keyword-based reason classification ───────────────────────────────────────

_REASON_RULES: list[tuple[str, list[str]]] = [
    ("Gewinnwarnung / schwache Quartalszahlen",
     ["earnings", "profit", "revenue", "miss", "guidance", "forecast",
      "quarterly", "results", "eps", "beat", "below expectations"]),
    ("Analystensenkung / Kurszielreduktion",
     ["downgrade", "cut", "lower", "price target", "underperform",
      "sell rating", "analyst", "rating"]),
    ("Handelspolitik / Zölle / Makrodruck",
     ["tariff", "trade war", "trade deal", "inflation", "interest rate",
      "fed ", "recession", "gdp", "sanctions", "geopolit"]),
    ("Regulierungsrisiko / Rechtliche Probleme",
     ["lawsuit", "regulation", "sec ", "ftc ", "doj ", "antitrust",
      "fine", "penalty", "investigation", "probe", "settlement"]),
    ("Wettbewerbsdruck / Marktanteilsverlust",
     ["competition", "market share", "competitor", "rival", "losing ground",
      "disruption"]),
    ("Führungswechsel / Restrukturierung",
     ["ceo", "resign", "executive", "departure", "cfo", "restructur",
      "layoff", "job cut", "workforce"]),
    ("China-Risiko / Geopolitik",
     ["china", "beijing", "taiwan", "hong kong", "export control",
      "decoupling"]),
    ("Übernahme / Fusion / M&A",
     ["acquisition", "merger", "deal", "acquire", "takeover", "buyout", "bid"]),
    ("Produktrückruf / Sicherheitsbedenken",
     ["recall", "safety", "defect", "ban", "hazard", "fda "]),
    ("Breiter Marktdruck / Sektorrotation",
     ["market sell", "selloff", "sector", "rotation", "broader market",
      "risk-off", "volatility"]),
]


def _classify_reason(headlines: list[str]) -> str | None:
    """Scores headlines against keyword rules; returns the top match or None."""
    text = " ".join(headlines).lower()
    best_label, best_score = None, 0
    for label, keywords in _REASON_RULES:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score, best_label = score, label
    if best_label:
        return f"Wahrscheinlicher Grund: {best_label}"
    return None


_RISE_REASON_RULES: list[tuple[str, list[str]]] = [
    ("Starke Quartalszahlen / Gewinnüberraschung",
     ["earnings", "profit", "revenue", "beat", "surprise", "record", "quarterly",
      "results", "eps", "above expectations", "strong quarter"]),
    ("Analysten-Hochstufung / Kurszielerh öhung",
     ["upgrade", "raise", "increase", "outperform", "price target", "buy rating",
      "analyst", "overweight", "initiates"]),
    ("Positive Produktankündigung / Innovation",
     ["launch", "release", "product", "new", "announce", "partnership",
      "agreement", "contract", "deal", "technology"]),
    ("Übernahmespekulation / M&A",
     ["acquisition", "merger", "takeover", "buyout", "bid", "acquire",
      "deal", "strategic"]),
    ("Starke Wirtschaftsdaten / Makrorückenwind",
     ["economic", "gdp", "growth", "fed", "rate cut", "stimulus",
      "recovery", "jobs", "consumer"]),
    ("Breite Marktrally / Sektorrückenwind",
     ["rally", "bull", "market gain", "sector surge", "risk-on",
      "momentum", "higher", "surge"]),
    ("Regulatorische Entlastung / Rechtlicher Erfolg",
     ["approval", "approved", "clearance", "fda", "win", "settlement",
      "regulatory", "green light"]),
    ("Aktienrückkauf / Dividendenerhöhung",
     ["buyback", "repurchase", "dividend", "increase", "shareholder",
      "return", "yield"]),
]


def _classify_rise_reason(headlines: list[str]) -> str | None:
    """Scores headlines for rise-context rules; returns the top match or None."""
    text = " ".join(headlines).lower()
    best_label, best_score = None, 0
    for label, keywords in _RISE_REASON_RULES:
        score = sum(1 for kw in keywords if kw in text)
        if score > best_score:
            best_score, best_label = score, label
    if best_label:
        return f"Wahrscheinlicher Grund: {best_label}"
    return None


def _translate_headlines(headlines: list[str]) -> list[str]:
    """Translates headlines to German via Google Translate (no API key needed)."""
    try:
        from deep_translator import GoogleTranslator  # lazy import
        translator = GoogleTranslator(source="auto", target="de")
        translated = []
        for h in headlines:
            # Preserve source attribution in parentheses
            if "  (" in h:
                text, source = h.rsplit("  (", 1)
                translated.append(f"{translator.translate(text)}  ({source}")
            else:
                translated.append(translator.translate(h))
        return translated
    except ModuleNotFoundError:
        logger.warning("Paket 'deep-translator' fehlt — bitte 'pip install deep-translator' ausführen")
        return headlines
    except Exception as exc:
        logger.warning("Übersetzung fehlgeschlagen (%s): %s", type(exc).__name__, exc)
        return headlines


import time as _time


_LLM_PROMPT = (
    "Die Aktie {company} ist diese Woche um {pct:.1f}% gefallen.\n\n"
    "Aktuelle Schlagzeilen (Englisch):\n{headlines}\n\n"
    "Aufgaben:\n"
    "1. Übersetze jede Schlagzeile präzise ins Deutsche. "
    "Quellangaben in Klammern beibehalten.\n"
    "2. Schreibe EINEN prägnanten deutschen Satz der den wahrscheinlichsten "
    "Grund für den Kursrückgang einordnet. Sei konkret — nenne den Auslöser "
    "(z.B. enttäuschende Quartalszahlen, Analystensenkung, Zollsorgen, "
    "Regulierungsdruck, Gewinnmitnahmen nach Allzeithoch usw.). "
    "Beginne mit 'Wahrscheinlicher Grund:'.\n\n"
    "Antworte NUR als JSON, kein Markdown:\n"
    '{{"grund": "...", "schlagzeilen": ["...", ...]}}'
)

_LLM_PROMPT_RISE = (
    "Die Aktie {company} ist diese Woche um {pct:.1f}% gestiegen.\n\n"
    "Aktuelle Schlagzeilen (Englisch):\n{headlines}\n\n"
    "Aufgaben:\n"
    "1. Übersetze jede Schlagzeile präzise ins Deutsche. "
    "Quellangaben in Klammern beibehalten.\n"
    "2. Schreibe EINEN prägnanten deutschen Satz der den wahrscheinlichsten "
    "Grund für den Kursanstieg einordnet. Sei konkret — nenne den Auslöser "
    "(z.B. starke Quartalszahlen, Analysten-Hochstufung, Produktankündigung, "
    "Übernahmespekulation, FDA-Zulassung, positive Wirtschaftsdaten usw.). "
    "Beginne mit 'Wahrscheinlicher Grund:'.\n\n"
    "Antworte NUR als JSON, kein Markdown:\n"
    '{{"grund": "...", "schlagzeilen": ["...", ...]}}'
)


def _parse_llm_json(text: str, raw_headlines: list[str]) -> tuple[list[str], str | None]:
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    data = json.loads(text)
    return data.get("schlagzeilen", raw_headlines), data.get("grund")


def _enrich_with_groq(
    raw_headlines: list[str], prompt: str, api_key: str,
) -> tuple[list[str], str | None]:
    """Groq free tier: ~14 400 req/day, no credit card. groq.com → API Keys."""
    try:
        from groq import Groq  # pip install groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
        )
        return _parse_llm_json(resp.choices[0].message.content.strip(), raw_headlines)
    except ModuleNotFoundError:
        logger.warning("Paket 'groq' fehlt — bitte 'pip install groq' ausführen")
        return None, None
    except Exception as exc:
        logger.warning("Groq-Anreicherung fehlgeschlagen (%s): %s", type(exc).__name__, exc)
        return None, None


_gemini_model = None


def _enrich_with_gemini(
    raw_headlines: list[str], prompt: str, api_key: str,
) -> tuple[list[str], str | None]:
    """Gemini free tier (flash-lite): ~1 500 req/day. aistudio.google.com/apikey."""
    global _gemini_model
    try:
        import google.generativeai as genai  # pip install google-generativeai
        if _gemini_model is None:
            genai.configure(api_key=api_key)
            _gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")
        response = _gemini_model.generate_content(prompt)
        return _parse_llm_json(response.text.strip(), raw_headlines)
    except ModuleNotFoundError:
        logger.warning("Paket 'google-generativeai' fehlt — bitte 'pip install google-generativeai' ausführen")
        return None, None
    except Exception as exc:
        logger.warning("Gemini-Anreicherung fehlgeschlagen (%s): %s", type(exc).__name__, exc)
        return None, None


def _enrich_news(
    raw_headlines: list[str],
    company: str,
    change_pct: float,
    is_rise: bool = False,
) -> tuple[list[str], str | None]:
    """
    Übersetzt Schlagzeilen ins Deutsche und ordnet die Kursbewegung ein.
    Reihenfolge:
      1. Groq  (GROQ_API_KEY)   — kostenlos, groq.com
      2. Gemini (GEMINI_API_KEY) — kostenlos, aistudio.google.com/apikey
      3. Keyword-Matching + deep-translator — kein Key nötig
    """
    if not raw_headlines:
        return [], None

    tmpl = _LLM_PROMPT_RISE if is_rise else _LLM_PROMPT
    prompt = tmpl.format(
        company=company,
        pct=abs(change_pct),
        headlines="\n".join(f"{i+1}. {h}" for i, h in enumerate(raw_headlines)),
    )

    for env_var, fn in [
        ("GROQ_API_KEY",   _enrich_with_groq),
        ("GEMINI_API_KEY", _enrich_with_gemini),
    ]:
        key = os.getenv(env_var)
        if key:
            headlines_de, reason = fn(raw_headlines, prompt, key)
            if headlines_de is not None:
                return headlines_de, reason

    # Offline fallback
    classifier = _classify_rise_reason if is_rise else _classify_reason
    return _translate_headlines(raw_headlines), classifier(raw_headlines)


def _sector_weekly_change(sector: str | None) -> float | None:
    if sector is None:
        return None
    etf = _SECTOR_ETFS.get(sector)
    if etf is None:
        return None
    if etf in _sector_cache:
        return _sector_cache[etf]
    try:
        p7, pnow, _, _, _ = _weekly_change(etf)
        pct = (pnow - p7) / p7 * 100
    except Exception:
        pct = None
    _sector_cache[etf] = pct
    return pct


def _compute_score(a: StockAlert) -> int:
    score = 0

    if a.roe is not None:
        if   a.roe >= 0.25: score += 20
        elif a.roe >= 0.20: score += 16
        elif a.roe >= 0.15: score += 12
        elif a.roe >= 0.10: score += 6
        elif a.roe > 0:     score += 2

    if a.debt_to_equity is not None:
        if   a.debt_to_equity < 30:  score += 20
        elif a.debt_to_equity < 80:  score += 14
        elif a.debt_to_equity < 150: score += 8
        elif a.debt_to_equity < 250: score += 3
    else:
        score += 8

    if a.free_cash_flow is not None and a.free_cash_flow > 0:
        score += 15

    if a.sector_drop_pct is not None:
        if   a.sector_drop_pct <= -5:  score += 15
        elif a.sector_drop_pct <= -3:  score += 10
        elif a.sector_drop_pct <= -1:  score += 5

    rec = (a.recommendation or "").lower()
    if   rec in ("buy", "strong_buy", "outperform"):       score += 10
    elif rec in ("hold", "neutral", "market_perform"):      score += 4

    if a.rsi is not None:
        if   a.rsi < 25: score += 10
        elif a.rsi < 30: score += 7
        elif a.rsi < 40: score += 3

    if a.dividend_yield and a.dividend_yield > 0:
        score += 5

    if a.beta is not None and 0 < a.beta < 1:
        score += 5

    return min(score, 100)


def _compute_rise_score(a: StockAlert) -> int:
    """
    Quality + momentum score for rising stocks (0–100).
    Rewards solid fundamentals, RSI in healthy range, sector tailwind,
    analyst backing, and continuity of the upward move.
    """
    score = 0

    # Fundamental quality (same as drop score)
    if a.roe is not None:
        if   a.roe >= 0.25: score += 20
        elif a.roe >= 0.15: score += 12
        elif a.roe >= 0.10: score += 6
        elif a.roe > 0:     score += 2

    if a.free_cash_flow is not None and a.free_cash_flow > 0:
        score += 15

    if a.debt_to_equity is not None:
        if   a.debt_to_equity < 80:  score += 10
        elif a.debt_to_equity < 150: score += 5

    # RSI: reward healthy momentum zone, penalise overbought
    if a.rsi is not None:
        if   55 <= a.rsi <= 72: score += 15   # ideal: strong but not exhausted
        elif 45 <= a.rsi < 55:  score += 8    # early, still room
        elif a.rsi > 78:        score -= 15   # overbought, reversal risk

    # Sector tailwind (sector also rising = macro support)
    if a.sector_drop_pct is not None:
        if   a.sector_drop_pct >= 3:  score += 15
        elif a.sector_drop_pct >= 1:  score += 8
        elif a.sector_drop_pct >= 0:  score += 3

    # Analyst backing
    rec = (a.recommendation or "").lower()
    if   rec in ("buy", "strong_buy", "outperform"): score += 15
    elif rec in ("hold", "neutral", "market_perform"): score += 5

    # Gross margin (moat indicator)
    if a.gross_margins is not None and a.gross_margins >= 0.40:
        score += 5

    # Continuity of the rise (momentum_days out of last 5)
    if   a.momentum_days >= 4: score += 10
    elif a.momentum_days == 3: score += 5

    return min(score, 100)


# ── Main entry point ──────────────────────────────────────────────────────────

def check_watchlist(watchlist: dict[str, str]) -> list[StockAlert]:
    _sector_cache.clear()
    drops:   list[StockAlert] = []
    rises:   list[StockAlert] = []
    failed:  list[str]        = []
    total  = len(watchlist)
    log_every = max(1, total // 10)   # log every ~10%

    logger.info("Starte Analyse von %d Stocks …", total)

    for done, (ticker, company) in enumerate(watchlist.items(), start=1):
        if done % log_every == 0 or done == total:
            logger.info(
                "%d/%d Stocks geprüft (%.0f%%) — %d Verlust-Alert(s), %d Anstieg-Alert(s) bisher",
                done, total, done / total * 100, len(drops), len(rises),
            )
        try:
            price_7d_ago, price_now, currency, closes, volumes = _weekly_change(ticker)
            change_pct = (price_now - price_7d_ago) / price_7d_ago * 100

            is_drop = change_pct <= -DROP_THRESHOLD_PCT
            is_rise = change_pct >= RISE_THRESHOLD_PCT

            if not is_drop and not is_rise:
                continue

            # For rises: check continuity filter (≥ 3 of last 5 trading days up)
            momentum_days = 0
            if is_rise:
                n = min(6, len(closes))
                momentum_days = sum(
                    1 for i in range(1, n)
                    if float(closes.iloc[-i]) > float(closes.iloc[-i - 1])
                )
                if momentum_days < 3:
                    continue   # spike, not a sustained trend

            fund  = _fetch_fundamentals(ticker)
            rsi   = _rsi(closes)

            if is_rise:
                trend = _momentum_prediction(closes, volumes, week_high_52=fund.get("week_high_52"))
            else:
                trend = _trend_prediction(closes, volumes, week_low_52=fund.get("week_low_52"))

            alert = StockAlert(
                ticker        = ticker,
                company       = company,
                price_7d_ago  = price_7d_ago,
                price_now     = price_now,
                drop_pct      = change_pct,
                currency      = currency,
                rsi           = rsi,
                trend         = trend,
                is_rise       = is_rise,
                momentum_days = momentum_days,
                **fund,
            )
            alert.sector_drop_pct  = _sector_weekly_change(alert.sector)

            if is_rise:
                alert.score            = _compute_rise_score(alert)
                alert.is_buy_candidate = False
            else:
                alert.score            = _compute_score(alert)
                alert.is_buy_candidate = alert.score >= 50

            raw_news, news_urls = _fetch_news(ticker)
            headlines_de, reason = _enrich_news(raw_news, company, change_pct, is_rise=is_rise)
            alert.news_headlines = headlines_de
            alert.news_urls      = news_urls
            alert.news_reason    = reason

            if is_rise:
                rises.append(alert)
            else:
                drops.append(alert)

        except Exception as exc:
            failed.append(ticker)
            logger.debug("Fehler bei %s (%s): %s", ticker, company, exc)

    drops.sort(key=lambda a: a.drop_pct)          # worst drop first
    rises.sort(key=lambda a: a.drop_pct, reverse=True)  # strongest rise first

    all_alerts = drops + rises

    logger.info(
        "Analyse abgeschlossen: %d/%d Stocks geprüft — "
        "%d Verlust-Alert(s), %d Anstieg-Alert(s), %d Fehler%s",
        total - len(failed), total, len(drops), len(rises), len(failed),
        f" ({', '.join(failed[:5])}{'…' if len(failed) > 5 else ''})" if failed else "",
    )

    return all_alerts
