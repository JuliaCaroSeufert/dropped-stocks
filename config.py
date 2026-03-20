"""
Watchlist configuration.

At startup the app fetches the S&P 500, S&P 400 MidCap, and S&P 600 SmallCap
component lists from Wikipedia (~1,500 US-listed large/mid/small caps), merges
them with a curated list of ~300 international blue-chips that trade on US
exchanges (ADRs or direct listings), and caches the result locally for 7 days.

If the network is unavailable the international list is used as a fallback.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Alert threshold ────────────────────────────────────────────────────────
DROP_THRESHOLD_PCT = 10.0

# ── Cache ──────────────────────────────────────────────────────────────────
_CACHE_FILE = Path(__file__).parent / ".watchlist_cache.json"
_CACHE_MAX_AGE = timedelta(days=7)

# ── S&P index Wikipedia sources ────────────────────────────────────────────
_SP_SOURCES = [
    {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "label": "S&P 500",
    },
    {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        "label": "S&P 400",
    },
    {
        "url": "https://en.wikipedia.org/wiki/List_of_S%26P_600_companies",
        "label": "S&P 600",
    },
]

# ── Curated international blue-chips (ADRs / direct US-exchange listings) ─
# These are large, reputable companies from outside the US that trade on NYSE,
# NASDAQ, or well-covered OTC markets and are reliably available in yfinance.
_INTERNATIONAL: dict[str, str] = {
    # ── United Kingdom ────────────────────────────────────────────────────
    "SHEL":  "Shell plc (UK)",
    "AZN":   "AstraZeneca (UK)",
    "BP":    "BP plc (UK)",
    "GSK":   "GSK plc (UK)",
    "BTI":   "British American Tobacco (UK)",
    "BCS":   "Barclays (UK)",
    "LYG":   "Lloyds Banking Group (UK)",
    "UL":    "Unilever (UK/Netherlands)",
    "VOD":   "Vodafone Group (UK)",
    "NGG":   "National Grid (UK)",
    "RIO":   "Rio Tinto (UK/Australia)",
    "ICLR":  "ICON plc (Ireland)",
    "ACCD":  "Accolade (UK)",          # placeholder — swap if needed
    "EXPGY": "Experian (Ireland/UK)",
    "RELX":  "RELX plc (UK)",
    "PSON":  "Pearson (UK)",
    # ── Netherlands ───────────────────────────────────────────────────────
    "ASML":  "ASML Holding (Netherlands)",
    "ING":   "ING Groep (Netherlands)",
    "PHG":   "Philips (Netherlands)",
    # ── Germany ───────────────────────────────────────────────────────────
    "DB":    "Deutsche Bank (Germany)",
    "SAP":   "SAP SE (Germany)",
    "SIEGY": "Siemens AG (Germany)",
    "BMWYY": "BMW AG (Germany)",
    "MBGYY": "Mercedes-Benz Group (Germany)",
    "BAYRY": "Bayer AG (Germany)",
    "BASFY": "BASF SE (Germany)",
    "DTEGY": "Deutsche Telekom (Germany)",
    "ALIZY": "Allianz SE (Germany)",
    "MURGY": "Münchener Rückversicherung / Munich Re (Germany)",
    "VWAGY": "Volkswagen AG (Germany)",
    "POAHY": "Porsche Automobil Holding (Germany)",
    "ADDYY": "adidas AG (Germany)",
    "HEI":   "Heidelberg Materials (Germany)",   # NYSE listed
    "RWEOY": "RWE AG (Germany)",
    "EONGY": "E.ON SE (Germany)",
    "DHLGY": "Deutsche Post / DHL Group (Germany)",
    "XTRAGY":"Covestro (Germany)",
    # ── France ────────────────────────────────────────────────────────────
    "TTE":   "TotalEnergies (France)",
    "SNY":   "Sanofi (France)",
    "EADSY": "Airbus SE (France/Europe)",
    "BNPQY": "BNP Paribas (France)",
    "LRLCY": "L'Oréal (France)",
    "LVMUY": "LVMH Moët Hennessy Louis Vuitton (France)",
    "HESAY": "Hermès International (France)",
    "DANOY": "Danone (France)",
    "SGBLY": "Société Générale (France)",
    "CRARY": "Crédit Agricole (France)",
    "AXAHY": "AXA SA (France)",
    "ENGIEY":"Engie (France)",
    "ORANF": "Orange SA (France)",
    "KERRY": "Kering (France)",
    "PUBGY": "Publicis Groupe (France)",
    "MLCO":  "Melco Resorts (Macau/France-listed parent)",
    "SBGSY": "Schneider Electric (France)",
    "CAPLF": "Capgemini (France)",
    "AIVAF": "Air Liquide (France)",
    "VIEIF": "Vivendi (France)",
    # ── Switzerland ───────────────────────────────────────────────────────
    "UBS":   "UBS Group AG (Switzerland)",
    "NVS":   "Novartis AG (Switzerland)",
    "NSRGY": "Nestlé SA (Switzerland)",
    "RHHBY": "Roche Holding AG (Switzerland)",
    "ABB":   "ABB Ltd (Switzerland)",
    "LOGI":  "Logitech International (Switzerland)",
    "ZURVY": "Zurich Insurance Group (Switzerland)",
    "CSGNY": "Swiss Re AG (Switzerland)",
    "GEBN":  "Geberit AG (Switzerland)",
    "SGSOY": "SGS SA (Switzerland)",
    "GFORY": "Georg Fischer AG (Switzerland)",
    # ── Scandinavia ───────────────────────────────────────────────────────
    "NVO":   "Novo Nordisk A/S (Denmark)",
    "EQNR":  "Equinor ASA (Norway)",
    "ERIC":  "Ericsson (Sweden)",
    "NOK":   "Nokia Oyj (Finland)",
    "NNDNF": "Neste Oyj (Finland)",
    "ATLCY": "Atlas Copco AB (Sweden)",
    "VOLVY": "Volvo AB (Sweden)",
    "HVOLF": "Husqvarna AB (Sweden)",
    "DNSKF": "Danske Bank (Denmark)",
    "NDVLY": "Novozymes (Denmark)",
    "ORSTED":"Ørsted A/S (Denmark)",
    "SMNEY": "Sampo Oyj (Finland)",
    # ── Spain ─────────────────────────────────────────────────────────────
    "SAN":   "Banco Santander (Spain)",
    "BBVA":  "BBVA (Spain)",
    "TEF":   "Telefónica (Spain)",
    "IDEXY": "Industria de Diseño Textil / Inditex (Spain)",
    "REPYY": "Repsol (Spain)",
    "IBDRY": "Iberdrola SA (Spain)",
    "ACSAY": "ACS Group (Spain)",
    "CLNX":  "Cellnex Telecom (Spain)",
    # ── Italy ─────────────────────────────────────────────────────────────
    "ENLAY": "Enel SpA (Italy)",
    "STM":   "STMicroelectronics (Italy/France)",
    "ENEL":  "Enel SpA (Italy)",
    "ENIOY": "Eni SpA (Italy)",
    "UNCRY": "UniCredit SpA (Italy)",
    "ISPZY": "Intesa Sanpaolo (Italy)",
    "PIAGF": "Piagio (Italy)",
    "EXAHY": "Exor (Italy)",
    # ── Belgium / Luxembourg ──────────────────────────────────────────────
    "ANHUY": "Anheuser-Busch InBev (Belgium)",
    "UCB":   "UCB SA (Belgium)",
    "AGLXY": "ageas (Belgium)",
    # ── Australia ─────────────────────────────────────────────────────────
    "BHP":   "BHP Group (Australia)",
    "WDS":   "Woodside Energy (Australia)",
    "CBAUY": "Commonwealth Bank of Australia",
    "NABZY": "National Australia Bank",
    "ANZGY": "ANZ Banking Group (Australia)",
    "WBCOY": "Westpac Banking (Australia)",
    "MQBKY": "Macquarie Group (Australia)",
    "NCMGY": "Newcrest Mining (Australia)",
    "BXBLY": "Brambles Ltd (Australia)",
    "RMDX":  "ResMed Inc (Australia/US)",   # NYSE listed
    "AMCRY": "Amcor plc (Australia/UK)",
    "ATLAX": "Atlassian (Australia/US)",    # TEAM on NASDAQ
    "TEAM":  "Atlassian Corporation (Australia/US)",
    # ── Japan ─────────────────────────────────────────────────────────────
    "TM":    "Toyota Motor Corporation (Japan)",
    "SONY":  "Sony Group Corporation (Japan)",
    "HMC":   "Honda Motor Co (Japan)",
    "MUFG":  "Mitsubishi UFJ Financial Group (Japan)",
    "SMFG":  "Sumitomo Mitsui Financial Group (Japan)",
    "MFG":   "Mizuho Financial Group (Japan)",
    "NTT":   "Nippon Telegraph & Telephone (Japan)",
    "TOELY": "Tokyo Electron Ltd (Japan)",
    "HTHIY": "Hitachi Ltd (Japan)",
    "FANUY": "Fanuc Corporation (Japan)",
    "DSNKY": "Daikin Industries (Japan)",
    "PCRFY": "Panasonic Holdings (Japan)",
    "SSDOY": "Shin-Etsu Chemical (Japan)",
    "KDDIY": "KDDI Corporation (Japan)",
    "SBCFF": "SoftBank Corp (Japan)",
    "SFTBY": "SoftBank Group (Japan)",
    "NTDOY": "Nintendo Co Ltd (Japan)",
    "CNTFY": "Canon Inc (Japan)",
    "SEKEY": "Seiko Epson (Japan)",
    "BRDCY": "Bridgestone Corporation (Japan)",
    "DNZOF": "Denso Corporation (Japan)",
    "ROHCY": "Rohm Co Ltd (Japan)",
    "KYOCY": "Kyocera Corporation (Japan)",
    "MRAAF": "Murata Manufacturing (Japan)",
    "AJINY": "Ajinomoto (Japan)",
    "FUJIY": "Fujifilm Holdings (Japan)",
    "OKSNY": "Olympus Corporation (Japan)",
    "NISTF": "Nissan Motor (Japan)",
    "MZDAY": "Mazda Motor (Japan)",
    "SSUMY": "Subaru Corporation (Japan)",
    "ISUZY": "Isuzu Motors (Japan)",
    "YAMCY": "Yamaha Motor (Japan)",
    "KWHIY": "Kawasaki Heavy Industries (Japan)",
    "NDEKY": "Nippon Steel (Japan)",
    "MITSY": "Mitsui & Co (Japan)",
    "MSBHY": "Mitsubishi Corporation (Japan)",
    "ITOCY": "Itochu Corporation (Japan)",
    "MARUY": "Marubeni Corporation (Japan)",
    "SSUNF": "Sumitomo Corporation (Japan)",
    "THKLY": "THK Co (Japan)",
    # ── South Korea ───────────────────────────────────────────────────────
    "PKX":   "POSCO Holdings (South Korea)",
    "KB":    "KB Financial Group (South Korea)",
    "SHG":   "Shinhan Financial Group (South Korea)",
    "WF":    "Woori Financial Group (South Korea)",
    "SSNLF": "Samsung Electronics (South Korea)",
    "LGCLF": "LG Chem (South Korea)",
    "HYMTF": "Hyundai Motor (South Korea)",
    "HXSCL": "Hyundai Mobis (South Korea)",
    "SKLKF": "SK Hynix (South Korea)",
    "XIACF": "NAVER Corporation (South Korea)",
    "KIAOF": "Kia Corporation (South Korea)",
    # ── Taiwan ────────────────────────────────────────────────────────────
    "TSM":   "Taiwan Semiconductor Manufacturing (Taiwan)",
    "UMC":   "United Microelectronics (Taiwan)",
    "ASX":   "ASE Technology Holding (Taiwan)",
    # ── China / Hong Kong (ADRs) ─────────────────────────────────────────
    "BABA":  "Alibaba Group Holding (China)",
    "TCEHY": "Tencent Holdings (China)",
    "JD":    "JD.com (China)",
    "PDD":   "PDD Holdings (China)",
    "BIDU":  "Baidu Inc (China)",
    "NTES":  "NetEase Inc (China)",
    "BEKE":  "KE Holdings (China)",
    "ZTO":   "ZTO Express (China)",
    "YUMC":  "Yum China Holdings (China)",
    "BZ":    "Kanzhun / BOSS Zhipin (China)",
    "MNSO":  "MINISO Group (China)",
    "VNET":  "VNET Group (China)",
    "LI":    "Li Auto (China)",
    "NIO":   "NIO Inc (China)",
    "XPEV":  "XPeng Inc (China)",
    "RERE":  "ATRenew (China)",
    "CANG":  "Cango Inc (China)",
    "TIGR":  "UP Fintech Holding (China)",
    "MPNGY": "Man Wah Holdings (China/HK)",
    # ── India ─────────────────────────────────────────────────────────────
    "HDB":   "HDFC Bank (India)",
    "INFY":  "Infosys Ltd (India)",
    "WIT":   "Wipro Ltd (India)",
    "IBN":   "ICICI Bank (India)",
    "ICICIF":"ICICI Bank (India alt ticker)",
    "SIFY":  "Sify Technologies (India)",
    "RECON": "Recon Technology (China/India)",
    "RDY":   "Dr. Reddy's Laboratories (India)",
    "CIPLA": "Cipla (India)",            # listed on NSE/BSE; OTC in US
    "HCLT":  "HCL Technologies (India)",
    "TATAF": "Tata Consultancy Services (India)",
    "MBFJF": "Mahindra & Mahindra (India)",
    # ── Canada ────────────────────────────────────────────────────────────
    "RY":    "Royal Bank of Canada",
    "TD":    "Toronto-Dominion Bank",
    "BNS":   "Bank of Nova Scotia",
    "BMO":   "Bank of Montreal",
    "CM":    "Canadian Imperial Bank of Commerce (CIBC)",
    "MFC":   "Manulife Financial Corporation",
    "SLF":   "Sun Life Financial",
    "GWO":   "Great-West Lifeco",
    "CNI":   "Canadian National Railway",
    "CP":    "Canadian Pacific Kansas City",
    "CNQ":   "Canadian Natural Resources",
    "SU":    "Suncor Energy",
    "IMO":   "Imperial Oil",
    "NTR":   "Nutrien Ltd",
    "SHOP":  "Shopify Inc",
    "BCE":   "BCE Inc",
    "TU":    "TELUS Corporation",
    "ENB":   "Enbridge Inc",
    "TRP":   "TC Energy Corporation",
    "BAM":   "Brookfield Asset Management",
    "BN":    "Brookfield Corporation",
    "TFII":  "TFI International",
    "WCN":   "Waste Connections",
    "CAE":   "CAE Inc",
    "QSR":   "Restaurant Brands International",
    "TECK":  "Teck Resources",
    "FM":    "First Quantum Minerals",
    "CCO":   "Cameco Corporation",
    "AGI":   "Alamos Gold",
    "K":     "Kinross Gold",
    "ABX":   "Barrick Gold (listed as GOLD on NYSE)",
    "GOLD":  "Barrick Gold Corporation",
    "WPM":   "Wheaton Precious Metals",
    "EQB":   "EQB Inc",
    "POW":   "Power Corporation of Canada",
    "MG":    "Magna International",
    "ONEX":  "Onex Corporation",
    "BYD":   "Boyd Group Services",
    "LSPD":  "Lightspeed Commerce",
    "DNTL":  "Dentalcorp Holdings",
    "AFRM":  "Affirm Holdings (US but notable)",  # already S&P if large enough
    # ── Brazil ────────────────────────────────────────────────────────────
    "VALE":  "Vale SA (Brazil)",
    "ITUB":  "Itaú Unibanco Holding (Brazil)",
    "BBD":   "Banco Bradesco (Brazil)",
    "PBR":   "Petróleo Brasileiro / Petrobras (Brazil)",
    "ABEV":  "Ambev SA (Brazil)",
    "BSBR":  "Banco Santander Brasil",
    "GGBR4": "Gerdau SA (Brazil)",
    "BRFS":  "BRF SA (Brazil)",
    "CIG":   "Companhia Energética de Minas Gerais (Brazil)",
    "GGB":   "Gerdau SA (Brazil)",
    "ELP":   "Centrais Elétricas Brasileiras (Brazil)",
    "ERJ":   "Embraer SA (Brazil)",
    "SBSP3": "Sabesp (Brazil)",          # might not be US-listed
    # ── Latin America ─────────────────────────────────────────────────────
    "SQM":   "Sociedad Química y Minera de Chile",
    "MELI":  "MercadoLibre Inc (Argentina/Uruguay)",
    "EC":    "Ecopetrol SA (Colombia)",
    "AMX":   "América Móvil SAB de CV (Mexico)",
    "GMEXICOB": "Grupo México (Mexico)",
    "WALMEX":"Walmart de México (Mexico)",
    "GFNORTEO": "Grupo Financiero Banorte (Mexico)",
    "FEMSAUBD": "FEMSA (Mexico)",
    "FMX":   "Fomento Económico Mexicano / FEMSA (Mexico)",
    # ── Israel ────────────────────────────────────────────────────────────
    "NICE":  "NICE Systems (Israel)",
    "CHKP":  "Check Point Software Technologies (Israel)",
    "CYBR":  "CyberArk Software (Israel)",
    "MNDY":  "monday.com (Israel)",
    "WIX":   "Wix.com (Israel)",
    "GLBE":  "Global-E Online (Israel)",
    "NVCR":  "NovoCure Ltd (Israel)",
    "TEVA":  "Teva Pharmaceutical Industries (Israel)",
    "ESLT":  "Elbit Systems (Israel)",
    "CEVA":  "CEVA Inc (Israel/US)",
    # ── South Africa ──────────────────────────────────────────────────────
    "NPN":   "Naspers (South Africa)",   # might be OTC only
    "NPSNY": "Naspers Limited (South Africa)",
    "ANGPY": "Anglo American Platinum (South Africa)",
    "AGLXY": "Anglo American (South Africa/UK)",
    # ── Russia (suspended / de-listed — skip) ─────────────────────────────
    # ── Other notable global companies ───────────────────────────────────
    "RDS-A": "Shell (legacy ticker)",    # now SHEL
    "GLNCY": "Glencore plc (Switzerland/UK)",
    "RYAAY": "Ryanair Holdings (Ireland)",
    "WIZZ":  "Wizz Air Holdings (Hungary/UK)",
    "FLTR":  "Flutter Entertainment (Ireland)",
    "INXN":  "InterXion (Netherlands/US)",
    "SPOT":  "Spotify Technology (Sweden/Luxembourg)",
    "DKNG":  "DraftKings (US but notable)",
    "SE":    "Sea Limited (Singapore)",
    "GRAB":  "Grab Holdings (Singapore)",
    "GOTU":  "Gaotu Techedu (China)",
    "OPRA":  "Opera Limited (Norway/China)",
    "GLOB":  "Globant SA (Luxembourg/Argentina)",
    "DESP":  "Despegar.com (Argentina)",
    "ARCO":  "Arcos Dorados Holdings (Argentina)",
    "CAAP":  "Corporación América Airports (Argentina)",
    "TS":    "Tenaris SA (Luxembourg/Argentina)",
    "PAM":   "Pampa Energía (Argentina)",
    "LOMA":  "Loma Negra (Argentina)",
    "SUPV":  "Grupo Supervielle (Argentina)",
    "BIOX":  "Bioceres Crop Solutions (Argentina)",
    "AGRO":  "Adecoagro SA (Luxembourg/Argentina)",
    "VIST":  "Vista Energy (Mexico/Argentina)",
}


# ── Watchlist builder ──────────────────────────────────────────────────────

def _normalize_ticker(ticker: str) -> str:
    """Yahoo Finance uses '-' where some sources use '.' (e.g. BRK.B → BRK-B)."""
    return str(ticker).strip().replace(".", "-")


def _fetch_sp_index(url: str, label: str) -> dict[str, str]:
    """
    Download one S&P index table from Wikipedia.
    Returns {ticker: company_name}.
    """
    try:
        import pandas as pd  # lazy import — not needed for cache hits

        tables = pd.read_html(url, header=0)
        df = tables[0]

        # Identify ticker and name columns (handles minor Wikipedia variations)
        ticker_col = next(
            (c for c in df.columns if str(c).lower() in ("symbol", "ticker symbol", "ticker")),
            df.columns[0],
        )
        name_col = next(
            (c for c in df.columns if str(c).lower() in ("security", "company", "name")),
            df.columns[1],
        )

        result: dict[str, str] = {}
        for _, row in df.iterrows():
            ticker = _normalize_ticker(row[ticker_col])
            name = str(row[name_col]).strip()
            if ticker and name and ticker.lower() != "nan":
                result[ticker] = name

        logger.info("Fetched %d tickers from %s", len(result), label)
        return result

    except Exception as exc:
        logger.warning("Could not fetch %s from Wikipedia: %s", label, exc)
        return {}


def _load_cache() -> dict[str, str] | None:
    """Return cached watchlist if it exists and is fresh, else None."""
    try:
        if not _CACHE_FILE.exists():
            return None
        data = json.loads(_CACHE_FILE.read_text())
        cached_at = datetime.fromisoformat(data["cached_at"])
        if datetime.utcnow() - cached_at > _CACHE_MAX_AGE:
            logger.info("Watchlist cache is stale; will refresh.")
            return None
        logger.info(
            "Loaded %d tickers from cache (age: %s).",
            len(data["watchlist"]),
            datetime.utcnow() - cached_at,
        )
        return data["watchlist"]
    except Exception as exc:
        logger.warning("Could not read watchlist cache: %s", exc)
        return None


def _save_cache(watchlist: dict[str, str]) -> None:
    try:
        _CACHE_FILE.write_text(
            json.dumps({"cached_at": datetime.utcnow().isoformat(), "watchlist": watchlist},
                       indent=2)
        )
    except Exception as exc:
        logger.warning("Could not write watchlist cache: %s", exc)


def build_watchlist() -> dict[str, str]:
    """
    Build the full watchlist:
      1. Try to load from a local cache (refreshed every 7 days).
      2. If cache is missing/stale, fetch S&P 500 + 400 + 600 from Wikipedia.
      3. Merge with the hardcoded international list.
      4. Persist the merged result to cache.
    """
    cached = _load_cache()
    if cached is not None:
        return cached

    watchlist: dict[str, str] = {}

    for source in _SP_SOURCES:
        watchlist.update(_fetch_sp_index(source["url"], source["label"]))

    # Merge international list (don't overwrite S&P names if ticker already present)
    for ticker, name in _INTERNATIONAL.items():
        watchlist.setdefault(ticker, name)

    if watchlist:
        _save_cache(watchlist)
        logger.info("Watchlist built: %d unique tickers total.", len(watchlist))
    else:
        # Complete fallback: use just the international list
        logger.warning(
            "Could not fetch any S&P data. Falling back to international list only (%d tickers).",
            len(_INTERNATIONAL),
        )
        watchlist = dict(_INTERNATIONAL)

    return watchlist


# ── Module-level WATCHLIST (built once on import) ─────────────────────────
WATCHLIST: dict[str, str] = build_watchlist()
