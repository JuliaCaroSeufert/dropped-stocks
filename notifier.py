"""
Sends an HTML e-mail alert listing all stocks that dropped significantly.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from checker import StockAlert

logger = logging.getLogger(__name__)


def _build_html(alerts: list[StockAlert], threshold: float) -> str:
    rows = ""
    for a in alerts:
        color = "#d32f2f" if a.drop_pct <= -20 else "#e64a19"
        rows += (
            f"<tr>"
            f"<td><strong>{a.company}</strong></td>"
            f"<td>{a.ticker}</td>"
            f"<td>{a.price_7d_ago:.2f} {a.currency}</td>"
            f"<td>{a.price_now:.2f} {a.currency}</td>"
            f"<td style='color:{color};font-weight:bold'>{a.drop_pct:+.2f}%</td>"
            f"</tr>"
        )

    return f"""
<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: Arial, sans-serif; color: #222; }}
    h2   {{ color: #b71c1c; }}
    table {{ border-collapse: collapse; width: 100%; max-width: 700px; }}
    th, td {{ border: 1px solid #ddd; padding: 10px 14px; text-align: left; }}
    th   {{ background: #f5f5f5; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    .footer {{ margin-top: 20px; font-size: 12px; color: #888; }}
  </style>
</head>
<body>
  <h2>&#9888; Stock Drop Alert — Weekly Drop &gt; {threshold:.0f}%</h2>
  <p>The following stocks have fallen more than <strong>{threshold:.0f}%</strong>
     over the past 7 days:</p>
  <table>
    <thead>
      <tr>
        <th>Company</th><th>Ticker</th>
        <th>7 Days Ago</th><th>Current Price</th><th>Change</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
  <p class="footer">
    Prices sourced from Yahoo Finance. This is not financial advice.
  </p>
</body>
</html>
"""


def _build_plain(alerts: list[StockAlert], threshold: float) -> str:
    lines = [
        f"STOCK DROP ALERT — Weekly Drop > {threshold:.0f}%",
        "=" * 50,
        "",
    ]
    for a in alerts:
        lines.append(str(a))
    lines += ["", "Prices sourced from Yahoo Finance. This is not financial advice."]
    return "\n".join(lines)


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
    """
    Sends an HTML e-mail listing *alerts* via the provided SMTP credentials.
    Raises on failure so the caller can log/retry.
    """
    subject = (
        f"[Stock Alert] {len(alerts)} stock(s) dropped >{threshold:.0f}% this week"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)

    msg.attach(MIMEText(_build_plain(alerts, threshold), "plain"))
    msg.attach(MIMEText(_build_html(alerts, threshold), "html"))

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
