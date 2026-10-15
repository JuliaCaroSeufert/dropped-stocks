"""
Monatlicher "Emerging Trends"-Report.

Erkennt FRÜHE, noch nicht mainstream-bekannte Trends und verschickt die Top 3
als hochwertigen Newsletter per E-Mail. Auslöser: 1. des Monats (automatisch
über main.py) oder manuell via `python main.py --trends`.

Zwei Betriebsarten:
  1. PREMIUM (empfohlen): Eine Claude-Session recherchiert monatlich tief mit
     WebSearch + PubMed, schreibt die Trends als JSON und ruft
     `python trends.py --send <datei.json>` zum Versand auf.
  2. OFFLINE (self-contained): `python trends.py --research` sammelt Frühsignale
     aus Google Trends, arXiv, PubMed und Hacker News und lässt Groq/Gemini
     daraus die Top 3 destillieren. Läuft ohne Claude-Session, dafür mit der
     Qualität des jeweiligen Gratis-LLM.

Das JSON-Schema (für beide Wege identisch) steht in TRENDS_SCHEMA unten.
"""

import json
import logging
import os
import smtplib
import urllib.parse
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


# ── JSON-Schema (Dokumentation für die recherchierende Instanz) ────────────────

TRENDS_SCHEMA = """
{
  "edition": "November 2026",                 # Monat + Jahr des Reports
  "report_date": "2026-11-01",
  "methodology": "2-3 Sätze: Wie wurde recherchiert, welche Signale zählten?",
  "trends": [
    {
      "rank": 1,
      "name": "Prägnanter Trendname (max 6 Wörter)",
      "category": "AI | Gesundheit | B2B | Consumer | Familie | Wildcard",
      "core_thesis": "Ein Satz: Kern des Trends und warum er zählt.",
      "why_now": "Welche KONKRETEN Signale zeigen, dass JETZT der Moment ist? (3-4 Sätze)",
      "why_still_early": "Warum noch NICHT Mainstream? Was fehlt zum Durchbruch? (2 Sätze)",
      "market_potential": "Konkrete Marktgrößen-Schätzung + Begründung.",
      "timeframe": "2026-2029",
      "early_signals": ["Signal 1 (mit Zahl/Quelle)", "Signal 2", "Signal 3"],
      "investment_angles": [
        {"thesis": "Konkreter Ansatz", "examples": "Firmen/Startups/Technologien"}
      ],
      "novelty_score": 90,                     # 0-100, wie neuartig/pre-mainstream
      "growth_score": 85,                      # 0-100, Wachstumspotenzial
      "main_risk": "Größtes Risiko in 1 Satz.",
      "sources": [{"label": "Quelle", "url": "https://..."}]
    }
  ]
}
"""


# ── Kategorie-Design ──────────────────────────────────────────────────────────

_CATEGORY = {
    "ai":         ("AI & KI",            "#7c3aed", "#f3f0ff"),
    "gesundheit": ("Gesundheit",         "#0d9488", "#e6fffb"),
    "health":     ("Gesundheit",         "#0d9488", "#e6fffb"),
    "b2b":        ("B2B & Enterprise",   "#ea580c", "#fff4ec"),
    "consumer":   ("Consumer",           "#2563eb", "#eef4ff"),
    "familie":    ("Familie & Fertilität","#db2777", "#fff0f7"),
    "family":     ("Familie & Fertilität","#db2777", "#fff0f7"),
    "wildcard":   ("Wildcard",           "#d97706", "#fff8ec"),
}


def _cat(category: str | None) -> tuple[str, str, str]:
    key = (category or "").strip().lower()
    for k, v in _CATEGORY.items():
        if k in key:
            return v
    return ("Trend", "#475569", "#f1f5f9")


def _score_bar(label: str, value: int, color: str) -> str:
    value = max(0, min(100, int(value)))
    return (
        f'<div style="margin-bottom:6px">'
        f'<div style="font-size:10px;color:#888;text-transform:uppercase;'
        f'letter-spacing:.5px;margin-bottom:3px">{label}</div>'
        f'<div style="background:#e8e8ec;border-radius:6px;height:7px;width:100%;position:relative">'
        f'<div style="background:{color};width:{value}%;height:7px;border-radius:6px"></div>'
        f'</div>'
        f'<div style="font-size:13px;font-weight:700;color:{color};margin-top:2px">{value}<span '
        f'style="font-size:10px;color:#aaa;font-weight:400">/100</span></div>'
        f'</div>'
    )


# ── HTML-Report ────────────────────────────────────────────────────────────────

def _trend_card(t: dict) -> str:
    label, color, bg = _cat(t.get("category"))
    rank = t.get("rank", "")

    signals = "".join(
        f'<li style="margin:6px 0;padding-left:4px">{s}</li>'
        for s in t.get("early_signals", [])
    )
    signals_block = (
        f'<div style="margin-top:16px">'
        f'<div style="font-size:10px;font-weight:700;color:#999;text-transform:uppercase;'
        f'letter-spacing:.8px;margin-bottom:6px">Erste Signale</div>'
        f'<ul style="margin:0;padding-left:18px;font-size:13px;color:#333;line-height:1.5">'
        f'{signals}</ul></div>'
    ) if signals else ""

    angles = ""
    for a in t.get("investment_angles", []):
        ex = a.get("examples", "")
        ex_html = (
            f'<div style="font-size:12px;color:#777;margin-top:3px">'
            f'<span style="color:#aaa">Beispiele:</span> {ex}</div>'
        ) if ex else ""
        angles += (
            f'<div style="background:{bg};border-left:3px solid {color};border-radius:4px;'
            f'padding:10px 12px;margin:8px 0">'
            f'<div style="font-size:13px;font-weight:600;color:#1a1a2e">▸ {a.get("thesis","")}</div>'
            f'{ex_html}</div>'
        )
    angles_block = (
        f'<div style="margin-top:16px">'
        f'<div style="font-size:10px;font-weight:700;color:#999;text-transform:uppercase;'
        f'letter-spacing:.8px;margin-bottom:6px">Investitionsthesen</div>{angles}</div>'
    ) if angles else ""

    sources = t.get("sources", [])
    sources_block = ""
    if sources:
        links = " · ".join(
            f'<a href="{s.get("url","#")}" style="color:{color};text-decoration:none" '
            f'target="_blank">{s.get("label","Quelle")}</a>'
            for s in sources
        )
        sources_block = (
            f'<div style="margin-top:16px;padding-top:12px;border-top:1px solid #f0f0f0;'
            f'font-size:11px;color:#999">Quellen: {links}</div>'
        )

    risk = t.get("main_risk", "")
    risk_block = (
        f'<div style="margin-top:14px;background:#fafafa;border-radius:4px;padding:10px 12px">'
        f'<span style="font-size:10px;font-weight:700;color:#b71c1c;text-transform:uppercase;'
        f'letter-spacing:.5px">⚠ Hauptrisiko</span> '
        f'<span style="font-size:12.5px;color:#555">{risk}</span></div>'
    ) if risk else ""

    def _section(title: str, text: str) -> str:
        if not text:
            return ""
        return (
            f'<div style="margin-top:14px">'
            f'<div style="font-size:10px;font-weight:700;color:#999;text-transform:uppercase;'
            f'letter-spacing:.8px;margin-bottom:4px">{title}</div>'
            f'<div style="font-size:13.5px;color:#333;line-height:1.6">{text}</div></div>'
        )

    return (
        f'<div style="background:#fff;border-radius:10px;overflow:hidden;'
        f'box-shadow:0 2px 10px rgba(0,0,0,.08);margin-bottom:24px">'

        # Colored top strip: rank + category + scores
        f'<div style="background:{color};padding:14px 20px">'
        f'<table style="width:100%;border:none;border-collapse:collapse"><tr>'
        f'<td style="border:none;padding:0;vertical-align:middle">'
        f'<span style="display:inline-block;background:rgba(255,255,255,.22);color:#fff;'
        f'font-size:13px;font-weight:700;width:26px;height:26px;line-height:26px;'
        f'text-align:center;border-radius:50%;margin-right:10px">{rank}</span>'
        f'<span style="color:#fff;font-size:11px;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:1px">{label}</span>'
        f'</td>'
        f'<td style="border:none;padding:0;text-align:right;vertical-align:middle">'
        f'<span style="color:rgba(255,255,255,.85);font-size:11px">{t.get("timeframe","")}</span>'
        f'</td>'
        f'</tr></table>'
        f'</div>'

        # Body
        f'<div style="padding:20px">'
        f'<div style="font-size:21px;font-weight:700;color:#1a1a2e;line-height:1.25">'
        f'{t.get("name","")}</div>'
        f'<div style="font-size:14px;color:#555;font-style:italic;margin-top:8px;line-height:1.5">'
        f'{t.get("core_thesis","")}</div>'

        # Scores row
        f'<table style="width:100%;border:none;border-collapse:collapse;margin-top:16px"><tr>'
        f'<td style="border:none;padding:0 12px 0 0;width:50%;vertical-align:top">'
        f'{_score_bar("Neuartigkeit", t.get("novelty_score",0), "#7c3aed")}</td>'
        f'<td style="border:none;padding:0 0 0 12px;width:50%;vertical-align:top">'
        f'{_score_bar("Wachstumspotenzial", t.get("growth_score",0), "#0d9488")}</td>'
        f'</tr></table>'

        f'{_section("Warum jetzt?", t.get("why_now",""))}'
        f'{_section("Warum noch früh?", t.get("why_still_early",""))}'
        f'{_section("Marktpotenzial", t.get("market_potential",""))}'
        f'{signals_block}'
        f'{angles_block}'
        f'{risk_block}'
        f'{sources_block}'
        f'</div>'
        f'</div>'
    )


def build_trends_html(data: dict) -> str:
    edition = data.get("edition") or datetime.utcnow().strftime("%B %Y")
    methodology = data.get("methodology", "")
    trends = data.get("trends", [])

    cards = "".join(_trend_card(t) for t in trends)

    method_block = ""
    if methodology:
        method_block = (
            f'<div style="background:#fff;border-radius:10px;padding:16px 20px;'
            f'margin-bottom:24px;border-left:4px solid #7c3aed">'
            f'<div style="font-size:10px;font-weight:700;color:#7c3aed;text-transform:uppercase;'
            f'letter-spacing:.8px;margin-bottom:6px">Recherche-Methodik</div>'
            f'<div style="font-size:13px;color:#444;line-height:1.6">{methodology}</div>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
           color:#333;background:#eef0f3;margin:0;padding:0; }}
    a {{ text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
  </style>
</head>
<body>
  <div style="max-width:720px;margin:0 auto;background:#eef0f3">

    <!-- Header -->
    <div style="background:#0a0e27;padding:32px 28px 26px;
                background-image:linear-gradient(135deg,#0a0e27 0%,#1a1248 100%)">
      <div style="font-size:11px;font-weight:700;color:#8b7fd0;text-transform:uppercase;
                  letter-spacing:2px;margin-bottom:8px">Emerging Trends Report</div>
      <div style="font-size:30px;font-weight:800;color:#fff;letter-spacing:-.5px">
        🔮&nbsp; Was als Nächstes kommt
      </div>
      <div style="font-size:15px;color:#a99fd8;margin-top:10px">
        <strong style="color:#fff">{edition}</strong> &nbsp;·&nbsp;
        Die Top {len(trends)} pre-mainstream Trends &nbsp;·&nbsp;
        <span style="color:#8b7fd0">sortiert nach Neuartigkeit &amp; Potenzial</span>
      </div>
    </div>

    <!-- Content -->
    <div style="padding:24px 20px">
      {method_block}
      {cards}
    </div>

    <!-- Footer -->
    <div style="padding:18px 24px 28px;font-size:11px;color:#999;background:#f4f5f7;
                border-top:1px solid #dde0e6;text-align:center;line-height:1.7">
      Früherkennung aus wissenschaftlichen Preprints, Suchtrend-Daten, Fach-Communities
      und Startup-Aktivität.<br>
      <strong style="color:#888">Keine Anlageberatung. Trends sind spekulativ —
      eigene Recherche ist unbedingt erforderlich.</strong>
    </div>

  </div>
</body>
</html>"""


def build_trends_plain(data: dict) -> str:
    edition = data.get("edition") or datetime.utcnow().strftime("%B %Y")
    lines = [
        f"EMERGING TRENDS REPORT — {edition}",
        "=" * 60,
        data.get("methodology", ""),
        "",
    ]
    for t in data.get("trends", []):
        lines.append(f"#{t.get('rank','')} — {t.get('name','')}  [{t.get('category','')}]")
        lines.append(f"   Neuartigkeit: {t.get('novelty_score','?')}/100  |  "
                     f"Potenzial: {t.get('growth_score','?')}/100  |  "
                     f"Zeitfenster: {t.get('timeframe','?')}")
        lines.append(f"   These: {t.get('core_thesis','')}")
        lines.append(f"   Warum jetzt: {t.get('why_now','')}")
        lines.append(f"   Warum noch früh: {t.get('why_still_early','')}")
        lines.append(f"   Marktpotenzial: {t.get('market_potential','')}")
        if t.get("early_signals"):
            lines.append("   Erste Signale:")
            for s in t["early_signals"]:
                lines.append(f"     • {s}")
        if t.get("investment_angles"):
            lines.append("   Investitionsthesen:")
            for a in t["investment_angles"]:
                lines.append(f"     ▸ {a.get('thesis','')}  ({a.get('examples','')})")
        if t.get("main_risk"):
            lines.append(f"   Hauptrisiko: {t['main_risk']}")
        if t.get("sources"):
            srcs = ", ".join(f"{s.get('label','')}: {s.get('url','')}" for s in t["sources"])
            lines.append(f"   Quellen: {srcs}")
        lines.append("")
    lines.append("Keine Anlageberatung. Eigene Recherche erforderlich.")
    return "\n".join(lines)


# ── Versand ────────────────────────────────────────────────────────────────────

def _send_via_resend(
    api_key: str | None, sender: str, recipients: list[str],
    subject: str, html: str, text: str,
) -> None:
    """
    Sends via the Resend HTTP API (https://resend.com).

    If api_key is given (local use), it is sent as a Bearer token. If it is
    None, no Authorization header is set — this is the cloud case where the
    environment's network secret for api.resend.com is injected by the egress
    proxy, so the session never sees the key value.
    """
    payload = json.dumps({
        "from": sender,
        "to": recipients,
        "subject": subject,
        "html": html,
        "text": text,
    }).encode("utf-8")
    # A custom User-Agent is required: the default "Python-urllib/x" is blocked
    # by Resend's CDN (Cloudflare error 1010).
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "dropped-stocks-trends/1.0",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = json.loads(r.read().decode("utf-8"))
        logger.info("Trend-Report über Resend verschickt (id=%s) an %s",
                    body.get("id"), recipients)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")
        raise RuntimeError(f"Resend-API-Fehler {e.code}: {detail}") from e


def _send_via_smtp(
    smtp_host: str, smtp_port: int, smtp_user: str, smtp_password: str,
    sender: str, recipients: list[str], subject: str, html: str, text: str,
    use_tls: bool = True,
) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    if use_tls:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.ehlo()
        server.starttls()
    else:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port)
    try:
        server.login(smtp_user, smtp_password)
        server.sendmail(sender, recipients, msg.as_string())
        logger.info("Trend-Report über SMTP verschickt an %s", recipients)
    finally:
        server.quit()


def send_trends_report(
    data: dict,
    sender: str,
    recipients: list[str],
    resend_api_key: str | None = None,
    smtp_host: str | None = None,
    smtp_port: int = 587,
    smtp_user: str | None = None,
    smtp_password: str | None = None,
    use_tls: bool = True,
) -> None:
    """
    Verschickt den Trend-Report. Bevorzugt Resend (RESEND_API_KEY), fällt sonst
    auf SMTP zurück.
    """
    edition = data.get("edition") or datetime.utcnow().strftime("%B %Y")
    n = len(data.get("trends", []))
    top = data["trends"][0]["name"] if data.get("trends") else ""
    subject = f"🔮 Emerging Trends — {edition}: Top {n} (#1: {top})"
    html = build_trends_html(data)
    text = build_trends_plain(data)

    # SMTP only when explicit SMTP creds are set; otherwise Resend. In the cloud
    # the Resend key is injected by the proxy (network secret for api.resend.com),
    # so resend_api_key may be None here and that is fine.
    if smtp_user and smtp_password:
        _send_via_smtp(smtp_host or "smtp.gmail.com", smtp_port, smtp_user,
                       smtp_password, sender, recipients, subject, html, text, use_tls)
    else:
        _send_via_resend(resend_api_key, sender, recipients, subject, html, text)


# ── Offline-Recherche (self-contained Fallback) ────────────────────────────────

_SEED_TERMS = {
    "AI": ["ai agent", "small language model", "neuromorphic computing",
           "world model ai", "test time compute", "ai inference chip"],
    "Gesundheit": ["senolytics", "biological age clock", "glp-1 beyond diabetes",
                   "microbiome therapeutics", "continuous glucose monitor healthy",
                   "mitochondrial health"],
    "B2B": ["agentic workflow automation", "vertical ai saas",
            "compliance automation ai", "ai data center cooling"],
    "Consumer": ["circadian health", "functional mushroom", "sober curious",
                 "longevity biohacking"],
    "Familie": ["preconception genomics", "male fertility decline",
                "postpartum depression biomarker", "fetal monitoring wearable",
                "fertility preservation"],
}


def _fetch_google_trends() -> str:
    try:
        from pytrends.request import TrendReq
        import time as _t
        py = TrendReq(hl="en-US", tz=0, timeout=(10, 25), retries=1)
        out = []
        for cat, seeds in _SEED_TERMS.items():
            for seed in seeds[:3]:
                try:
                    py.build_payload([seed], timeframe="today 3-m", geo="")
                    rq = py.related_queries().get(seed, {})
                    rising = rq.get("rising")
                    if rising is not None and not rising.empty:
                        tops = []
                        for _, r in rising.head(4).iterrows():
                            tag = "BREAKOUT" if r["value"] == 0 else f"+{int(r['value'])}%"
                            tops.append(f"{r['query']} ({tag})")
                        out.append(f"[{cat}] '{seed}' → steigend: " + "; ".join(tops))
                    _t.sleep(1.2)
                except Exception as e:
                    logger.debug("pytrends '%s': %s", seed, e)
        return "\n".join(out) if out else "(keine Google-Trends-Daten)"
    except ModuleNotFoundError:
        return "(pytrends nicht installiert)"
    except Exception as e:
        logger.warning("Google Trends gesamt: %s", e)
        return "(Google Trends nicht verfügbar)"


def _fetch_arxiv(cats: list[str], days: int = 45, limit: int = 30) -> str:
    try:
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y%m%d")
        now = datetime.utcnow().strftime("%Y%m%d")
        q = "(" + "+OR+".join(f"cat:{c}" for c in cats) + ")"
        q += f"+AND+submittedDate:[{since}0000+TO+{now}2359]"
        params = urllib.parse.urlencode({
            "search_query": q, "max_results": limit,
            "sortBy": "submittedDate", "sortOrder": "descending",
        })
        url = f"https://export.arxiv.org/api/query?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "TrendsMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            root = ET.fromstring(r.read().decode("utf-8"))
        ns = {"a": "http://www.w3.org/2005/Atom"}
        titles = [e.find("a:title", ns).text.strip().replace("\n", " ")
                  for e in root.findall("a:entry", ns) if e.find("a:title", ns) is not None]
        return "\n".join(f"• {t[:130]}" for t in titles[:limit]) or "(keine Paper)"
    except Exception as e:
        logger.warning("arXiv: %s", e)
        return "(arXiv nicht verfügbar)"


def _fetch_pubmed(term: str, days: int = 60, limit: int = 15) -> str:
    try:
        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        q = urllib.parse.urlencode({
            "db": "pubmed", "term": f"{term} AND last {days} days[dp]",
            "retmax": limit, "retmode": "json", "sort": "date",
        })
        with urllib.request.urlopen(f"{base}/esearch.fcgi?{q}", timeout=20) as r:
            ids = json.loads(r.read())["esearchresult"].get("idlist", [])
        if not ids:
            return ""
        q2 = urllib.parse.urlencode({"db": "pubmed", "id": ",".join(ids), "retmode": "json"})
        with urllib.request.urlopen(f"{base}/esummary.fcgi?{q2}", timeout=20) as r:
            res = json.loads(r.read())["result"]
        titles = [res[i]["title"] for i in ids if i in res and "title" in res[i]]
        return f"[PubMed '{term}'] " + " | ".join(t[:90] for t in titles[:8])
    except Exception as e:
        logger.debug("PubMed '%s': %s", term, e)
        return ""


def _fetch_hackernews() -> str:
    try:
        cutoff = int((datetime.utcnow() - timedelta(days=21)).timestamp())
        url = ("https://hn.algolia.com/api/v1/search?tags=story"
               f"&numericFilters=points%3E150,created_at_i%3E{cutoff}&hitsPerPage=40")
        req = urllib.request.Request(url, headers={"User-Agent": "TrendsMonitor/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            hits = json.loads(r.read()).get("hits", [])
        rows = [f"• {h.get('title','')} ({h.get('points',0)} Punkte)" for h in hits[:30]]
        return "\n".join(rows) or "(keine HN-Daten)"
    except Exception as e:
        logger.warning("HN: %s", e)
        return "(HN nicht verfügbar)"


_OFFLINE_PROMPT = """\
Du bist Lead Analyst bei einem europäischen Venture-Capital-Fonds und sollst die
TOP 3 WIRKLICH FRÜHEN, noch nicht mainstream-bekannten Trends identifizieren.

MASSSTAB (so früh musst du sein):
- Longevity als Investmentthese: erkannt ~2019-2021, VOR dem Bryan-Johnson-Hype 2022/23
- AI Agents als Kategorie: erkannt Ende 2022, VOR dem Hype 2023/24
Du suchst Trends auf genau diesem Früherkennungs-Niveau.

SUCHRASTER: AI, Gesundheit/Longevity, B2B/Enterprise, Consumer-Verhalten,
Kinder/Schwangerschaft/Fertilität. Wildcards außerhalb erlaubt, wenn global/EU-weit groß.

STRENGE FILTER — ein Trend muss ALLE bestehen:
✓ Noch NICHT als "nächster großer Trend" in FAZ/Spiegel/Bloomberg/TechCrunch
✓ Konkrete frühe Signale (Paper-Cluster, Suchanstiege, Community-Aktivität)
✓ Realistisch >500 Mio EUR Marktpotenzial in 5 Jahren
✓ Spezifisch genug für konkrete Investitionsthesen
VERBOTEN (zu breit/bekannt): "KI im Gesundheitswesen", "Nachhaltigkeit", "E-Commerce wächst".

ROHSIGNALE (heute gesammelt):

=== GOOGLE TRENDS (Breakout = >5000%) ===
{trends}

=== ARXIV (neue Preprints) ===
{arxiv}

=== PUBMED (neue Medizin-Publikationen) ===
{pubmed}

=== HACKER NEWS (was Early Adopters diskutieren) ===
{hackernews}

Antworte AUSSCHLIESSLICH als valides JSON nach diesem Schema (keine Erklärung drumherum):
{schema}
Heutiges Datum: {today}. Fülle edition/report_date entsprechend.
"""


def _llm_json(prompt: str) -> dict | None:
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        try:
            from groq import Groq
            resp = Groq(api_key=groq_key).chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000, temperature=0.4,
            )
            return _parse_json(resp.choices[0].message.content)
        except Exception as e:
            logger.warning("Groq Trend-Analyse: %s", e)
    gem_key = os.getenv("GEMINI_API_KEY")
    if gem_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gem_key)
            model = genai.GenerativeModel("gemini-2.0-flash-lite")
            return _parse_json(model.generate_content(prompt).text)
        except Exception as e:
            logger.warning("Gemini Trend-Analyse: %s", e)
    logger.error("Kein LLM-Key (GROQ_API_KEY/GEMINI_API_KEY) für Offline-Recherche")
    return None


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return json.loads(text)


def research_trends_offline() -> dict | None:
    """Self-contained research via free signal sources + Groq/Gemini."""
    logger.info("Offline-Trendrecherche: sammle Signale …")
    trends = _fetch_google_trends()
    arxiv = (
        "[AI/ML/Robotics]\n" + _fetch_arxiv(["cs.AI", "cs.LG", "cs.RO"]) +
        "\n\n[Quant Bio/Econ]\n" + _fetch_arxiv(["q-bio.QM", "q-bio.MN", "econ.GN"])
    )
    pubmed = "\n".join(filter(None, [
        _fetch_pubmed("longevity senescence"),
        _fetch_pubmed("preconception fertility"),
        _fetch_pubmed("microbiome therapeutic"),
    ])) or "(keine PubMed-Daten)"
    hn = _fetch_hackernews()

    prompt = _OFFLINE_PROMPT.format(
        trends=trends[:6000], arxiv=arxiv[:5000],
        pubmed=pubmed[:3000], hackernews=hn[:3000],
        schema=TRENDS_SCHEMA, today=datetime.utcnow().strftime("%Y-%m-%d"),
    )
    logger.info("Offline-Trendrecherche: frage LLM …")
    return _llm_json(prompt)


# ── CLI ─────────────────────────────────────────────────────────────────────────

def _delivery_from_env() -> dict:
    """
    Liest die Versand-Konfiguration aus Umgebungsvariablen.
    Bevorzugt Resend (RESEND_API_KEY); SMTP ist der Fallback.
    """
    return {
        "resend_api_key": os.getenv("RESEND_API_KEY") or None,
        "sender": os.getenv("EMAIL_SENDER") or os.getenv("SMTP_USER", ""),
        "recipients": [r.strip() for r in os.getenv("EMAIL_RECIPIENTS", "").split(",") if r.strip()],
        "smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"),
        "smtp_port": int(os.getenv("SMTP_PORT", "587")),
        "smtp_user": os.getenv("SMTP_USER") or None,
        "smtp_password": os.getenv("SMTP_PASSWORD") or None,
        "use_tls": os.getenv("USE_TLS", "true").lower() != "false",
    }


# Rückwärtskompatibler Alias
_smtp_from_env = _delivery_from_env


def main() -> None:
    import argparse
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ModuleNotFoundError:
        # --send only needs the stdlib; env vars may come from the environment
        # directly (e.g. cloud secrets), so a missing python-dotenv is fine.
        pass
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s  %(levelname)-8s  %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

    p = argparse.ArgumentParser(description="Emerging-Trends-Report erstellen und versenden.")
    p.add_argument("--send", metavar="JSON", help="Vorbereitete Trends-JSON laden und per E-Mail verschicken.")
    p.add_argument("--research", action="store_true",
                   help="Offline-Recherche (Groq/Gemini) durchführen, JSON ausgeben und verschicken.")
    p.add_argument("--out", metavar="JSON", help="Recherche-Ergebnis zusätzlich in diese Datei schreiben.")
    p.add_argument("--no-email", action="store_true", help="Nur recherchieren/rendern, nicht verschicken.")
    args = p.parse_args()

    if args.send:
        with open(args.send, encoding="utf-8") as f:
            data = json.load(f)
    elif args.research:
        data = research_trends_offline()
        if not data:
            logger.error("Recherche lieferte kein Ergebnis.")
            raise SystemExit(1)
    else:
        p.error("Bitte --send <datei.json> oder --research angeben.")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Trends-JSON gespeichert: %s", args.out)

    if args.no_email:
        print(build_trends_html(data))
        return

    cfg = _delivery_from_env()
    if not cfg["recipients"]:
        logger.error("EMAIL_RECIPIENTS fehlt — kann nicht versenden.")
        raise SystemExit(1)
    if not cfg["sender"]:
        logger.error("EMAIL_SENDER fehlt (bei Resend die verifizierte Absenderadresse).")
        raise SystemExit(1)
    # Ohne SMTP-Creds läuft der Versand über Resend. Der Key kann aus der
    # Umgebung kommen (RESEND_API_KEY) oder — in der Cloud — vom Proxy als
    # Netzwerk-Secret für api.resend.com injiziert werden.
    send_trends_report(data, **cfg)


if __name__ == "__main__":
    main()
