# Stock Drop Monitor

Sends you an e-mail whenever a stock from a reputable company drops **more than 10%** in the last 7 days.

## Monitored companies

| Ticker | Company |
|--------|---------|
| GOOGL | Alphabet (Google) |
| AAPL | Apple |
| MSFT | Microsoft |
| AMZN | Amazon |
| META | Meta Platforms |
| NVDA | NVIDIA |
| TSLA | Tesla |
| PYPL | PayPal |
| V | Visa |
| MA | Mastercard |
| DB | Deutsche Bank |
| JPM | JPMorgan Chase |
| BAC | Bank of America |
| GS | Goldman Sachs |
| JNJ | Johnson & Johnson |
| WMT | Walmart |
| BRK-B | Berkshire Hathaway |

You can add or remove tickers in `config.py`, and adjust `DROP_THRESHOLD_PCT` there too.

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure e-mail

```bash
cp .env.example .env
# edit .env with your SMTP credentials
```

**Gmail tip:** Use an [App Password](https://support.google.com/accounts/answer/185833) instead of your regular password. Set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `USE_TLS=true`.

**Outlook/Office 365 tip:** `SMTP_HOST=smtp.office365.com`, `SMTP_PORT=587`, `USE_TLS=true`.

---

## Usage

### Run once (useful for testing)

```bash
python main.py --once
```

### Run on a daily schedule (default: 09:00 every day)

```bash
python main.py
```

### Weekdays only at 08:30

```bash
python main.py --time 08:30 --weekdays-only
```

### Run as a background service (Linux systemd example)

Create `/etc/systemd/system/stock-monitor.service`:

```ini
[Unit]
Description=Stock Drop Monitor
After=network-online.target

[Service]
WorkingDirectory=/path/to/dropped-stocks
ExecStart=/usr/bin/python3 main.py --time 09:00 --weekdays-only
EnvironmentFile=/path/to/dropped-stocks/.env
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now stock-monitor
```

---

## How it works

1. At the scheduled time, `main.py` calls `check_watchlist()` in `checker.py`.
2. For each ticker, it downloads ~10 days of price history from Yahoo Finance via `yfinance`.
3. It compares the latest closing price to the closing price 7 calendar days ago.
4. Any stock that dropped more than `DROP_THRESHOLD_PCT` (default **10%**) triggers an alert.
5. If at least one alert exists, `notifier.py` sends a formatted HTML e-mail via SMTP.

---

*Prices are sourced from Yahoo Finance. This tool is for informational purposes only and is not financial advice.*
