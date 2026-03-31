"""
Sends an HTML e-mail alert listing all stocks that dropped significantly,
enriched with quality metrics and a buy-candidate score.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from checker import StockAlert, TrendPrediction

logger = logging.getLogger(__name__)


# ── Formatting helpers ────────────────────────────────────────────────────────

def _score_color(score: int) -> str:
    if score >= 70: return "#2e7d32"   # green
    if score >= 50: return "#f57f17"   # amber
    return "#b71c1c"                   # red


def _score_label(score: int) -> str:
    if score >= 70: return "★ Starker Kaufkandidat"
    if score >= 50: return "◆ Mögliche Chance"
    return "✗ Vorsicht"


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


def _trend_badge(t: TrendPrediction | None) -> str:
    if t is None:
        return ""
    cfg = {
        "BOTTOM_LIKELY": ("#2e7d32", "#e8f5e9", "📈 Tief möglicherweise erreicht"),
        "MIXED":         ("#e65100", "#fff3e0", "⚖️  Gemischte Signale"),
        "DOWNTREND":     ("#b71c1c", "#fce4ec", "📉 Abwärtstrend läuft weiter"),
    }
    color, bg, label = cfg.get(t.verdict, ("#555", "#f5f5f5", t.verdict))

    bull_rows = "".join(
        f"<tr><td style='padding:3px 6px;color:#2e7d32'>✓</td>"
        f"<td style='padding:3px 6px'>{s}</td></tr>"
        for s in t.bull_signals
    ) or "<tr><td colspan='2' style='padding:3px 6px;color:#999'>Keine bullischen Signale</td></tr>"

    bear_rows = "".join(
        f"<tr><td style='padding:3px 6px;color:#b71c1c'>✗</td>"
        f"<td style='padding:3px 6px'>{s}</td></tr>"
        for s in t.bear_signals
    ) or "<tr><td colspan='2' style='padding:3px 6px;color:#999'>Keine bärischen Signale</td></tr>"

    return f"""
  <div style="border:1px solid {color};background:{bg};border-radius:4px;
              margin-top:12px;padding:12px">
    <div style="font-weight:bold;font-size:15px;color:{color};margin-bottom:8px">
      {label}
      <span style="font-weight:normal;font-size:12px;color:#555">
        &nbsp;— Konfidenz: {t.confidence}%
      </span>
    </div>
    <table style="width:100%;border:none;font-size:12px">
      <tr style="vertical-align:top">
        <td style="border:none;padding:0;width:50%">
          <strong style="color:#2e7d32">Bullische Signale</strong>
          <table style="border:none;margin-top:4px"><tbody>{bull_rows}</tbody></table>
        </td>
        <td style="border:none;padding:0;width:50%">
          <strong style="color:#b71c1c">Bärische Signale</strong>
          <table style="border:none;margin-top:4px"><tbody>{bear_rows}</tbody></table>
        </td>
      </tr>
    </table>
    <p style="font-size:10px;color:#888;margin:8px 0 0">
      Basiert auf: RSI-Level &amp; -Richtung · MACD-Histogramm · Bollinger Bands ·
      Momentum-Dezeleration · 5/10-Tage-MA · Volumenanalyse.
      Keine Garantie — technische Signale können scheitern.
    </p>
  </div>"""


def _interpret_fundamentals(a: StockAlert) -> str:
    """
    Highlights only the metrics that are notably good or bad for this specific
    company. Neutral / middle-of-the-road values are skipped entirely.
    """
    lines: list[tuple[str, str]] = []
    name = a.company.split(" (")[0]

    # ── ROE: only notable highs or lows ──────────────────────────────────
    if a.roe is not None:
        v = a.roe * 100
        if v >= 25:
            lines.append(("#2e7d32",
                f"<b>Eigenkapitalrendite (ROE) {v:.1f}%</b> — {name} erwirtschaftet "
                f"für jeden Euro Eigenkapital der Aktionäre {v:.1f} Cent Gewinn. "
                f"Der Marktdurchschnitt liegt bei ~15%, {name} übertrifft ihn deutlich. "
                f"Das spricht für ein Geschäftsmodell mit echtem Wettbewerbsvorteil — "
                f"Preismacht, Skaleneffekte oder strukturell hohe Eintrittsbarrieren."))
        elif v < 0:
            lines.append(("#b71c1c",
                f"<b>Eigenkapitalrendite (ROE) {v:.1f}%</b> — {name} macht derzeit "
                f"Verluste und zehrt damit am Eigenkapital der Aktionäre ab. "
                f"Das ist per se kein Ausschlusskriterium — Wachstumsunternehmen "
                f"investieren oft auf Kosten kurzfristiger Profitabilität — aber es "
                f"erhöht die Abhängigkeit von externer Finanzierung und die "
                f"Verwundbarkeit gegenüber einem Umsatzrückgang."))
        elif v < 8:
            lines.append(("#e65100",
                f"<b>Eigenkapitalrendite (ROE) {v:.1f}%</b> — Schwach. {name} erzielt "
                f"weniger als halb so viel wie der Marktdurchschnitt (~15%) auf das "
                f"eingesetzte Eigenkapital. Das deutet auf niedrige Margen, "
                f"ineffizienten Kapitaleinsatz oder strukturellen Margendruck hin."))

    # ── D/E: only very low (strength) or very high (risk) ────────────────
    if a.debt_to_equity is not None:
        v = a.debt_to_equity
        if v < 25:
            lines.append(("#2e7d32",
                f"<b>Verschuldungsgrad (D/E) {v:.0f}</b> — Nahezu schuldenfreie Bilanz. "
                f"{name} finanziert sich fast ausschließlich aus eigenen Mitteln. "
                f"Das gibt dem Unternehmen in Krisenzeiten enormen Spielraum: "
                f"keine drückende Zinslast, keine Refinanzierungsrisiken, "
                f"und die Möglichkeit, günstig Kapital aufzunehmen wenn andere es nicht können."))
        elif v > 150:
            lines.append(("#b71c1c",
                f"<b>Verschuldungsgrad (D/E) {v:.0f}</b> — Hohe Verschuldung. "
                f"Auf jeden Euro Eigenkapital kommen {v/100:.1f}€ Fremdkapital. "
                f"Das bedeutet eine erhebliche Zinslast, die bei sinkenden Umsätzen "
                f"oder steigenden Zinsen schnell existenzbedrohend werden kann. "
                f"Besonders relevant jetzt, da die aktuellen Nachrichten auf "
                f"Gegenwind für {name} hindeuten."))

    # ── FCF: always relevant, but only if notably positive or negative ────
    if a.free_cash_flow is not None:
        fcf = a.free_cash_flow
        fcf_str = _fmt_fcf(fcf)
        if fcf > 0:
            lines.append(("#2e7d32",
                f"<b>Free Cash Flow {fcf_str}</b> — Nach allen laufenden Ausgaben "
                f"und Investitionen fließen {fcf_str} als echtes Bargeld in die Kasse "
                f"von {name}. Das ist die härteste Währung in der Unternehmensanalyse: "
                f"nicht manipulierbar wie Buchgewinne, sondern reales Geld. "
                f"Es ermöglicht Dividenden, Aktienrückkäufe und Schuldenabbau "
                f"ohne auf externe Geldgeber angewiesen zu sein."))
        else:
            lines.append(("#e65100",
                f"<b>Free Cash Flow {fcf_str}</b> — {name} gibt derzeit mehr aus als "
                f"es einnimmt. Das muss kein Problem sein — viele Wachstumsunternehmen "
                f"verbrennen gezielt Kapital um Marktanteile aufzubauen. "
                f"Kritisch wird es, wenn gleichzeitig die Verschuldung steigt und "
                f"kein klarer Weg zur Profitabilität erkennbar ist."))

    # ── P/E: only cheap or expensive, skip the middle ────────────────────
    if a.trailing_pe is not None:
        v = a.trailing_pe
        if v < 0:
            lines.append(("#b71c1c",
                f"<b>KGV negativ</b> — {name} schreibt Verluste, daher ist kein "
                f"sinnvolles Kurs-Gewinn-Verhältnis berechenbar. Die Bewertung "
                f"hängt vollständig an der Erwartung künftiger Gewinne — "
                f"enttäuschte Wachstumshoffnungen können hier zu starken Korrekturen führen."))
        elif v < 11:
            lines.append(("#2e7d32",
                f"<b>KGV {v:.1f}x</b> — Günstige Bewertung: für jeden Euro Jahresgewinn "
                f"zahlt man aktuell nur {v:.1f}€. Das liegt weit unter dem "
                f"S&P-500-Durchschnitt (~20x) und könnte echte Unterbewertung bedeuten — "
                f"oder der Markt preist strukturelle Risiken ein, die in den "
                f"Nachrichten sichtbar werden."))
        elif v > 40:
            lines.append(("#b71c1c",
                f"<b>KGV {v:.1f}x</b> — Sehr ambitionierte Bewertung: der Markt zahlt "
                f"{v:.1f}€ für jeden Euro heutigen Jahresgewinns. Das impliziert "
                f"hohe Wachstumserwartungen, die {name} über viele Jahre liefern muss. "
                f"Gerade in einem Umfeld mit negativen Nachrichten ist das Potenzial "
                f"für eine Bewertungskorrektur erheblich."))
        elif v > 28:
            lines.append(("#e65100",
                f"<b>KGV {v:.1f}x</b> — Überdurchschnittliche Bewertung (~20x Markt). "
                f"{name} muss Gewinnwachstum liefern, um den Aufschlag zu rechtfertigen. "
                f"Bei negativen Nachrichten sind solche Bewertungen anfälliger "
                f"für stärkere Korrekturen als günstigere Wettbewerber."))

    # ── Gross Margin: only high (competitive moat) or low (risk) ─────────
    if a.gross_margins is not None:
        v = a.gross_margins * 100
        if v >= 55:
            lines.append(("#2e7d32",
                f"<b>Bruttomarge {v:.1f}%</b> — Von jedem Umsatz-Euro verbleiben "
                f"{v:.0f} Cent nach Produktionskosten bei {name}. "
                f"Das ist ein Zeichen echter Preismacht: {name} kann Preise setzen "
                f"statt nehmen, was auf starke Marken, Netzwerkeffekte oder "
                f"schwer kopierbare Technologie hindeutet. Hohe Margen puffern "
                f"auch Umsatzrückgänge deutlich besser ab."))
        elif v < 18:
            lines.append(("#e65100",
                f"<b>Bruttomarge {v:.1f}%</b> — Sehr enge Marge: von jedem "
                f"Umsatz-Euro bleiben nur {v:.0f} Cent nach direkten Kosten. "
                f"Das lässt wenig Spielraum für Betriebskosten, Investitionen "
                f"und Gewinne. Kostensteigerungen (Material, Energie, Löhne) "
                f"können schnell das Ergebnis ins Negative drehen."))

    # ── Beta: only defensive (positive) or highly volatile (risk) ────────
    if a.beta is not None:
        v = a.beta
        if v < 0.55:
            lines.append(("#2e7d32",
                f"<b>Beta {v:.2f}</b> — Sehr defensiver Charakter: {name} bewegt "
                f"sich historisch kaum mit dem Gesamtmarkt. Selbst in breiten "
                f"Marktabverkäufen bleibt die Aktie relativ stabil — sie fällt "
                f"weniger, steigt aber in Rallyes auch weniger stark. "
                f"Attraktiv als Stabilitätsanker im Portfolio."))
        elif v > 1.7:
            lines.append(("#b71c1c",
                f"<b>Beta {v:.2f}</b> — Hohe Marktempfindlichkeit: historisch "
                f"verstärkt {name} Marktbewegungen um den Faktor {v:.1f}. "
                f"Bei einem Markteinbruch von 10% fällt {name} typischerweise "
                f"~{v*10:.0f}%. Das erklärt auch den aktuellen Rückgang bei "
                f"breitem Marktdruck. Die Kehrseite: in Aufwärtsphasen "
                f"outperformt die Aktie entsprechend."))

    # ── RSI: only at extremes ─────────────────────────────────────────────
    if a.rsi is not None:
        v = a.rsi
        if v < 25:
            lines.append(("#1565c0",
                f"<b>RSI {v:.0f} — extrem überverkauft</b> — Der Relative-Stärke-Index "
                f"misst ob eine Aktie technisch über- oder unterverkauft ist. "
                f"Werte unter 30 gelten als Warnsignal für Überverkauf, unter 25 "
                f"als extreme Zone. {name} befindet sich dort: der Kurs ist so "
                f"stark gefallen, dass kurzfristig Gegenbewegungen wahrscheinlicher "
                f"werden — ob es sich um eine Erholung oder nur ein kurzes Aufbäumen "
                f"handelt, hängt von den fundamentalen Ursachen ab."))
        elif v < 30:
            lines.append(("#1565c0",
                f"<b>RSI {v:.0f} — überverkauft</b> — Technisch befindet sich "
                f"{name} in der klassischen Überverkauft-Zone (unter 30). "
                f"Viele Swing-Trader nutzen genau diesen Bereich als Einstiegspunkt, "
                f"weil der kurzfristige Verkaufsdruck statistisch nachlässt. "
                f"Wichtig: das RSI-Signal sagt nichts über die fundamentale "
                f"Qualität aus — ein schwaches Unternehmen kann auch lange "
                f"überverkauft bleiben."))
        elif v > 70:
            lines.append(("#b71c1c",
                f"<b>RSI {v:.0f} — überkauft</b> — Trotz des Wochenrückgangs ist "
                f"{name} technisch noch im überkauften Bereich (über 70). "
                f"Das deutet darauf hin, dass die Aktie vor dem aktuellen Einbruch "
                f"stark gelaufen ist und die Korrektur möglicherweise noch nicht "
                f"abgeschlossen ist."))

    # ── Dividend: only if meaningful (>1.5%) ─────────────────────────────
    if a.dividend_yield and a.dividend_yield >= 0.015:
        v = a.dividend_yield * 100
        annual_per_10k = 10000 * a.dividend_yield
        lines.append(("#2e7d32",
            f"<b>Dividendenrendite {v:.1f}%</b> — Wer {name} heute für 10.000€ kauft, "
            f"erhält bei gleichbleibender Ausschüttung jährlich ~{annual_per_10k:.0f}€ "
            f"Dividende — unabhängig davon ob der Kurs steigt oder fällt. "
            f"Die aktuelle Rendite von {v:.1f}% liegt "
            + ("deutlich über dem Marktdurchschnitt (~1.5%) " if v > 3 else
               "über dem Marktdurchschnitt (~1.5%) ")
            + f"und bietet einen gewissen Puffer gegen weiteren Kursrückgang."))

    # ── 52w range: only show if near low or deeply off high ──────────────
    if a.week_high_52 and a.week_low_52:
        from_high = (a.price_now / a.week_high_52 - 1) * 100
        from_low  = (a.price_now / a.week_low_52  - 1) * 100
        if from_low < 10:
            lines.append(("#b71c1c",
                f"<b>Jahrestief in Reichweite</b> — Mit {a.price_now:.2f} {a.currency} "
                f"notiert {name} nur noch {from_low:.1f}% über dem 52-Wochen-Tief "
                f"({a.week_low_52:.2f} {a.currency}). Das Jahreshoch lag bei "
                f"{a.week_high_52:.2f} {a.currency} — die Aktie hat also bereits "
                f"{abs(from_high):.0f}% von ihrem Hoch verloren. "
                f"Ein Unterschreiten des Jahrestiefs würde charttechnisch als "
                f"starkes Warnsignal gewertet und könnte weiteren "
                f"algorithmischen Verkaufsdruck auslösen."))
        elif from_high < -40:
            lines.append(("#e65100",
                f"<b>Tief im Jahresbereich</b> — {name} handelt {abs(from_high):.0f}% "
                f"unter seinem 52-Wochen-Hoch ({a.week_high_52:.2f} {a.currency}) "
                f"und hat damit mehr als {abs(from_high):.0f}% seines Jahreshöchstwerts "
                f"abgegeben. Das Jahrestief liegt bei {a.week_low_52:.2f} {a.currency} "
                f"— noch {from_low:.0f}% entfernt. Eine so starke Korrektur vom Hoch "
                f"kann Einstiegschance oder Vorbote weiterer Schwäche sein."))

    if not lines:
        return ""

    rows = "".join(
        f'<div style="margin:8px 0;font-size:12.5px;color:{color};'
        f'border-left:3px solid {color};padding:4px 0 4px 10px;line-height:1.55">'
        f'{text}</div>'
        for color, text in lines
    )
    return (
        f'<div style="margin-top:14px;padding:12px 16px;background:#fafafa;'
        f'border:1px solid #e0e0e0;border-radius:4px">'
        f'<div style="font-weight:bold;font-size:12px;color:#555;margin-bottom:10px;'
        f'text-transform:uppercase;letter-spacing:0.5px">'
        f'Was bedeuten die Kennzahlen für {name}?</div>'
        f'{rows}</div>'
    )


def _news_block(
    headlines: list[str],
    reason: str | None = None,
    urls: list[str] | None = None,
) -> str:
    if not headlines and not reason:
        return ""
    reason_html = ""
    if reason:
        reason_html = (
            f'<div style="font-size:13.5px;font-weight:bold;color:#1a237e;'
            f'background:#e8eaf6;padding:8px 12px;border-radius:3px;margin-bottom:10px">'
            f'{reason}</div>'
        )
    items_html = ""
    if headlines:
        items = ""
        for i, h in enumerate(headlines):
            url = (urls or [])[i] if urls and i < len(urls) else ""
            if url:
                items += (
                    f"<li style='margin:5px 0'>"
                    f"<a href='{url}' style='color:#1565c0;text-decoration:none' "
                    f"target='_blank'>{h}</a></li>"
                )
            else:
                items += f"<li style='margin:5px 0;color:#444'>{h}</li>"
        items_html = (
            f'<div style="font-size:11.5px;color:#666;margin-bottom:4px">'
            f'Aktuelle Schlagzeilen:</div>'
            f'<ul style="margin:0;padding-left:18px;font-size:12.5px">{items}</ul>'
        )
    return (
        f'<div style="margin-top:12px;padding:10px 14px;background:#f9f9f9;'
        f'border-left:3px solid #3949ab;border-radius:3px">'
        f'<div style="font-weight:bold;font-size:12px;color:#3949ab;margin-bottom:8px;'
        f'text-transform:uppercase;letter-spacing:0.5px">Warum ist die Aktie gefallen?</div>'
        f'{reason_html}{items_html}'
        f'</div>'
    )


def _fmt_52w_range(a: StockAlert) -> str:
    parts = []
    if a.week_high_52:
        pct_from_high = (a.price_now / a.week_high_52 - 1) * 100
        parts.append(f"52w Hoch: {a.week_high_52:.2f} {a.currency} ({pct_from_high:+.1f}%)")
    if a.week_low_52:
        pct_from_low = (a.price_now / a.week_low_52 - 1) * 100
        color = "#b71c1c" if pct_from_low < 8 else "#555"
        parts.append(
            f'<span style="color:{color}">52w Tief: {a.week_low_52:.2f} {a.currency} '
            f"(+{pct_from_low:.1f}% darüber)</span>"
        )
    if not parts:
        return ""
    return f'<br><span style="color:#555;font-size:12px">{" &nbsp;|&nbsp; ".join(parts)}</span>'


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

    # ── Metrics row helper ────────────────────────────────────────────────
    def _mrow(lbl1: str, val1: str, lbl2: str, val2: str, shade: bool = False) -> str:
        bg = "background:#fafafa;" if shade else ""
        return (
            f'<tr style="{bg}">'
            f'<td style="padding:5px 10px 5px 0;color:#999;font-size:12px;white-space:nowrap'
            f';vertical-align:top">{lbl1}</td>'
            f'<td style="padding:5px 16px 5px 0;font-weight:600;font-size:13px;color:#1a1a2e'
            f';vertical-align:top">{val1}</td>'
            f'<td style="padding:5px 10px 5px 0;color:#999;font-size:12px;white-space:nowrap'
            f';vertical-align:top">{lbl2}</td>'
            f'<td style="padding:5px 0;font-weight:600;font-size:13px;color:#1a1a2e'
            f';vertical-align:top">{val2}</td>'
            f'</tr>'
        )

    # ── Summary banner ────────────────────────────────────────────────────
    summary_rows = ""
    for a in buy_candidates:
        summary_rows += (
            f'<tr>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #e8f5e9">'
            f'<strong style="color:#1a1a2e">{a.company}</strong>'
            f'<span style="color:#aaa;font-size:12px"> · {a.ticker}</span></td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #e8f5e9;'
            f'color:{_drop_color(a.drop_pct)};font-weight:700">{a.drop_pct:+.2f}%</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #e8f5e9;'
            f'color:{_score_color(a.score)};font-weight:700">{a.score}/100</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #e8f5e9;'
            f'color:{_score_color(a.score)};font-size:12px">{_score_label(a.score)}</td>'
            f'</tr>'
        )

    summary_section = ""
    if buy_candidates:
        summary_section = (
            f'<div style="background:#fff;border-radius:8px;border:1px solid #c8e6c9;'
            f'margin-bottom:28px;overflow:hidden">'
            f'<div style="background:#e8f5e9;padding:11px 16px;border-bottom:1px solid #c8e6c9">'
            f'<span style="font-size:11px;font-weight:700;color:#2e7d32;'
            f'text-transform:uppercase;letter-spacing:.8px">✓ Kaufkandidaten im Überblick</span>'
            f'</div>'
            f'<table style="width:100%;border-collapse:collapse;font-size:13px">'
            f'<thead><tr style="background:#f9fbf9">'
            f'<th style="padding:8px 12px;text-align:left;font-weight:600;color:#777;'
            f'border-bottom:1px solid #e0e0e0;font-size:11px;text-transform:uppercase;'
            f'letter-spacing:.5px">Unternehmen</th>'
            f'<th style="padding:8px 12px;text-align:left;font-weight:600;color:#777;'
            f'border-bottom:1px solid #e0e0e0;font-size:11px;text-transform:uppercase;'
            f'letter-spacing:.5px">Wochenverlust</th>'
            f'<th style="padding:8px 12px;text-align:left;font-weight:600;color:#777;'
            f'border-bottom:1px solid #e0e0e0;font-size:11px;text-transform:uppercase;'
            f'letter-spacing:.5px">Score</th>'
            f'<th style="padding:8px 12px;text-align:left;font-weight:600;color:#777;'
            f'border-bottom:1px solid #e0e0e0;font-size:11px;text-transform:uppercase;'
            f'letter-spacing:.5px">Signal</th>'
            f'</tr></thead>'
            f'<tbody>{summary_rows}</tbody>'
            f'</table>'
            f'</div>'
        )

    # ── Detail cards ──────────────────────────────────────────────────────
    cards = ""
    for a in alerts:
        sc       = a.score
        border   = _score_color(sc)
        label    = _score_label(sc)
        score_bg = "#e8f5e9" if sc >= 70 else "#fff3e0" if sc >= 50 else "#fce4ec"

        rsi_note = ""
        if a.rsi is not None:
            if a.rsi < 30:   rsi_note = " ⚡ überverkauft"
            elif a.rsi < 40: rsi_note = " ↓ tief"

        metrics = (
            _mrow("ROE", _fmt_pct(a.roe),
                  "Verschuldungsgrad", _fmt_float(a.debt_to_equity)) +
            _mrow("Free Cash Flow", _fmt_fcf(a.free_cash_flow),
                  "Bruttomarge", _fmt_pct(a.gross_margins), shade=True) +
            _mrow("KGV (aktuell)", _fmt_float(a.trailing_pe),
                  "KGV (Prognose)", _fmt_float(a.forward_pe)) +
            _mrow("Dividendenrendite", _fmt_pct(a.dividend_yield),
                  "Beta", _fmt_float(a.beta), shade=True) +
            _mrow("RSI (14T)", f"{_fmt_float(a.rsi, 1)}{rsi_note}",
                  "Analysten-Konsens", _fmt_rec(a.recommendation)) +
            _mrow("Sektor", a.sector or "—",
                  "Sektor-ETF diese Woche", _sector_context(a), shade=True)
        )

        cards += (
            # Card wrapper: white, rounded, subtle shadow, colored top border
            f'<div style="background:#fff;border-radius:8px;'
            f'box-shadow:0 1px 6px rgba(0,0,0,.07);'
            f'margin-bottom:20px;overflow:hidden;border-top:4px solid {border}">'

            # ── Card header ──────────────────────────────────────────────
            f'<div style="padding:18px 20px 14px">'
            f'<table style="width:100%;border:none;border-collapse:collapse"><tr>'

            f'<td style="border:none;padding:0;vertical-align:top">'
            f'<div style="font-size:17px;font-weight:700;color:#1a1a2e;line-height:1.2">'
            f'{a.company}</div>'
            f'<div style="font-size:12px;color:#aaa;margin-top:2px">{a.ticker}</div>'
            f'<div style="margin-top:10px">'
            f'<span style="font-size:26px;font-weight:700;color:{_drop_color(a.drop_pct)}">'
            f'{a.drop_pct:+.2f}%</span>'
            f'<span style="font-size:12px;color:#888;margin-left:8px">'
            f'{a.price_7d_ago:.2f} → {a.price_now:.2f} {a.currency}</span>'
            f'</div>'
            f'{_fmt_52w_range(a)}'
            f'</td>'

            f'<td style="border:none;padding:0 0 0 16px;vertical-align:top;text-align:right">'
            f'<div style="display:inline-block;background:{score_bg};border-radius:8px;'
            f'padding:10px 14px;text-align:center;min-width:60px">'
            f'<div style="font-size:24px;font-weight:700;color:{border};line-height:1">{sc}</div>'
            f'<div style="font-size:10px;color:#aaa;margin-top:2px">/100</div>'
            f'</div>'
            f'<div style="font-size:11px;color:{border};margin-top:6px;font-weight:600">'
            f'{label}</div>'
            f'</td>'

            f'</tr></table>'
            f'</div>'

            # ── Kennzahlen ───────────────────────────────────────────────
            f'<div style="padding:12px 20px 16px;border-top:1px solid #f0f0f0">'
            f'<div style="font-size:10px;font-weight:700;color:#ccc;'
            f'text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px">Kennzahlen</div>'
            f'<table style="width:100%;border:none;border-collapse:collapse">'
            f'{metrics}'
            f'</table>'
            f'</div>'

            f'{_interpret_fundamentals(a)}'
            f'{_trend_badge(a.trend)}'
            f'{_news_block(a.news_headlines, a.news_reason, a.news_urls)}'
            f'</div>'
        )

    # ── Glossary ──────────────────────────────────────────────────────────
    def _grow(term: str, benchmark: str, description: str, shade: bool = False) -> str:
        bg = "background:#fafafa;" if shade else ""
        last_td_style = "padding:9px 12px" if shade else "padding:9px 12px"
        return (
            f'<tr style="{bg}">'
            f'<td style="padding:9px 12px;vertical-align:top;border-bottom:1px solid #f0f0f0">'
            f'{term}</td>'
            f'<td style="padding:9px 12px;vertical-align:top;border-bottom:1px solid #f0f0f0;'
            f'font-size:12px;color:#666">{benchmark}</td>'
            f'<td style="padding:9px 12px;border-bottom:1px solid #f0f0f0;'
            f'font-size:12.5px">{description}</td>'
            f'</tr>'
        )

    glossary = (
        f'<div style="margin-top:36px">'
        f'<div style="font-size:10px;font-weight:700;color:#bbb;text-transform:uppercase;'
        f'letter-spacing:.8px;margin-bottom:12px">📚 Kennzahlen erklärt</div>'
        f'<table style="width:100%;border-collapse:collapse;font-size:12.5px;'
        f'border:1px solid #e8e8e8;border-radius:6px;overflow:hidden">'
        f'<thead><tr style="background:#f5f5f5">'
        f'<th style="padding:10px 12px;text-align:left;font-weight:600;color:#555;'
        f'border-bottom:1px solid #e0e0e0;width:18%">Kennzahl</th>'
        f'<th style="padding:10px 12px;text-align:left;font-weight:600;color:#555;'
        f'border-bottom:1px solid #e0e0e0;width:22%">Gut / Schlecht</th>'
        f'<th style="padding:10px 12px;text-align:left;font-weight:600;color:#555;'
        f'border-bottom:1px solid #e0e0e0">Was sie bedeutet</th>'
        f'</tr></thead><tbody>'
        + _grow("<strong>Wochenverlust</strong>", "—",
                "Kursrückgang der Aktie innerhalb der letzten 7 Tage. Ab –10 % wird der Alert "
                "ausgelöst. Ein starker Rückgang allein sagt noch nichts über die Qualität des "
                "Unternehmens aus — erst die anderen Kennzahlen zeigen, ob es eine Kaufgelegenheit "
                "ist oder ein strukturelles Problem vorliegt.")
        + _grow("<strong>Score</strong>", "≥ 70 stark / ≥ 50 möglich / &lt; 50 Vorsicht",
                "Zusammenfassung aller Qualitätssignale auf einer Skala von 0–100. Je höher der "
                "Score, desto wahrscheinlicher handelt es sich um ein grundsolides Unternehmen, "
                "das gerade günstig bewertet ist. Punkte kommen aus: ROE (20) + Schulden (20) + "
                "FCF (15) + Sektorrückgang (15) + Analysten (10) + RSI (10) + Dividende (5) + Beta (5).",
                shade=True)
        + _grow("<strong>ROE</strong> <small style='color:#999'>Return on Equity</small>",
                "≥ 15 % gut / &lt; 0 % schlecht",
                "Eigenkapitalrendite — zeigt, wie viel Gewinn das Management aus dem investierten "
                "Eigenkapital der Aktionäre herausholt. Ein dauerhaft hoher ROE (≥ 15 %) ist ein "
                "starkes Zeichen für einen Wettbewerbsvorteil (Burggraben). Beispiel: Coca-Cola, "
                "Apple. Achtung: Bei sehr hohen Schulden kann der ROE künstlich aufgebläht sein.")
        + _grow("<strong>Verschuldungsgrad</strong> <small style='color:#999'>Debt / Equity</small>",
                "&lt; 80 gut / &gt; 200 riskant",
                "Verhältnis von Fremdkapital zu Eigenkapital (in %). Ein niedriger Wert bedeutet, "
                "das Unternehmen ist wenig verschuldet und kann Krisen besser überstehen — Zinsen "
                "müssen auch in schlechten Jahren bezahlt werden. Branchen wie Banken und Versorger "
                "haben strukturell höhere Werte, was normal ist.",
                shade=True)
        + _grow("<strong>Free Cash Flow</strong>", "Positiv = gut",
                "Geld, das nach allen Investitionen und Betriebskosten wirklich übrig bleibt. "
                "Anders als der Gewinn (der durch Bilanzierung beeinflusst werden kann) lügt der "
                "Cashflow nicht. Unternehmen mit positivem FCF können Dividenden zahlen, Schulden "
                "tilgen und in Krisen selbst überleben — ohne neue Aktien ausgeben zu müssen.")
        + _grow("<strong>Bruttomarge</strong> <small style='color:#999'>Gross Margin</small>",
                "Je höher, desto besser",
                "Anteil des Umsatzes, der nach den reinen Produktionskosten übrig bleibt. Eine "
                "hohe und stabile Bruttomarge zeigt, dass das Unternehmen Preissetzungsmacht hat "
                "(z. B. Luxusgüter, Software). Niedrige Margen &lt; 20 % deuten auf hartes "
                "Wettbewerbsumfeld hin (z. B. Handel, Rohstoffe).",
                shade=True)
        + _grow("<strong>KGV (aktuell)</strong> <small style='color:#999'>Trailing P/E</small>",
                "Kontextabhängig",
                "Aktueller Kurs geteilt durch den Gewinn der letzten 12 Monate. Zeigt, wie viel "
                "Anleger bereit sind für €1 Gewinn zu zahlen. Günstig oder teuer hängt stark vom "
                "Sektor ab — Tech-Aktien haben historisch höhere KGVs als Banken. Wichtig: mit dem "
                "Sektor-Durchschnitt und dem eigenen historischen KGV vergleichen.")
        + _grow("<strong>KGV (Prognose)</strong> <small style='color:#999'>Forward P/E</small>",
                "Niedriger als aktuell = Wachstum erwartet",
                "Wie KGV (aktuell), aber basierend auf den Gewinnschätzungen der nächsten 12 Monate. "
                "Wenn Forward P/E deutlich unter Trailing P/E liegt, erwartet der Markt steigende "
                "Gewinne — ein gutes Zeichen. Liegt er höher, werden sinkende Gewinne erwartet.",
                shade=True)
        + _grow("<strong>Dividendenrendite</strong>",
                "&gt; 2 % solide / &gt; 6 % prüfen",
                "Jährliche Dividende in % des aktuellen Kurses. Unternehmen, die auch in Krisen "
                "Dividende zahlen (oder erhöhen), zeigen damit finanzielle Stärke. Sehr hohe "
                "Renditen (&gt; 6–7 %) können aber eine Warnung sein, dass der Markt eine "
                "Kürzung erwartet.")
        + _grow("<strong>Beta</strong>", "&lt; 1 stabil / &gt; 1,5 volatil",
                "Misst, wie stark die Aktie im Vergleich zum Gesamtmarkt schwankt. Beta = 1,0: "
                "bewegt sich wie der Markt. Beta = 0,5: halb so volatil (z. B. Nestlé). "
                "Beta = 2,0: doppelt so volatil. Bei Krisenrückgängen fallen hochvolatile Aktien "
                "oft überproportional — erholen sich aber auch schneller.",
                shade=True)
        + _grow("<strong>RSI (14T)</strong> <small style='color:#999'>Relative Strength Index</small>",
                "&lt; 30 überverkauft / &gt; 70 überkauft",
                "Technischer Indikator (0–100), der zeigt ob eine Aktie kurzfristig zu stark "
                "gefallen (überverkauft) oder gestiegen (überkauft) ist. RSI unter 30 bedeutet: "
                "die Aktie wurde vermutlich emotional zu stark abverkauft — statistisch folgt "
                "häufig eine Gegenbewegung nach oben. Kein Garant, aber ein nützliches Zusatzsignal.")
        + _grow("<strong>Analysten-Konsens</strong>", "Buy / Strong Buy = positiv",
                "Konsensus-Empfehlung aller Analysten, die diese Aktie abdecken (aggregiert von "
                "Yahoo Finance). \"Strong Buy\" bedeutet, die Mehrheit der Profis erwartet "
                "Kurssteigerungen. Wichtig: Analysten liegen oft falsch — als ein Signal unter "
                "mehreren verwenden, nicht allein.",
                shade=True)
        + _grow("<strong>Sektor-ETF diese Woche</strong>", "Sektor gefallen = Makro-Krise",
                "Wochenperformance des zugehörigen Sektor-ETFs (z. B. XLK für Tech, XLF für "
                "Finanzwerte). Wenn der gesamte Sektor ähnlich stark gefallen ist, liegt der "
                "Grund wahrscheinlich in externen Faktoren (Zinsen, Zölle, Rezessionsangst) — "
                "nicht im Unternehmen selbst. Wenn nur diese Aktie fiel, aber der Sektor stabil "
                "blieb → unternehmens-spezifisches Problem → mehr Vorsicht.")
        + _grow("<strong>52w Hoch</strong>", "Je größer Abstand, desto günstiger relativ",
                "Höchster Kurs der letzten 52 Wochen. Der prozentuale Abstand vom Jahreshoch "
                "zeigt wie weit die Aktie bereits korrigiert hat. –30 % vom Hoch bei einem "
                "Qualitätsunternehmen kann eine attraktive Einstiegsgelegenheit sein — "
                "vorausgesetzt die Fundamentaldaten sind intakt.",
                shade=True)
        + _grow("<strong>52w Tief</strong>", "&lt; 8% darüber = kritisch",
                "Niedrigster Kurs der letzten 52 Wochen. Liegt der aktuelle Kurs nahe am "
                "Jahrestief (&lt; 8% darüber), testet er eine kritische Unterstützungszone — "
                "fällt er darunter, ist das ein starkes Warnsignal. Je mehr Abstand nach oben, "
                "desto mehr Puffer hat die Aktie noch vor einem neuen Jahrestief.")
        + f'</tbody></table></div>'
    )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
      color: #333;
      background: #eef0f3;
      margin: 0;
      padding: 0;
    }}
    a {{ color: #1565c0; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div style="max-width:700px;margin:0 auto;background:#eef0f3">

    <!-- Header -->
    <div style="background:#1b2a4a;padding:28px 28px 22px">
      <div style="font-size:11px;font-weight:700;color:#7a9cc4;text-transform:uppercase;
                  letter-spacing:1.2px;margin-bottom:6px">Kursüberwachung</div>
      <div style="font-size:26px;font-weight:700;color:#fff;letter-spacing:-.3px">
        ⚠&nbsp; Kurswarnung
      </div>
      <div style="font-size:14px;color:#8ab0d0;margin-top:8px">
        <strong style="color:#fff">{len(alerts)}</strong> Aktie(n) mit mehr als
        <strong style="color:#fff">{threshold:.0f}%</strong> Wochenverlust
        &nbsp;·&nbsp;
        <strong style="color:#81c784">{len(buy_candidates)}</strong>
        Kaufkandidat(en)&nbsp;≥&nbsp;50&nbsp;Punkte
      </div>
    </div>

    <!-- Content -->
    <div style="padding:24px 20px">

      {summary_section}

      <div style="font-size:10px;font-weight:700;color:#bbb;text-transform:uppercase;
                  letter-spacing:.8px;margin-bottom:14px">Detailanalyse</div>

      {cards}

      {glossary}

    </div>

    <!-- Footer -->
    <div style="padding:16px 24px 24px;font-size:11px;color:#aaa;background:#f4f5f7;
                border-top:1px solid #dde0e6;text-align:center;line-height:1.7">
      Kurse &amp; Fundamentaldaten von Yahoo Finance via yfinance.<br>
      <strong style="color:#888">Dies ist keine Anlageberatung.
      Eigene Recherche ist unbedingt erforderlich.</strong>
    </div>

  </div>
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
        low_note = (
            f"  |  52w Tief: {a.week_low_52:.2f} "
            f"(+{(a.price_now/a.week_low_52-1)*100:.1f}% darüber)"
            if a.week_low_52 else ""
        )
        high_note = (
            f"52w Hoch: {a.week_high_52:.2f} "
            f"({(a.price_now/a.week_high_52-1)*100:+.1f}%)"
            if a.week_high_52 else ""
        )
        if high_note or low_note:
            lines.append(f"   {high_note}{low_note}")
        lines.append(f"   Sector ({a.sector or '?'}): {_sector_context(a)}")
        if a.trend:
            lines.append(f"   Trend-Prognose: {a.trend.verdict}  (Konfidenz: {a.trend.confidence}%)")
            for s in a.trend.bull_signals:
                lines.append(f"     ✓ {s}")
            for s in a.trend.bear_signals:
                lines.append(f"     ✗ {s}")
        if a.news_reason:
            lines.append(f"   {a.news_reason}")
        if a.news_headlines:
            lines.append("   Aktuelle Schlagzeilen:")
            for h in a.news_headlines:
                lines.append(f"     • {h}")
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
