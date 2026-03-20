"""
Configuration: list of reputable company stocks to monitor.
"""

WATCHLIST = {
    # Tech
    "GOOGL": "Alphabet (Google)",
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "AMZN":  "Amazon",
    "META":  "Meta Platforms",
    "NVDA":  "NVIDIA",
    "TSLA":  "Tesla",
    # Fintech / Payments
    "PYPL":  "PayPal",
    "V":     "Visa",
    "MA":    "Mastercard",
    # Banking
    "DB":    "Deutsche Bank",
    "JPM":   "JPMorgan Chase",
    "BAC":   "Bank of America",
    "GS":    "Goldman Sachs",
    # Other blue-chips
    "JNJ":   "Johnson & Johnson",
    "WMT":   "Walmart",
    "BRK-B": "Berkshire Hathaway",
}

# Alert threshold: notify when weekly drop exceeds this percentage
DROP_THRESHOLD_PCT = 10.0
