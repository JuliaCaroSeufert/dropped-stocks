"""
Sends an HTML e-mail alert listing all stocks that dropped significantly,
enriched with quality metrics and a buy-candidate score.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from checker import StockAlert

logger = logging.getLogger(__name__)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 70: return "#2e7d32"   # green
    if score >= 50: return "#f57f17"   # amber
    return "#b71c1c"                   # red


def _score_label(score: int) -> str:
    if score >= 70: return "★ Strong Buy Candidate"
    if score >= 50: return "◆ Possible Opportunity"
    return "✗ Caution"


def _fmt_pct(v: float | None) -> str:
    return f"{v*100:+.1f}%" if v is not None else "—"


def _fmt_float(v: float | None, decimals: int = 2) -> str:
    return f"{v:.{decimals}f}" if v is not None else "—"


def _fmt_fcf(v: float | None) -> str:
    if v is None:
        return "—"
    if abs(v) >= 1e9:
        return f"{v/1e9:+.1f}B"
    if abs(v) >= 1e6:
        return f"{v/1e6:+.1f}M"
    return f"{v:+.0f}"


def _fmt_rec(v: str | None) -> str:
    if not v:
        return "—"
    return v.replace("_", " ").title()


def _drop_color(pct: float) -> str:
    if pct <= -20: return "#b71c1c"
    if pct <= -15: return "#c62828"
    return "#d32f2f"


def _sector_context(a: StockAlert) -> str:
    if a.sector_drop_pct is None:
        return "—"
    etf_pct = f"{a.sector_drop_pct:+.1f}%"
    if a.sector_drop_pct <= -3:
        return f"{etf_pct} ← whole sector fell (macro)"
    if a.sector_drop_pct <= 0:
        return f"{etf_pct} ← sector slightly down"
    return f"{etf_pct} ← sector held / rose (company-specific!)"


# ── HTML builder ──────────────────────────────────────────────────────────────

def _build_html(alerts: list[StockAlert], threshold: float) -> str:
    buy_candidates = [a for a in alerts if a.is_buy_candidate]

    # ── Summary banner ────────────────────────────────────────────────────
    summary_rows = ""
    for a in buy_candidates:
        summary_rows += f"""
          <tr>
            <td><strong>{a.company}</strong> ({a.ticker})</td>
            <td style="color:{_drop_color(a.drop_pct)};font-weight:bold">{a.drop_pct:+.2f}%</td>
            <td style="color:{_score_color(a.score)};font-weight:bold">{a.score}/100</td>
            <td style="color:{_score_color(a.score)}">{_score_label(a.score)}</td>
          </tr>"""

    summary_section = ""
    if buy_candidates:
        summary_section = f"""
  <h3 style="color:#2e7d32">&#10003; Buy Candidates at a Glance</h3>
  <table>
    <thead><tr>
      <th>Company</th><th>Weekly Drop</th><th>Score</th><th>Signal</th>
    </tr></thead>
    <tbody>{summary_rows}</tbody>
  </table>
  <br>"""

    # ── Detail cards ──────────────────────────────────────────────────────
    cards = ""
    for a in alerts:
        sc      = a.score
        bg      = "#e8f5e9" if a.is_buy_candidate else "#fff3e0" if sc >= 30 else "#fce4ec"
        border  = _score_color(sc)
        label   = _score_label(sc)

        # Score bar (visual)
        bar_filled = sc
        bar_empty  = 100 - sc
        bar_color  = _score_color(sc)

        rsi_note = ""
        if a.rsi is not None:
            if a.rsi < 30:
                rsi_note = " ⚡ Oversold"
            elif a.rsi < 40:
                rsi_note = " ↓ Low"

        cards += f"""
  <div style="border-left:5px solid {border};background:{bg};
              margin:16px 0;padding:16px;border-radius:4px">

    <table style="width:100%;border:none">
      <tr>
        <td style="border:none;padding:0;vertical-align:top;width:55%">
          <span style="font-size:17px;font-weight:bold">{a.company}</span>
          <span style="color:#555;font-size:13px"> ({a.ticker})</span><br>
          <span style="font-size:22px;font-weight:bold;color:{_drop_color(a.drop_pct)}">
            {a.drop_pct:+.2f}%
          </span>
          <span style="color:#555;font-size:13px">
            &nbsp;{a.price_7d_ago:.2f} → {a.price_now:.2f} {a.currency}
          </span>
          {f'<br><span style="color:#555;font-size:12px">52w High: {a.week_high_52:.2f} {a.currency} &nbsp;|&nbsp; {((a.price_now/a.week_high_52)-1)*100:+.1f}% from high</span>' if a.week_high_52 else ''}
        </td>
        <td style="border:none;padding:0;vertical-align:top;text-align:right">
          <div style="font-size:28px;font-weight:bold;color:{bar_color}">{sc}/100</div>
          <div style="font-size:11px;color:{bar_color}">{label}</div>
          <div style="background:#ddd;border-radius:4px;height:8px;margin-top:6px;width:120px;display:inline-block">
            <div style="background:{bar_color};width:{bar_filled}%;height:8px;border-radius:4px"></div>
          </div>
        </td>
      </tr>
    </table>

    <table style="width:100%;margin-top:12px;font-size:13px">
      <tr>
        <th style="background:#0001;text-align:left;padding:6px 10px;width:25%">Metric</th>
        <th style="background:#0001;text-align:left;padding:6px 10px;width:25%">Value</th>
        <th style="background:#0001;text-align:left;padding:6px 10px;width:25%">Metric</th>
        <th style="background:#0001;text-align:left;padding:6px 10px;width:25%">Value</th>
      </tr>
      <tr>
        <td style="padding:5px 10px">ROE</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_pct(a.roe)}</td>
        <td style="padding:5px 10px">Debt / Equity</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_float(a.debt_to_equity)}</td>
      </tr>
      <tr style="background:#0001">
        <td style="padding:5px 10px">Free Cash Flow</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_fcf(a.free_cash_flow)}</td>
        <td style="padding:5px 10px">Gross Margin</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_pct(a.gross_margins)}</td>
      </tr>
      <tr>
        <td style="padding:5px 10px">Trailing P/E</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_float(a.trailing_pe)}</td>
        <td style="padding:5px 10px">Forward P/E</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_float(a.forward_pe)}</td>
      </tr>
      <tr style="background:#0001">
        <td style="padding:5px 10px">Dividend Yield</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_pct(a.dividend_yield)}</td>
        <td style="padding:5px 10px">Beta</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_float(a.beta)}</td>
      </tr>
      <tr>
        <td style="padding:5px 10px">RSI (14d)</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_float(a.rsi, 1)}{rsi_note}</td>
        <td style="padding:5px 10px">Analyst View</td>
        <td style="padding:5px 10px;font-weight:bold">{_fmt_rec(a.recommendation)}</td>
      </tr>
      <tr style="background:#0001">
        <td style="padding:5px 10px">Sector</td>
        <td style="padding:5px 10px;font-weight:bold">{a.sector or '—'}</td>
        <td style="padding:5px 10px">Sector ETF this week</td>
        <td style="padding:5px 10px;font-weight:bold">{_sector_context(a)}</td>
      </tr>
    </table>
  </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    body  {{ font-family: Arial, sans-serif; color: #222; max-width: 780px; margin: 0 auto; }}
    h2    {{ color: #b71c1c; }}
    h3    {{ margin-top: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
    th    {{ background: #f5f5f5; font-weight: 600; }}
    tr:nth-child(even) td {{ background: #fafafa; }}
    .footer {{ margin-top: 28px; font-size: 11px; color: #999; border-top: 1px solid #eee; padding-top: 10px; }}
  </style>
</head>
<body>
  <h2>&#9888; Stock Drop Alert &mdash; Weekly Drop &gt; {threshold:.0f}%</h2>
  <p>
    <strong>{len(alerts)}</strong> stock(s) fell more than <strong>{threshold:.0f}%</strong>
    this week &mdash; <strong style="color:#2e7d32">{len(buy_candidates)}</strong>
    scored &ge; 50/100 as potential buy candidates.
  </p>

  {summary_section}

  <h3>Full Analysis</h3>
  {cards}

  <p class="footer">
    Prices &amp; fundamentals sourced from Yahoo Finance via yfinance.<br>
    Score = ROE (20) + Low Debt (20) + Positive FCF (15) + Sector also fell (15)
            + Analyst buy (10) + RSI oversold (10) + Dividend (5) + Low beta (5).<br>
    <strong>This is not financial advice. Always do your own research.</strong>
  </p>
</body>
</html>"""


# ── Plain-text fallback ───────────────────────────────────────────────────────

def _build_plain(alerts: list[StockAlert], threshold: float) -> str:
    buy = [a for a in alerts if a.is_buy_candidate]
    lines = [
        f"STOCK DROP ALERT — Weekly Drop > {threshold:.0f}%",
        "=" * 60,
        f"{len(alerts)} stocks dropped. {len(buy)} scored ≥50/100 as buy candidates.",
        "",
    ]
    for a in alerts:
        flag = "★ BUY CANDIDATE" if a.is_buy_candidate else "  "
        lines.append(f"{flag}  {a.company} ({a.ticker})")
        lines.append(f"   Drop: {a.drop_pct:+.2f}%  |  Score: {a.score}/100")
        lines.append(f"   ROE: {_fmt_pct(a.roe)}  |  D/E: {_fmt_float(a.debt_to_equity)}"
                     f"  |  FCF: {_fmt_fcf(a.free_cash_flow)}")
        lines.append(f"   P/E: {_fmt_float(a.trailing_pe)}  |  RSI: {_fmt_float(a.rsi,1)}"
                     f"  |  Analyst: {_fmt_rec(a.recommendation)}")
        lines.append(f"   Sector ({a.sector or '?'}): {_sector_context(a)}")
        lines.append("")
    lines.append("Prices from Yahoo Finance. Not financial advice.")
    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def send_alert(
    alerts: list[StockAlert],
    threshold: float,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    sender: str,
    recipients: list[str],
    use_tls: bool = True,
) -> None:
    buy = sum(1 for a in alerts if a.is_buy_candidate)
    subject = (
        f"[Stock Alert] {len(alerts)} dropped >{threshold:.0f}% "
        f"— {buy} buy candidate(s)"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(recipients)

    msg.attach(MIMEText(_build_plain(alerts, threshold), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(alerts, threshold),  "html",  "utf-8"))

    if use_tls:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.ehlo()
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)

    try:
        server.login(smtp_user, smtp_password)
        server.sendmail(sender, recipients, msg.as_string())
        logger.info("Alert e-mail sent to %s", recipients)
    finally:
        server.quit()
