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
    num_analysts:     int   | None = None
    perf_6m_pct:      float | None = None   # 6-Monats-Kursentwicklung in %
    above_200d:       bool  | None = None   # Kurs über 200-Tage-Linie?

    # Bewertung
    score:        int  = 0
    score_parts:  dict = field(default_factory=dict)
    upside_pct:   float | None = None       # Kursziel vs. aktueller Kurs

    # Text (Deutsch)
    summary_en:  str | None = None          # Roh-Geschäftsbeschreibung (EN)
    was:         str | None = None          # Was macht die Firma?
    warum:       str | None = None          # Warum ist die Aktie interessant?
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

    return out


# ── Scoring ───────────────────────────────────────────────────────────────────
def _score(pick: GrowthPick) -> tuple[int, dict]:
    parts: dict[str, int] = {}

    # 1) Umsatzwachstum — das wichtigste Signal (bis 30)
    rg = pick.revenue_growth
    if rg is not None:
        if   rg >= 0.40: parts["Umsatzwachstum"] = 30
        elif rg >= 0.25: parts["Umsatzwachstum"] = 24
        elif rg >= 0.15: parts["Umsatzwachstum"] = 18
        elif rg >= 0.08: parts["Umsatzwachstum"] = 10
        elif rg >  0:    parts["Umsatzwachstum"] = 4

    # 2) Bruttomarge / Skalierbarkeit (bis 20)
    gm = pick.gross_margins
    if gm is not None:
        if   gm >= 0.60: parts["Bruttomarge"] = 20
        elif gm >= 0.40: parts["Bruttomarge"] = 14
        elif gm >= 0.25: parts["Bruttomarge"] = 8
        elif gm >  0:    parts["Bruttomarge"] = 3

    # 3) Sektor-/Themen-Rückenwind (bis 20) — Zugehörigkeit zu einem
    #    Zukunftsthema plus positives Gewinnwachstum als Bestätigung
    tail = 12
    eg = pick.earnings_growth
    if eg is not None and eg > 0.15:
        tail += 8
    elif eg is not None and eg > 0:
        tail += 4
    parts["Themen-Rückenwind"] = min(tail, 20)

    # 4) Kurs-Momentum (bis 15)
    mom = 0
    if pick.above_200d:
        mom += 7
    if pick.perf_6m_pct is not None:
        if   pick.perf_6m_pct >= 40: mom += 8
        elif pick.perf_6m_pct >= 15: mom += 6
        elif pick.perf_6m_pct >  0:  mom += 3
    if mom:
        parts["Momentum"] = min(mom, 15)

    # 5) Marktkapitalisierungs-Fenster (bis 8) — Mid/Large bevorzugt,
    #    Billionen-Konzerne ("schon das fertige Nvidia") leicht abgewertet
    mc = pick.market_cap
    if mc is not None:
        if   2e9  <= mc < 2e11:  parts["Größe"] = 8    # 2 Mrd – 200 Mrd = Sweet Spot
        elif 5e8  <= mc < 2e9:   parts["Größe"] = 6    # Small-Cap: Potenzial + Risiko
        elif 2e11 <= mc < 1e12:  parts["Größe"] = 4
        elif mc  >= 1e12:        parts["Größe"] = 2    # Mega-Cap
        # < 500 Mio: zu klein/illiquide → 0

    # 6) Analysten-Kursziel-Upside (bis 12)
    if pick.target_mean and pick.price and pick.price > 0:
        upside = (pick.target_mean - pick.price) / pick.price * 100
        pick.upside_pct = upside
        if   upside >= 30: parts["Kursziel-Upside"] = 12
        elif upside >= 15: parts["Kursziel-Upside"] = 8
        elif upside >= 5:  parts["Kursziel-Upside"] = 4

    total = min(sum(parts.values()), 100)
    return total, parts


# ── LLM-Begründung ──────────────────────────────────────────────────────────
_PROMPT = (
    "Du bist ein nüchterner Aktien-Analyst. Firma: {company} ({ticker}), "
    "Zukunftsthema: {theme}, Branche: {industry}.\n"
    "Kennzahlen: Umsatzwachstum {rg}, Bruttomarge {gm}, "
    "Marktkapitalisierung {mc}, 6-Monats-Kurs {perf}.\n"
    "Geschäftsbeschreibung (Englisch):\n{summary}\n\n"
    "Antworte NUR als JSON auf Deutsch, kein Markdown, keine Anlageberatung:\n"
    '{{"was": "2-3 Sätze: was die Firma konkret macht und womit sie Geld '
    'verdient", "warum": "2-4 Sätze: warum die Aktie in diesem Zukunftssektor '
    'langfristig interessant sein könnte — konkret auf Wachstumstreiber, '
    'Wettbewerbsvorteil und Sektortrend eingehen", "risiken": "1 Satz zum '
    'wichtigsten Risiko"}}'
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
    rg = f"{pick.revenue_growth*100:+.0f}% Umsatzwachstum" if pick.revenue_growth else "solides Wachstum"
    warum = (
        f"Das Unternehmen ist im Zukunftsthema „{pick.theme}“ positioniert und zeigt "
        f"{rg}. Sektoren wie dieser profitieren strukturell von mehrjährigen Trends "
        f"(Digitalisierung, Automatisierung, Elektrifizierung), was langfristiges "
        f"Nachfragewachstum stützen kann."
    )
    return {
        "was": was or f"{pick.company} ist im Bereich {pick.industry or pick.theme} tätig.",
        "warum": warum,
        "risiken": "Hohe Bewertung und Wettbewerbsdruck können zu starker Kursvolatilität führen.",
    }


def _enrich(pick: GrowthPick) -> None:
    prompt = _PROMPT.format(
        company=pick.company, ticker=pick.ticker, theme=pick.theme,
        industry=pick.industry or "unbekannt",
        rg=f"{pick.revenue_growth*100:+.0f}%" if pick.revenue_growth is not None else "unbekannt",
        gm=f"{pick.gross_margins*100:.0f}%" if pick.gross_margins is not None else "unbekannt",
        mc=_fmt_mc(pick.market_cap),
        perf=f"{pick.perf_6m_pct:+.0f}%" if pick.perf_6m_pct is not None else "unbekannt",
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

    pick.was     = data.get("was")
    pick.warum   = data.get("warum")
    pick.risiken = data.get("risiken")


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
