"""
Newsticker — "Das nächste Nvidia"
=================================
Wöchentlicher Scanner, der Aktien in langfristigen Wachstumssektoren aufspürt
und die überzeugendsten Kandidaten mit einer verständlichen Begründung per
E-Mail schickt: *was die Firma macht* und *warum die Aktie langfristig
interessant sein könnte*.

Idee
----
Nicht Tages-Kursbewegungen (das macht `checker.py`), sondern strukturelle
Qualität: Firmen in Sektoren mit mehrjährigem Rückenwind (KI/Halbleiter, Cloud &
Cybersecurity, Robotik/Automation/E-Mobilität, Clean Energy/Biotech/Quantum),
die schnell wachsen, gute Margen haben und noch nicht "das fertige Riesending"
sind.

Jede Aktie bekommt einen **Zukunfts-Score (0–100)** aus:
  • Umsatzwachstum            (bis 30 Punkte)
  • Bruttomarge / Skalierung  (bis 20 Punkte)
  • Sektor-/Themen-Rückenwind (bis 20 Punkte)
  • Kurs-Momentum             (bis 15 Punkte)
  • Marktkapitalisierungs-Fenster (bis  8 Punkte)   ← Mid-Cap bevorzugt
  • Analysten-Kursziel-Upside (bis 12 Punkte)

Es werden **so viele Kandidaten wie überzeugend** gemeldet (Score ≥
`NEWSTICKER_SCORE_THRESHOLD`), höchstens `NEWSTICKER_MAX_PICKS`.

Die Begründungen werden von einem kostenlosen LLM formuliert
(Groq → Gemini → Offline-Fallback), wie in `checker.py`.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field

import yfinance as yf

from growth_universe import THEMES, build_growth_universe

logger = logging.getLogger(__name__)

# ── Tuning-Parameter (per .env überschreibbar) ────────────────────────────────
NEWSTICKER_SCORE_THRESHOLD = int(os.getenv("NEWSTICKER_SCORE_THRESHOLD", "62"))
NEWSTICKER_MAX_PICKS       = int(os.getenv("NEWSTICKER_MAX_PICKS", "12"))
# Obergrenze Marktkapitalisierung: schon fertige Mega-Caps ("Nvidia von heute")
# werden ausgeschlossen. Default 250 Mrd. USD. 0 = keine Grenze.
NEWSTICKER_MAX_MARKETCAP   = float(os.getenv("NEWSTICKER_MAX_MARKETCAP", str(250e9)))


# ── Datentyp ──────────────────────────────────────────────────────────────────
@dataclass
class GrowthPick:
    ticker:   str
    company:  str
    theme:    str                       # Zukunftsthema (z.B. "KI & Halbleiter")
    currency: str = "USD"

    # Kennzahlen
    price:            float | None = None
    market_cap:       float | None = None
    revenue_growth:   float | None = None   # YoY, Anteil (0.35 = +35 %)
    earnings_growth:  float | None = None
    gross_margins:    float | None = None
    profit_margins:   float | None = None
    sector:           str   | None = None
    industry:         str   | None = None
    recommendation:   str   | None = None
    target_mean:      float | None = None
    num_analysts:     int   | None = None   # Analysten-Abdeckung (wenige = unentdeckt)
    perf_6m_pct:      float | None = None   # 6-Monats-Kursentwicklung in %
    above_200d:       bool  | None = None   # Kurs über 200-Tage-Linie?
    week_high_52:     float | None = None
    week_low_52:      float | None = None
    pct_below_high:   float | None = None   # % unter dem 52-Wochen-Hoch (Luft nach oben)

    # Bewertung
    score:        int  = 0
    score_parts:  dict = field(default_factory=dict)
    upside_pct:   float | None = None       # Kursziel vs. aktueller Kurs

    # Text (Deutsch)
    summary_en:  str | None = None          # Roh-Geschäftsbeschreibung (EN)
    was:         str | None = None          # Was macht die Firma?
    these:       str | None = None          # Wachstumsthese: wohin + was ist NICHT eingepreist
    katalysator: str | None = None          # Konkreter Auslöser der nächsten 1-3 Jahre
    risiken:     str | None = None          # Wichtigstes Risiko

    def __str__(self) -> str:
        rg = f"{self.revenue_growth*100:+.0f}%" if self.revenue_growth is not None else "?"
        return (
            f"{self.company} ({self.ticker}) [{self.theme}] "
            f"Score {self.score}/100  Umsatz {rg}"
        )


# ── Kennzahlen laden ────────────────────────────────────────────────────────
def _fetch_metrics(ticker: str) -> dict:
    """Holt Fundamentaldaten + kurze Kursreihe für ein Ticker via yfinance."""
    out: dict = {}
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
    except Exception as exc:
        logger.debug("info() für %s fehlgeschlagen: %s", ticker, exc)
        info = {}

    def g(key):
        v = info.get(key)
        return v if v not in (None, "N/A", "") else None

    out.update(
        company        = g("shortName") or g("longName"),
        currency       = g("currency") or "USD",
        price          = g("currentPrice") or g("regularMarketPrice"),
        market_cap     = g("marketCap"),
        revenue_growth = g("revenueGrowth"),
        earnings_growth= g("earningsGrowth"),
        gross_margins  = g("grossMargins"),
        profit_margins = g("profitMargins"),
        sector         = g("sector"),
        industry       = g("industry"),
        recommendation = g("recommendationKey"),
        target_mean    = g("targetMeanPrice"),
        num_analysts   = g("numberOfAnalystOpinions"),
        week_high_52   = g("fiftyTwoWeekHigh"),
        week_low_52    = g("fiftyTwoWeekLow"),
        summary_en     = g("longBusinessSummary"),
    )

    # 6-Monats-Momentum + 200-Tage-Linie
    try:
        hist = tk.history(period="8mo", interval="1d")["Close"].dropna()
        if len(hist) > 20:
            price_now = float(hist.iloc[-1])
            if out.get("price") is None:
                out["price"] = price_now
            # ~126 Handelstage ≈ 6 Monate
            idx = max(0, len(hist) - 126)
            price_6m = float(hist.iloc[idx])
            if price_6m > 0:
                out["perf_6m_pct"] = (price_now - price_6m) / price_6m * 100
            if len(hist) >= 200:
                ma200 = float(hist.tail(200).mean())
                out["above_200d"] = price_now > ma200
    except Exception as exc:
        logger.debug("history() für %s fehlgeschlagen: %s", ticker, exc)

    # Abstand zum 52-Wochen-Hoch (wie viel Luft nach oben ist noch nicht gelaufen?)
    hi, px = out.get("week_high_52"), out.get("price")
    if hi and px and hi > 0:
        out["pct_below_high"] = (hi - px) / hi * 100

    return out


# ── Scoring ───────────────────────────────────────────────────────────────────
def _score(pick: GrowthPick) -> tuple[int, dict]:
    """
    „Nvidia 2020"-Profil: nicht das schon gelaufene Riesenunternehmen, sondern
    das früh-stadige, noch unterentdeckte mit ungepreistem Potenzial.

    Belohnt wird deshalb bewusst: hohes Umsatzwachstum, Skalierbarkeit, KLEINE
    Größe, GERINGE Analystenabdeckung (unentdeckt) und noch Luft nach oben
    (nicht schon am Allzeithoch). Momentum-Chasing wird NICHT belohnt.
    """
    parts: dict[str, int] = {}

    # 1) Umsatzwachstum — der Wachstumsmotor (bis 30)
    rg = pick.revenue_growth
    if rg is not None:
        if   rg >= 0.50: parts["Umsatzwachstum"] = 30
        elif rg >= 0.30: parts["Umsatzwachstum"] = 25
        elif rg >= 0.20: parts["Umsatzwachstum"] = 19
        elif rg >= 0.10: parts["Umsatzwachstum"] = 11
        elif rg >  0:    parts["Umsatzwachstum"] = 4

    # 2) Bruttomarge / Skalierbarkeit (bis 15) — Software/IP skaliert billig
    gm = pick.gross_margins
    if gm is not None:
        if   gm >= 0.70: parts["Bruttomarge"] = 15
        elif gm >= 0.50: parts["Bruttomarge"] = 11
        elif gm >= 0.35: parts["Bruttomarge"] = 7
        elif gm >  0:    parts["Bruttomarge"] = 3

    # 3) Frühphase / „noch klein" (bis 22) — je kleiner, desto mehr Verzehn-
    #    fachungs-Potenzial. Riesenkonzerne (schon das fertige Nvidia) → 0.
    mc = pick.market_cap
    if mc is not None:
        if   3e8  <= mc < 2e9:   parts["Frühphase"] = 22   # 0,3–2 Mrd: echte Frühphase
        elif 2e9  <= mc < 1e10:  parts["Frühphase"] = 18   # 2–10 Mrd
        elif 1e10 <= mc < 5e10:  parts["Frühphase"] = 12   # 10–50 Mrd
        elif 5e10 <= mc < 1.5e11:parts["Frühphase"] = 6    # 50–150 Mrd
        elif 1.5e11<= mc < 2.5e11:parts["Frühphase"] = 2
        # ≥ 250 Mrd wird ohnehin herausgefiltert (siehe scan)

    # 4) Unentdeckt — geringe Analystenabdeckung (bis 12).
    #    Wenige/keine Analysten = noch nicht von der Wall Street durchgekaut.
    na = pick.num_analysts
    if na is None or na <= 6:  parts["Unentdeckt"] = 12
    elif na <= 12:             parts["Unentdeckt"] = 8
    elif na <= 20:             parts["Unentdeckt"] = 4

    # 5) Luft nach oben (bis 13) — GEGENTEIL von Momentum-Chasing.
    #    Am Allzeithoch ist viel eingepreist; eine gesunde Konsolidierung
    #    (deutlich unter Hoch, aber kein Totalabsturz) lässt Raum.
    pbh = pick.pct_below_high
    if pbh is not None:
        if   15 <= pbh <= 50: parts["Luft nach oben"] = 13  # Sweet Spot
        elif 50 <  pbh <= 70: parts["Luft nach oben"] = 8
        elif 5  <= pbh < 15:  parts["Luft nach oben"] = 6   # nahe Hoch = teils gepreist
        elif pbh > 70:        parts["Luft nach oben"] = 5   # tief gefallen = spekulativ
        else:                 parts["Luft nach oben"] = 3   # am Hoch

    # 6) Zukunftsthema (bis 8) — alle Kandidaten sind thematisch positioniert
    parts["Zukunftsthema"] = 8

    # Analysten-Kursziel nur als Zusatzinfo (fließt NICHT in den Score, damit
    # „schon entdeckte" Werte keinen Vorteil bekommen)
    if pick.target_mean and pick.price and pick.price > 0:
        pick.upside_pct = (pick.target_mean - pick.price) / pick.price * 100

    total = min(sum(parts.values()), 100)
    return total, parts


# ── LLM-Begründung ──────────────────────────────────────────────────────────
_PROMPT = (
    "Du bist ein Venture-/Growth-Analyst auf der Suche nach dem NÄCHSTEN Nvidia "
    "im Frühstadium — also einer Firma, BEVOR der große Anstieg eingepreist ist, "
    "nicht dem heutigen Riesenkonzern.\n\n"
    "Firma: {company} ({ticker}), Zukunftsthema: {theme}, Branche: {industry}.\n"
    "Kennzahlen: Umsatzwachstum {rg}, Bruttomarge {gm}, Marktkapitalisierung {mc} "
    "(noch klein!), {analysts} Analysten-Abdeckung, {below} unter 52-Wochen-Hoch.\n"
    "Geschäftsbeschreibung (Englisch):\n{summary}\n\n"
    "Wichtig: Erkläre NICHT nur, dass der Sektor wächst (das ist eingepreist), "
    "sondern WOHIN diese konkrete Firma wachsen könnte und WAS der Markt heute "
    "noch NICHT einpreist. Sei konkret zum adressierbaren Markt (TAM), zum "
    "Skalierungspfad und zum Auslöser.\n\n"
    "Antworte NUR als JSON auf Deutsch, kein Markdown, keine Anlageberatung:\n"
    '{{'
    '"was": "2 Sätze: was die Firma konkret macht und womit sie heute Geld verdient", '
    '"these": "3-4 Sätze: die Wachstumsthese. Wie groß ist der adressierbare Markt, '
    'wohin könnte Umsatz/Firma in 3-5 Jahren wachsen, und WELCHER Teil davon ist '
    'aktuell noch NICHT im Kurs eingepreist? Warum ist das ein Frühphasen-/'
    '\'Nvidia-2020\'-Profil (noch klein, unterschätzt)?", '
    '"katalysator": "1-2 Sätze: der konkrete Auslöser der nächsten 1-3 Jahre, der '
    'die These zünden könnte (z.B. neues Produkt, Design-Win, Zulassung, '
    'Kapazitätsausbau, Kipppunkt zur Profitabilität)", '
    '"risiken": "1 Satz zum wichtigsten Risiko dieser Frühphasen-Wette"'
    '}}'
)


def _fmt_mc(mc: float | None) -> str:
    if mc is None:
        return "unbekannt"
    if mc >= 1e12:
        return f"{mc/1e12:.1f} Bio. USD"
    if mc >= 1e9:
        return f"{mc/1e9:.1f} Mrd. USD"
    return f"{mc/1e6:.0f} Mio. USD"


def _llm_json(text: str) -> dict | None:
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    try:
        return json.loads(text.strip())
    except Exception:
        return None


def _call_groq(prompt: str, api_key: str) -> dict | None:
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
        )
        return _llm_json(resp.choices[0].message.content.strip())
    except ModuleNotFoundError:
        logger.warning("Paket 'groq' fehlt — 'pip install groq'")
    except Exception as exc:
        logger.warning("Groq fehlgeschlagen (%s): %s", type(exc).__name__, exc)
    return None


_gemini_model = None


def _call_gemini(prompt: str, api_key: str) -> dict | None:
    global _gemini_model
    try:
        import google.generativeai as genai
        if _gemini_model is None:
            genai.configure(api_key=api_key)
            _gemini_model = genai.GenerativeModel("gemini-2.0-flash-lite")
        return _llm_json(_gemini_model.generate_content(prompt).text.strip())
    except ModuleNotFoundError:
        logger.warning("Paket 'google-generativeai' fehlt")
    except Exception as exc:
        logger.warning("Gemini fehlgeschlagen (%s): %s", type(exc).__name__, exc)
    return None


def _offline_text(pick: GrowthPick) -> dict:
    """Fallback ohne LLM: übersetzt die Geschäftsbeschreibung, falls möglich."""
    was = pick.summary_en or ""
    if was:
        was = was.strip()
        # Auf ~2 Sätze kürzen
        parts = was.replace("\n", " ").split(". ")
        was = ". ".join(parts[:2]).strip()
        if was and not was.endswith("."):
            was += "."
        try:
            from deep_translator import GoogleTranslator
            was = GoogleTranslator(source="auto", target="de").translate(was[:1500])
        except Exception:
            pass
    rg = f"{pick.revenue_growth*100:+.0f}% Umsatzwachstum" if pick.revenue_growth else "hohes Wachstum"
    groesse = _fmt_mc(pick.market_cap)
    these = (
        f"Mit nur {groesse} Marktkapitalisierung ist die Firma im Zukunftsthema "
        f"„{pick.theme}“ noch klein und zeigt {rg}. Sollte sie ihren Nischenmarkt "
        f"weiter erobern, ist ein Vielfaches des heutigen Umsatzes denkbar — ein "
        f"Skalierungspfad, den der Markt bei so geringer Größe und Analystenabdeckung "
        f"oft noch nicht voll einpreist (Frühphasen-Profil)."
    )
    kat = (
        "Ein Katalysator wären beschleunigtes Umsatzwachstum, ein großer Kunden-/"
        "Design-Win oder der Kipppunkt zur Profitabilität."
    )
    return {
        "was": was or f"{pick.company} ist im Bereich {pick.industry or pick.theme} tätig.",
        "these": these,
        "katalysator": kat,
        "risiken": "Frühphasen-Wette: hohe Bewertung, mögliche Verwässerung und "
                   "Wettbewerbsdruck können zu starker Volatilität führen.",
    }


def _enrich(pick: GrowthPick) -> None:
    prompt = _PROMPT.format(
        company=pick.company, ticker=pick.ticker, theme=pick.theme,
        industry=pick.industry or "unbekannt",
        rg=f"{pick.revenue_growth*100:+.0f}%" if pick.revenue_growth is not None else "unbekannt",
        gm=f"{pick.gross_margins*100:.0f}%" if pick.gross_margins is not None else "unbekannt",
        mc=_fmt_mc(pick.market_cap),
        analysts=pick.num_analysts if pick.num_analysts is not None else "sehr wenige",
        below=f"{pick.pct_below_high:.0f}%" if pick.pct_below_high is not None else "unbekannt",
        summary=(pick.summary_en or "keine")[:2000],
    )

    data = None
    for env_var, fn in (("GROQ_API_KEY", _call_groq), ("GEMINI_API_KEY", _call_gemini)):
        key = os.getenv(env_var)
        if key:
            data = fn(prompt, key)
            if data:
                break

    if not data:
        data = _offline_text(pick)

    pick.was         = data.get("was")
    pick.these       = data.get("these") or data.get("warum")
    pick.katalysator = data.get("katalysator")
    pick.risiken     = data.get("risiken")


# ── Haupt-Scan ────────────────────────────────────────────────────────────────
def scan_growth_candidates(
    universe: dict[str, tuple[str, str]] | None = None,
    threshold: int = NEWSTICKER_SCORE_THRESHOLD,
    max_picks: int = NEWSTICKER_MAX_PICKS,
) -> list[GrowthPick]:
    """
    Bewertet das Wachstums-Universum und liefert die überzeugendsten Kandidaten
    (Score ≥ threshold), absteigend sortiert, höchstens `max_picks`.

    `universe` ist ein Dict {ticker: (company, theme)}; ohne Angabe wird das
    kuratierte Zukunfts-Universum aus `growth_universe.py` verwendet.
    """
    if universe is None:
        universe = build_growth_universe()

    total = len(universe)
    log_every = max(1, total // 10)
    logger.info("Newsticker: analysiere %d Zukunfts-Kandidaten …", total)

    picks: list[GrowthPick] = []
    for done, (ticker, (company, theme)) in enumerate(universe.items(), start=1):
        if done % log_every == 0 or done == total:
            logger.info("  %d/%d geprüft — %d Kandidaten bisher", done, total, len(picks))
        try:
            m = _fetch_metrics(ticker)
            if not m.get("price"):
                continue
            # Schon fertige Mega-Caps ausschließen — wir suchen „Nvidia 2020",
            # nicht „Nvidia heute".
            mc = m.get("market_cap")
            if NEWSTICKER_MAX_MARKETCAP and mc and mc > NEWSTICKER_MAX_MARKETCAP:
                continue
            pick = GrowthPick(
                ticker=ticker,
                company=m.get("company") or company,
                theme=theme,
                currency=m.get("currency") or "USD",
                price=m.get("price"),
                market_cap=m.get("market_cap"),
                revenue_growth=m.get("revenue_growth"),
                earnings_growth=m.get("earnings_growth"),
                gross_margins=m.get("gross_margins"),
                profit_margins=m.get("profit_margins"),
                sector=m.get("sector"),
                industry=m.get("industry"),
                recommendation=m.get("recommendation"),
                target_mean=m.get("target_mean"),
                num_analysts=m.get("num_analysts"),
                perf_6m_pct=m.get("perf_6m_pct"),
                above_200d=m.get("above_200d"),
                week_high_52=m.get("week_high_52"),
                week_low_52=m.get("week_low_52"),
                pct_below_high=m.get("pct_below_high"),
                summary_en=m.get("summary_en"),
            )
            pick.score, pick.score_parts = _score(pick)
            if pick.score >= threshold:
                picks.append(pick)
        except Exception as exc:
            logger.debug("Kandidat %s übersprungen: %s", ticker, exc)

    picks.sort(key=lambda p: p.score, reverse=True)
    picks = picks[:max_picks]

    logger.info("Newsticker: %d überzeugende Kandidat(en) (Score ≥ %d).", len(picks), threshold)

    # Nur für die finale Auswahl die (teureren) LLM-Begründungen erzeugen
    for pick in picks:
        _enrich(pick)
        logger.info("  → %s", pick)

    return picks
