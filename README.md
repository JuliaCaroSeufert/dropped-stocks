# Stock Drop Monitor

Sends you an e-mail whenever a stock drops **more than 10%** in the last 7 days.

## Monitored companies

The watchlist is built dynamically from ~2,000 reputable stocks:

- **S&P 500, S&P 400 MidCap, S&P 600 SmallCap** — fetched from Wikipedia on first run (~1,500 US large/mid/small caps)
- **~300 international blue-chips** — ADRs and direct US-exchange listings from the UK, Germany, France, Switzerland, Japan, South Korea, Canada, Australia, China, India, Brazil, and more

The combined list is cached locally in `.watchlist_cache.json` for 7 days. If Wikipedia is unreachable, the international list is used as a fallback.

You can adjust `DROP_THRESHOLD_PCT` in `config.py` to change the alert threshold.

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

### Force a fresh watchlist fetch

```bash
python main.py --refresh-cache --once
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
