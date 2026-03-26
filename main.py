"""
Stock Drop Monitor
==================
Checks a watchlist of ~2,000 reputable stocks once per day (or on-demand) and
sends an e-mail alert whenever any stock has fallen more than DROP_THRESHOLD_PCT
over the past 7 days.

The watchlist is built from:
  • S&P 500, S&P 400 MidCap, S&P 600 SmallCap (fetched from Wikipedia, ~1,500)
  • ~300 international blue-chips (ADRs / direct US-exchange listings)
  The combined list is cached locally in .watchlist_cache.json for 7 days.

Usage
-----
  # Run once immediately
  python main.py --once

  # Run on a daily schedule (default: every day at 09:00 local time)
  python main.py

  # Custom schedule: check at 08:30 every weekday
  python main.py --time 08:30 --weekdays-only

  # Force a fresh Wikipedia fetch (ignore cache)
  python main.py --refresh-cache --once

Environment / .env variables
-----------------------------
  SMTP_HOST        SMTP server hostname     (default: smtp.gmail.com)
  SMTP_PORT        SMTP port                (default: 587)
  SMTP_USER        Login username / address
  SMTP_PASSWORD    Login password or app-password
  EMAIL_SENDER     From address             (defaults to SMTP_USER)
  EMAIL_RECIPIENTS Comma-separated list of recipient addresses
  USE_TLS          true / false             (default: true)
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime

import schedule
from dotenv import load_dotenv

from checker import check_watchlist
from config import DROP_THRESHOLD_PCT, WATCHLIST, _CACHE_FILE, build_watchlist
from notifier import send_alert

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Suppress noisy yfinance download messages
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env(key: str, default: str | None = None, required: bool = False) -> str:
    value = os.getenv(key, default)
    if required and not value:
        logger.error("Missing required environment variable: %s", key)
        sys.exit(1)
    return value or ""


def _smtp_config() -> dict:
    return {
        "smtp_host":     _env("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port":     int(_env("SMTP_PORT", "587")),
        "smtp_user":     _env("SMTP_USER", required=True),
        "smtp_password": _env("SMTP_PASSWORD", required=True),
        "sender":        _env("EMAIL_SENDER") or _env("SMTP_USER"),
        "recipients":    [r.strip() for r in _env("EMAIL_RECIPIENTS", required=True).split(",")],
        "use_tls":       _env("USE_TLS", "true").lower() != "false",
    }


# ---------------------------------------------------------------------------
# Core job
# ---------------------------------------------------------------------------

def run_check() -> None:
    logger.info("Starting stock check — %d tickers", len(WATCHLIST))
    alerts = check_watchlist(WATCHLIST)

    if not alerts:
        logger.info(
            "No stocks dropped more than %.0f%% in the past week. Nothing to report.",
            DROP_THRESHOLD_PCT,
        )
        return

    logger.info(
        "%d stock(s) dropped >%.0f%% — sending alert e-mail …",
        len(alerts), DROP_THRESHOLD_PCT,
    )
    for a in alerts:
        logger.info("  %s", a)

    cfg = _smtp_config()
    try:
        send_alert(alerts=alerts, threshold=DROP_THRESHOLD_PCT, **cfg)
    except Exception as exc:
        logger.error("Failed to send alert e-mail: %s", exc)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor ~2,000 reputable stocks and alert on weekly drops >10%."
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check immediately and exit.",
    )
    parser.add_argument(
        "--time",
        default="09:00",
        metavar="HH:MM",
        help="Time of day to run the daily check (default: 09:00).",
    )
    parser.add_argument(
        "--weekdays-only",
        action="store_true",
        help="Only run Monday–Friday (skip weekends).",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Delete the local watchlist cache and force a fresh Wikipedia fetch.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.refresh_cache and _CACHE_FILE.exists():
        _CACHE_FILE.unlink()
        logger.info("Watchlist cache cleared; will re-fetch from Wikipedia.")
        # Re-build the module-level WATCHLIST after clearing cache
        import config as _cfg
        _cfg.WATCHLIST.clear()
        _cfg.WATCHLIST.update(build_watchlist())

    logger.info("Watchlist contains %d tickers.", len(WATCHLIST))

    if args.once:
        run_check()
        return

    # Scheduled mode
    if args.weekdays_only:
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday"):
            getattr(schedule.every(), day).at(args.time).do(run_check)
        logger.info(
            "Scheduled: weekdays at %s. Waiting for next run …", args.time
        )
    else:
        schedule.every().day.at(args.time).do(run_check)
        logger.info(
            "Scheduled: every day at %s. Waiting for next run …", args.time
        )

    logger.info("Next run: %s", schedule.next_run())

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
