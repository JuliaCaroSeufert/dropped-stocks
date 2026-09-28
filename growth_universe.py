"""
Zukunfts-Universum für den Newsticker
=====================================
Zwei Quellen, kombiniert:

1. **Kuratierte Kandidaten** (`_SEED`) — hochkarätige Firmen in den vier
   Zukunftsthemen. Robuste Basis, funktioniert sofort ohne Netzwerk-Discovery.

2. **Dynamische Sektor-Erkennung** (`_discover_from_watchlist`) — durchsucht
   die große Watchlist aus `config.py` und nimmt zusätzlich jede Firma auf,
   deren *Branche* (industry) auf ein Wachstumsthema passt. So bleibt das
   Universum nicht auf eine handgepflegte Liste beschränkt, sondern greift
   automatisch neue/aufstrebende Firmen in wachsenden Sektoren auf.

Jeder Eintrag ist {ticker: (firmenname, thema)}.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Die vier Zukunftsthemen (Anzeigenamen)
THEMES = {
    "AI":      "KI & Halbleiter",
    "CLOUD":   "Cloud, Software & Cybersecurity",
    "ROBOTICS":"Robotik, Automation & E-Mobilität",
    "FRONTIER":"Clean Energy, Biotech & Quantum",
}

# ── 1) Kuratierte Kandidaten ──────────────────────────────────────────────────
# Bewusst inklusive einiger etablierter Namen (Referenz/Rückenwind) und vieler
# aufstrebender Mid-Caps ("das nächste Nvidia"-Kandidaten). Der Score in
# newsticker.py entscheidet, was tatsächlich gemeldet wird.
_SEED: dict[str, tuple[str, str]] = {
    # ── KI & Halbleiter ──────────────────────────────────────────────────────
    "NVDA": ("NVIDIA",                       THEMES["AI"]),
    "AMD":  ("Advanced Micro Devices",       THEMES["AI"]),
    "AVGO": ("Broadcom",                      THEMES["AI"]),
    "TSM":  ("Taiwan Semiconductor",          THEMES["AI"]),
    "ASML": ("ASML Holding",                  THEMES["AI"]),
    "ARM":  ("Arm Holdings",                  THEMES["AI"]),
    "MRVL": ("Marvell Technology",            THEMES["AI"]),
    "MU":   ("Micron Technology",             THEMES["AI"]),
    "LRCX": ("Lam Research",                  THEMES["AI"]),
    "KLAC": ("KLA Corporation",               THEMES["AI"]),
    "AMAT": ("Applied Materials",             THEMES["AI"]),
    "SMCI": ("Super Micro Computer",          THEMES["AI"]),
    "CRDO": ("Credo Technology",              THEMES["AI"]),
    "ALAB": ("Astera Labs",                   THEMES["AI"]),
    "SOUN": ("SoundHound AI",                 THEMES["AI"]),
    "TEM":  ("Tempus AI",                     THEMES["AI"]),

    # ── Cloud, Software & Cybersecurity ───────────────────────────────────────
    "PLTR": ("Palantir Technologies",         THEMES["CLOUD"]),
    "SNOW": ("Snowflake",                      THEMES["CLOUD"]),
    "CRWD": ("CrowdStrike",                    THEMES["CLOUD"]),
    "ZS":   ("Zscaler",                        THEMES["CLOUD"]),
    "PANW": ("Palo Alto Networks",             THEMES["CLOUD"]),
    "NET":  ("Cloudflare",                     THEMES["CLOUD"]),
    "DDOG": ("Datadog",                        THEMES["CLOUD"]),
    "MDB":  ("MongoDB",                        THEMES["CLOUD"]),
    "S":    ("SentinelOne",                    THEMES["CLOUD"]),
    "FTNT": ("Fortinet",                       THEMES["CLOUD"]),
    "NOW":  ("ServiceNow",                     THEMES["CLOUD"]),
    "TEAM": ("Atlassian",                      THEMES["CLOUD"]),
    "HUBS": ("HubSpot",                        THEMES["CLOUD"]),
    "GTLB": ("GitLab",                         THEMES["CLOUD"]),
    "CFLT": ("Confluent",                      THEMES["CLOUD"]),
    "OKTA": ("Okta",                           THEMES["CLOUD"]),

    # ── Robotik, Automation & E-Mobilität ─────────────────────────────────────
    "TSLA": ("Tesla",                          THEMES["ROBOTICS"]),
    "ISRG": ("Intuitive Surgical",             THEMES["ROBOTICS"]),
    "ROK":  ("Rockwell Automation",            THEMES["ROBOTICS"]),
    "PATH": ("UiPath",                          THEMES["ROBOTICS"]),
    "SYM":  ("Symbotic",                        THEMES["ROBOTICS"]),
    "ABBNY":("ABB Ltd",                         THEMES["ROBOTICS"]),
    "FANUY":("Fanuc",                           THEMES["ROBOTICS"]),
    "TER":  ("Teradyne",                        THEMES["ROBOTICS"]),
    "ALB":  ("Albemarle",                       THEMES["ROBOTICS"]),
    "RIVN": ("Rivian Automotive",               THEMES["ROBOTICS"]),
    "ENVX": ("Enovix",                          THEMES["ROBOTICS"]),
    "QS":   ("QuantumScape",                    THEMES["ROBOTICS"]),
    "STEM": ("Stem Inc",                        THEMES["ROBOTICS"]),
    "NVTS": ("Navitas Semiconductor",           THEMES["ROBOTICS"]),

    # ── Clean Energy, Biotech & Quantum ───────────────────────────────────────
    "ENPH": ("Enphase Energy",                 THEMES["FRONTIER"]),
    "FSLR": ("First Solar",                     THEMES["FRONTIER"]),
    "PLUG": ("Plug Power",                      THEMES["FRONTIER"]),
    "BE":   ("Bloom Energy",                    THEMES["FRONTIER"]),
    "SEDG": ("SolarEdge Technologies",          THEMES["FRONTIER"]),
    "NEE":  ("NextEra Energy",                  THEMES["FRONTIER"]),
    "CEG":  ("Constellation Energy",            THEMES["FRONTIER"]),
    "VRT":  ("Vertiv Holdings",                 THEMES["FRONTIER"]),
    "IONQ": ("IonQ",                            THEMES["FRONTIER"]),
    "RGTI": ("Rigetti Computing",               THEMES["FRONTIER"]),
    "QBTS": ("D-Wave Quantum",                  THEMES["FRONTIER"]),
    "CRSP": ("CRISPR Therapeutics",             THEMES["FRONTIER"]),
    "NTLA": ("Intellia Therapeutics",           THEMES["FRONTIER"]),
    "BEAM": ("Beam Therapeutics",               THEMES["FRONTIER"]),
    "RXRX": ("Recursion Pharmaceuticals",       THEMES["FRONTIER"]),
    "MRNA": ("Moderna",                         THEMES["FRONTIER"]),
    "DNA":  ("Ginkgo Bioworks",                 THEMES["FRONTIER"]),
}


# ── 2) Dynamische Sektor-Erkennung ────────────────────────────────────────────
# Branchen-Stichworte (yfinance "industry"), die auf ein Zukunftsthema deuten.
_INDUSTRY_KEYWORDS: list[tuple[str, str]] = [
    # KI & Halbleiter
    ("semiconductor",              THEMES["AI"]),
    ("semiconductor equipment",    THEMES["AI"]),
    # Cloud, Software & Cybersecurity
    ("software—infrastructure",    THEMES["CLOUD"]),
    ("software - infrastructure",  THEMES["CLOUD"]),
    ("software—application",       THEMES["CLOUD"]),
    ("software - application",     THEMES["CLOUD"]),
    ("information technology serv",THEMES["CLOUD"]),
    # Robotik, Automation & E-Mobilität
    ("robot",                      THEMES["ROBOTICS"]),
    ("automation",                 THEMES["ROBOTICS"]),
    ("electrical equipment",       THEMES["ROBOTICS"]),
    ("auto manufacturers",         THEMES["ROBOTICS"]),
    ("auto parts",                 THEMES["ROBOTICS"]),
    # Clean Energy, Biotech & Quantum
    ("solar",                      THEMES["FRONTIER"]),
    ("renewable",                  THEMES["FRONTIER"]),
    ("biotechnology",              THEMES["FRONTIER"]),
    ("diagnostics & research",     THEMES["FRONTIER"]),
]


def _match_theme(industry: str | None) -> str | None:
    if not industry:
        return None
    low = industry.lower()
    for kw, theme in _INDUSTRY_KEYWORDS:
        if kw in low:
            return theme
    return None


def _discover_from_watchlist(limit: int = 400) -> dict[str, tuple[str, str]]:
    """
    Durchsucht die große Watchlist aus config.py und ergänzt Firmen, deren
    Branche auf ein Zukunftsthema passt. Kostet je einen yfinance-info-Aufruf,
    daher per `limit` gedeckelt. Fehler werden still übersprungen.
    """
    found: dict[str, tuple[str, str]] = {}
    try:
        import yfinance as yf
        from config import WATCHLIST
    except Exception as exc:
        logger.warning("Dynamische Erkennung nicht möglich: %s", exc)
        return found

    tickers = [t for t in WATCHLIST if t not in _SEED][:limit]
    logger.info("Dynamische Sektor-Erkennung: prüfe %d Watchlist-Ticker …", len(tickers))
    for ticker in tickers:
        try:
            industry = (yf.Ticker(ticker).info or {}).get("industry")
        except Exception:
            continue
        theme = _match_theme(industry)
        if theme:
            found[ticker] = (WATCHLIST[ticker], theme)
    logger.info("Dynamische Erkennung: %d zusätzliche Kandidaten gefunden.", len(found))
    return found


def build_growth_universe(discover: bool | None = None) -> dict[str, tuple[str, str]]:
    """
    Baut das komplette Zukunfts-Universum.

    `discover` steuert die dynamische Watchlist-Erkennung:
      • None  → per Umgebungsvariable NEWSTICKER_DISCOVER (Default: aus)
      • True  → immer einbeziehen
      • False → nur die kuratierte Liste
    """
    universe = dict(_SEED)

    if discover is None:
        discover = os.getenv("NEWSTICKER_DISCOVER", "false").lower() == "true"

    if discover:
        limit = int(os.getenv("NEWSTICKER_DISCOVER_LIMIT", "400"))
        universe.update(_discover_from_watchlist(limit=limit))

    return universe
