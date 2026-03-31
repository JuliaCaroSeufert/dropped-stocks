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
          {_fmt_52w_range(a)}
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
    {_interpret_fundamentals(a)}
    {_trend_badge(a.trend)}
    {_news_block(a.news_headlines, a.news_reason, a.news_urls)}
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

  <h3 style="margin-top:32px;color:#37474f">&#128218; Kennzahlen erklärt</h3>
  <table style="font-size:13px">
    <thead>
      <tr>
        <th style="width:18%">Kennzahl</th>
        <th style="width:18%">Gut / Schlecht</th>
        <th>Was sie bedeutet &amp; warum sie wichtig ist</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>Weekly Drop</strong></td>
        <td>—</td>
        <td>Kursrückgang der Aktie innerhalb der letzten 7 Tage. Ab –10 % wird
            der Alert ausgelöst. Ein starker Rückgang allein sagt noch nichts über
            die Qualität des Unternehmens aus — erst die anderen Kennzahlen zeigen,
            ob es eine Kaufgelegenheit ist oder ein strukturelles Problem vorliegt.</td>
      </tr>
      <tr>
        <td><strong>Score</strong></td>
        <td>≥ 70 stark &nbsp;/&nbsp; ≥ 50 möglich &nbsp;/&nbsp; &lt; 50 Vorsicht</td>
        <td>Zusammenfassung aller Qualitätssignale auf einer Skala von 0–100.
            Je höher der Score, desto wahrscheinlicher handelt es sich um ein
            grundsolides Unternehmen, das gerade günstig bewertet ist.
            Punkte kommen aus: ROE (20) + Schulden (20) + FCF (15) +
            Sektorrückgang (15) + Analysten (10) + RSI (10) + Dividende (5) + Beta (5).</td>
      </tr>
      <tr>
        <td><strong>ROE</strong><br><small>Return on Equity</small></td>
        <td>≥ 15 % gut &nbsp;/&nbsp; &lt; 0 % schlecht</td>
        <td>Eigenkapitalrendite — zeigt, wie viel Gewinn das Management aus dem
            investierten Eigenkapital der Aktionäre herausholt.
            Ein dauerhaft hoher ROE (≥ 15 %) ist ein starkes Zeichen für einen
            Wettbewerbsvorteil (Burggraben). Beispiel: Coca-Cola, Apple.
            Achtung: Bei sehr hohen Schulden kann der ROE künstlich aufgebläht sein.</td>
      </tr>
      <tr>
        <td><strong>Debt / Equity</strong><br><small>Verschuldungsgrad</small></td>
        <td>&lt; 80 gut &nbsp;/&nbsp; &gt; 200 riskant</td>
        <td>Verhältnis von Fremdkapital zu Eigenkapital (in %).
            Ein niedriger Wert bedeutet, das Unternehmen ist wenig verschuldet und
            kann Krisen besser überstehen — Zinsen müssen auch in schlechten Jahren
            bezahlt werden. Branchen wie Banken und Versorger haben strukturell
            höhere Werte, was normal ist.</td>
      </tr>
      <tr>
        <td><strong>Free Cash Flow</strong><br><small>Freier Cashflow</small></td>
        <td>Positiv = gut</td>
        <td>Geld, das nach allen Investitionen und Betriebskosten wirklich übrig bleibt.
            Anders als der Gewinn (der durch Bilanzierung beeinflusst werden kann)
            lügt der Cashflow nicht. Unternehmen mit positivem FCF können
            Dividenden zahlen, Schulden tilgen und in Krisen selbst überleben —
            ohne neue Aktien ausgeben zu müssen.</td>
      </tr>
      <tr>
        <td><strong>Gross Margin</strong><br><small>Bruttomarge</small></td>
        <td>Je höher, desto besser</td>
        <td>Anteil des Umsatzes, der nach den reinen Produktionskosten übrig bleibt.
            Eine hohe und stabile Bruttomarge zeigt, dass das Unternehmen Preissetzungsmacht
            hat (z. B. Luxusgüter, Software). Niedrige Margen &lt; 20 % deuten
            auf hartes Wettbewerbsumfeld hin (z. B. Handel, Rohstoffe).</td>
      </tr>
      <tr>
        <td><strong>Trailing P/E</strong><br><small>Kurs-Gewinn-Verhältnis</small></td>
        <td>Kontext abhängig</td>
        <td>Aktueller Kurs geteilt durch den Gewinn der letzten 12 Monate.
            Zeigt, wie viel Anleger bereit sind für €1 Gewinn zu zahlen.
            Ein P/E von 15 bedeutet: der Markt zahlt 15-fachen Jahresgewinn.
            Günstig oder teuer hängt stark vom Sektor ab — Tech-Aktien haben
            historisch höhere KGVs als Banken. Wichtig: mit dem Sektor-Durchschnitt
            und dem eigenen historischen KGV vergleichen.</td>
      </tr>
      <tr>
        <td><strong>Forward P/E</strong></td>
        <td>Niedriger als Trailing = Wachstum erwartet</td>
        <td>Wie Trailing P/E, aber basierend auf den Gewinnschätzungen der
            nächsten 12 Monate. Wenn Forward P/E deutlich unter Trailing P/E liegt,
            erwartet der Markt steigende Gewinne — ein gutes Zeichen.
            Liegt er höher, werden sinkende Gewinne erwartet.</td>
      </tr>
      <tr>
        <td><strong>Dividend Yield</strong><br><small>Dividendenrendite</small></td>
        <td>&gt; 2 % solide &nbsp;/&nbsp; &gt; 6 % prüfen</td>
        <td>Jährliche Dividende in % des aktuellen Kurses.
            Unternehmen, die auch in Krisen Dividende zahlen (oder erhöhen),
            zeigen damit finanzielle Stärke und Selbstvertrauen des Managements.
            Sehr hohe Renditen (&gt; 6–7 %) können aber eine Warnung sein,
            dass der Markt eine Kürzung erwartet.</td>
      </tr>
      <tr>
        <td><strong>Beta</strong></td>
        <td>&lt; 1 stabil &nbsp;/&nbsp; &gt; 1,5 volatil</td>
        <td>Misst, wie stark die Aktie im Vergleich zum Gesamtmarkt schwankt.
            Beta = 1,0 bedeutet: bewegt sich genau wie der Markt.
            Beta = 0,5 bedeutet: halb so volatil (z. B. Nestlé).
            Beta = 2,0 bedeutet: doppelt so volatil (z. B. manche Tech-Aktien).
            Bei Krisenrückgängen fallen hochvolatile Aktien oft überproportional —
            aber erholen sich auch schneller.</td>
      </tr>
      <tr>
        <td><strong>RSI (14d)</strong><br><small>Relative Strength Index</small></td>
        <td>&lt; 30 überverkauft &nbsp;/&nbsp; &gt; 70 überkauft</td>
        <td>Technischer Indikator (0–100), der zeigt ob eine Aktie kurzfristig
            zu stark gefallen (überverkauft) oder gestiegen (überkauft) ist.
            RSI unter 30 bedeutet: die Aktie wurde vermutlich emotional zu stark
            abverkauft — statistisch folgt häufig eine Gegenbewegung nach oben.
            Kein Garant, aber ein nützliches Zusatzsignal.</td>
      </tr>
      <tr>
        <td><strong>Analyst View</strong></td>
        <td>Buy / Strong Buy = positiv</td>
        <td>Konsensus-Empfehlung aller Analysten, die diese Aktie abdecken
            (aggregiert von Yahoo Finance). "Strong Buy" bedeutet, die Mehrheit
            der Profis erwartet Kurssteigerungen. Wichtig: Analysten liegen oft
            falsch und haben manchmal Interessenkonflikte — als ein Signal unter
            mehreren verwenden, nicht allein.</td>
      </tr>
      <tr>
        <td><strong>Sector ETF this week</strong></td>
        <td>Sektor auch gefallen = Makro-Krise</td>
        <td>Wochenperformance des zugehörigen Sektor-ETFs (z. B. XLK für Tech,
            XLF für Finanzwerte). Wenn der gesamte Sektor ähnlich stark gefallen
            ist, ist der Rückgang wahrscheinlich auf externe Faktoren zurückzuführen
            (Zinsen, Zölle, Rezessionsangst) — nicht auf ein Problem im Unternehmen.
            Das macht den Rückgang eher zu einer Kaufgelegenheit.
            Wenn nur diese Aktie gefallen ist, aber der Sektor stabil war →
            Unternehmens-spezifisches Problem → mehr Vorsicht geboten.</td>
      </tr>
      <tr>
        <td><strong>52w High</strong></td>
        <td>Je größer Abstand, desto günstiger relativ</td>
        <td>Höchster Kurs der letzten 52 Wochen. Der prozentuale Abstand vom
            Jahreshoch zeigt wie weit die Aktie bereits korrigiert hat.
            –30 % vom Hoch bei einem Qualitätsunternehmen kann eine attraktive
            Einstiegsgelegenheit sein — vorausgesetzt die Fundamentaldaten sind intakt.</td>
      </tr>
      <tr>
        <td><strong>52w Tief</strong></td>
        <td>&lt; 8% darüber = kritisch</td>
        <td>Niedrigster Kurs der letzten 52 Wochen. Wichtig für die Trendprognose:
            liegt der aktuelle Kurs nahe am Jahrestief (&lt; 8% darüber), testet
            er eine kritische Unterstützungszone — fällt er darunter, ist das ein
            starkes Warnsignal (kein Boden in Sicht). Je mehr Abstand nach oben,
            desto mehr Puffer hat die Aktie noch vor einem neuen Jahrestief.</td>
      </tr>
    </tbody>
  </table>

  <p class="footer">
    Preise &amp; Fundamentaldaten von Yahoo Finance via yfinance.<br>
    <strong>Dies ist keine Anlageberatung. Eigene Recherche ist unbedingt erforderlich.</strong>
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
