"""
Newsletter-Versand für den Newsticker
=====================================
Baut aus einer Liste von `GrowthPick`s eine moderne HTML-E-Mail (plus
Plaintext-Fallback) und verschickt sie per SMTP — gleiche Zugangsdaten wie
`notifier.py`.
"""

from __future__ import annotations

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from newsticker import GrowthPick

logger = logging.getLogger(__name__)


# ── Formatierungs-Helfer ──────────────────────────────────────────────────────
def _pct(v: float | None, signed: bool = True) -> str:
    if v is None:
        return "—"
    return f"{v*100:+.0f}%" if signed else f"{v*100:.0f}%"


def _mc(mc: float | None) -> str:
    if mc is None:
        return "—"
    if mc >= 1e12:
        return f"{mc/1e12:.1f} Bio. $"
    if mc >= 1e9:
        return f"{mc/1e9:.1f} Mrd. $"
    return f"{mc/1e6:.0f} Mio. $"


def _score_color(score: int) -> str:
    if score >= 80:
        return "#16a34a"
    if score >= 70:
        return "#65a30d"
    return "#ca8a04"


_THEME_COLORS = {
    "KI & Halbleiter":                    "#7c3aed",
    "Cloud, Software & Cybersecurity":    "#2563eb",
    "Robotik, Automation & E-Mobilität":  "#0891b2",
    "Clean Energy, Biotech & Quantum":    "#059669",
}


# ── HTML ──────────────────────────────────────────────────────────────────────
def _card(p: GrowthPick) -> str:
    theme_color = _THEME_COLORS.get(p.theme, "#475569")
    sc = _score_color(p.score)
    price = f"{p.price:,.2f} {p.currency}" if p.price else "—"
    analysts = "sehr wenige" if p.num_analysts is None else str(p.num_analysts)
    below = f"−{p.pct_below_high:.0f}%" if p.pct_below_high is not None else "—"

    # Kennzahlen — Fokus auf „früh & unentdeckt"-Signale
    metrics = [
        ("Kurs",              price),
        ("Marktkap. (klein)", _mc(p.market_cap)),
        ("Umsatzwachstum",    _pct(p.revenue_growth)),
        ("Bruttomarge",       _pct(p.gross_margins, signed=False)),
        ("Analysten",         analysts),
        ("Unter 52W-Hoch",    below),
    ]
    metric_cells = "".join(
        f'<td style="padding:6px 10px;border:1px solid #e2e8f0;">'
        f'<div style="font-size:11px;color:#64748b;">{lbl}</div>'
        f'<div style="font-size:15px;font-weight:600;color:#0f172a;">{val}</div></td>'
        + ("</tr><tr>" if (i % 3 == 2) else "")
        for i, (lbl, val) in enumerate(metrics)
    )

    risiken = (
        f'<div style="margin-top:10px;padding:10px 12px;background:#fef2f2;'
        f'border-left:3px solid #dc2626;border-radius:4px;font-size:13px;color:#7f1d1d;">'
        f'<strong>Risiko:</strong> {p.risiken}</div>'
        if p.risiken else ""
    )

    return f"""
    <div style="margin:0 0 22px;border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;
                background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.06);">
      <div style="padding:14px 18px;background:{theme_color};color:#fff;">
        <div style="display:flex;justify-content:space-between;align-items:baseline;">
          <div>
            <span style="font-size:18px;font-weight:700;">{p.company}</span>
            <span style="font-size:13px;opacity:0.85;"> · {p.ticker}</span>
          </div>
          <span style="background:rgba(255,255,255,0.22);padding:3px 10px;border-radius:20px;
                       font-size:12px;font-weight:600;">{p.theme}</span>
        </div>
      </div>
      <div style="padding:16px 18px;">
        <div style="display:inline-block;background:{sc};color:#fff;font-weight:700;
                    font-size:14px;padding:4px 12px;border-radius:20px;margin-bottom:12px;">
          Zukunfts-Score {p.score}/100
        </div>
        <table style="border-collapse:collapse;width:100%;margin-bottom:14px;">
          <tr>{metric_cells}</tr>
        </table>
        <div style="margin-bottom:10px;">
          <div style="font-size:12px;font-weight:700;color:{theme_color};text-transform:uppercase;
                      letter-spacing:0.4px;margin-bottom:3px;">Was macht die Firma?</div>
          <div style="font-size:14px;color:#334155;line-height:1.55;">{p.was or '—'}</div>
        </div>
        <div style="margin-bottom:10px;padding:10px 12px;background:#f0fdf4;border-left:3px solid {theme_color};
                    border-radius:4px;">
          <div style="font-size:12px;font-weight:700;color:{theme_color};text-transform:uppercase;
                      letter-spacing:0.4px;margin-bottom:3px;">Wachstumsthese — was noch nicht eingepreist ist</div>
          <div style="font-size:14px;color:#334155;line-height:1.55;">{p.these or '—'}</div>
        </div>
        <div style="margin-bottom:4px;">
          <div style="font-size:12px;font-weight:700;color:{theme_color};text-transform:uppercase;
                      letter-spacing:0.4px;margin-bottom:3px;">⚡ Katalysator (1–3 Jahre)</div>
          <div style="font-size:14px;color:#334155;line-height:1.55;">{p.katalysator or '—'}</div>
        </div>
        {risiken}
      </div>
    </div>"""


def _summary_row(p: GrowthPick) -> str:
    sc = _score_color(p.score)
    return f"""
      <tr>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-weight:600;color:#0f172a;">
          {p.company} <span style="color:#94a3b8;font-weight:400;">{p.ticker}</span></td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;font-size:13px;color:#475569;">{p.theme}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;color:#16a34a;font-weight:600;">
          {_pct(p.revenue_growth)}</td>
        <td style="padding:8px 10px;border-bottom:1px solid #e2e8f0;text-align:center;">
          <span style="background:{sc};color:#fff;padding:2px 9px;border-radius:12px;font-weight:700;
                       font-size:13px;">{p.score}</span></td>
      </tr>"""


def build_html(picks: list[GrowthPick]) -> str:
    today = date.today().strftime("%d.%m.%Y")
    summary = "".join(_summary_row(p) for p in picks)
    cards = "".join(_card(p) for p in picks)
    return f"""<!DOCTYPE html>
<html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <div style="max-width:680px;margin:0 auto;padding:24px 16px;">
    <div style="text-align:center;margin-bottom:24px;">
      <div style="font-size:26px;font-weight:800;color:#0f172a;">📡 Zukunfts-Newsticker</div>
      <div style="font-size:14px;color:#64748b;margin-top:4px;">
        Frühphasen-Aktien mit ungepreistem Potenzial — „Nvidia 2020" statt „Nvidia heute" · {today}</div>
    </div>

    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:16px 18px;margin-bottom:24px;">
      <div style="font-size:15px;font-weight:700;color:#0f172a;margin-bottom:10px;">
        {len(picks)} interessante{'r' if len(picks)==1 else ''} Kandidat{'' if len(picks)==1 else 'en'} diese Woche</div>
      <table style="border-collapse:collapse;width:100%;">
        <tr style="font-size:11px;color:#64748b;text-transform:uppercase;letter-spacing:0.4px;text-align:left;">
          <th style="padding:6px 10px;">Firma</th><th style="padding:6px 10px;">Thema</th>
          <th style="padding:6px 10px;">Umsatz</th><th style="padding:6px 10px;text-align:center;">Score</th></tr>
        {summary}
      </table>
    </div>

    {cards}

    <div style="margin-top:8px;padding:14px 18px;background:#f8fafc;border:1px solid #e2e8f0;
                border-radius:10px;font-size:12px;color:#94a3b8;line-height:1.55;">
      Der Zukunfts-Score sucht bewusst <strong>Frühphasen-Profile</strong>: hohes
      Umsatzwachstum, Skalierbarkeit, kleine Marktkapitalisierung, geringe
      Analystenabdeckung (noch unentdeckt) und Luft nach oben (nicht am Allzeithoch).
      Schon gelaufene Mega-Caps werden ausgeschlossen. Datenquelle: Yahoo Finance.<br>
      <strong>Keine Anlageberatung</strong> — nur zu Informationszwecken. Frühphasen-
      Aktien sind hochvolatil und riskant; bitte immer eigene Recherche betreiben.
    </div>
  </div>
</body></html>"""


def build_plain(picks: list[GrowthPick]) -> str:
    lines = [
        "ZUKUNFTS-NEWSTICKER — Auf der Suche nach dem nächsten Nvidia",
        date.today().strftime("%d.%m.%Y"),
        "=" * 60, "",
        f"{len(picks)} interessante Kandidaten diese Woche:", "",
    ]
    for p in picks:
        lines.append(f"### {p.company} ({p.ticker}) — {p.theme}")
        lines.append(f"Zukunfts-Score: {p.score}/100")
        lines.append(
            f"Umsatzwachstum: {_pct(p.revenue_growth)} | Marktkap.: {_mc(p.market_cap)} | "
            f"Bruttomarge: {_pct(p.gross_margins, signed=False)}"
        )
        if p.was:
            lines.append(f"Was: {p.was}")
        if p.these:
            lines.append(f"Wachstumsthese (ungepreist): {p.these}")
        if p.katalysator:
            lines.append(f"Katalysator: {p.katalysator}")
        if p.risiken:
            lines.append(f"Risiko: {p.risiken}")
        lines.append("")
    lines.append("-" * 60)
    lines.append("Keine Anlageberatung — nur zu Informationszwecken. Quelle: Yahoo Finance.")
    return "\n".join(lines)


# ── Versand ───────────────────────────────────────────────────────────────────
def send_newsletter(
    picks: list[GrowthPick],
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    sender: str,
    recipients: list[str],
    use_tls: bool = True,
) -> None:
    if not picks:
        logger.info("Newsticker: keine Kandidaten — keine E-Mail versendet.")
        return

    subject = f"📡 Zukunfts-Newsticker: {len(picks)} spannende Aktie(n) diese Woche"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = sender
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(build_plain(picks), "plain", "utf-8"))
    msg.attach(MIMEText(build_html(picks),  "html",  "utf-8"))

    if use_tls:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.ehlo()
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)
    try:
        server.login(smtp_user, smtp_password)
        server.sendmail(sender, recipients, msg.as_string())
        logger.info("Newsticker-E-Mail an %s gesendet.", recipients)
    finally:
        server.quit()
