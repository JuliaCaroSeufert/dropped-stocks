# Monatliche Emerging-Trends-Routine

Dieser Report wird **nicht** vom Python-Scheduler in `main.py` erzeugt, sondern von
einer server-seitig gespeicherten **Claude-Code-Routine** (geplanter Trigger). Jeden
Monat startet eine frische Claude-Session, recherchiert mit WebSearch tief über alle
Themenfelder, bestimmt die Top 5 wirklich frühen Trends (darunter mind. 1 B2B-Trend
und 1 wirklich nischiger Trend) und verschickt die Mail über
`python trends.py --send <datei.json>`.

Jeder Lauf pusht sein Ergebnis zusätzlich als `reports/trends_<JAHR>-<MONAT>.json`
in den Branch — so ist jeder Report versioniert abrufbar, auch wenn der Mailversand
(noch) nicht konfiguriert ist.

Diese Datei dokumentiert die Routine, damit ihre Konfiguration versioniert und
reproduzierbar ist. Sie wird vom Programm **nicht** gelesen — sie ist reine Referenz.

## Eckdaten

| Feld            | Wert                                                        |
|-----------------|-------------------------------------------------------------|
| Name            | Monatlicher Emerging-Trends-Report                          |
| Trigger-ID      | `trig_01WdgjrMtYVr2DDeZf1ctnWs`                             |
| Zeitplan (cron) | `CRON_TZ=Europe/Berlin 38 7 1 * *` (1. des Monats, 07:38)   |
| Modus           | Frische Session pro Lauf (`create_new_session_on_fire`)     |
| Umgebung        | `env_015utT5BAXWwZAufy1q4Vhyo`                              |
| Benachrichtigung| Push + E-Mail nach jedem Lauf                               |

## Voraussetzung: SMTP-Secrets in der Umgebung

Die Routine läuft in der Cloud, nicht lokal — die `.env`-Datei reicht ihr daher nicht.
Für den Versand müssen diese Variablen als **Secrets der Cloud-Umgebung** hinterlegt
sein (Cloud-Umgebungsmenü im Session-Titelbalken → Edit):

- `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_RECIPIENTS` (zwingend)
- `SMTP_HOST`, `SMTP_PORT`, `EMAIL_SENDER`, `USE_TLS` (optional, haben Defaults)

Fehlen die Secrets, recherchiert die Routine trotzdem und gibt das Trend-JSON als Text
aus; nur der automatische Versand entfällt.

## Verwaltung

- **Manuell auslösen / pausieren / bearbeiten:** über die Routinen-Übersicht in der
  Claude-App, oder über die Claude-Code-Remote-Tools (`fire_trigger`, `update_trigger`,
  `delete_trigger`) mit obiger Trigger-ID.
- **Neu anlegen** (falls der Trigger verloren geht): eine Routine mit dem Zeitplan und
  dem Prompt unten erzeugen (`create_new_session_on_fire = true`).

## Prompt der Routine

> Du erstellst den monatlichen "Emerging Trends"-Report für den Nutzer
> (j.c.seufert@gmail.com). Ziel: die 3 WIRKLICH FRÜHEN, noch nicht mainstream-bekannten
> Trends finden, gründlich recherchieren und als E-Mail verschicken. Du startest ohne
> Vorwissen — folge dieser Anleitung vollständig.
>
> **1. REPO BEREITSTELLEN** — Das Skript `trends.py` rendert und verschickt den Report
> (JSON-Schema steht darin in `TRENDS_SCHEMA`). Repo: `JuliaCaroSeufert/dropped-stocks`.
> Falls `trends.py` nicht im Arbeitsverzeichnis liegt, Repo holen/klonen und hineinwechseln.
> Liegt `trends.py` nur auf dem Branch `claude/stock-drop-alerts-A2y47`, diesen auschecken
> (nach Merge in den Default-Branch reicht dieser).
>
> **2. RECHERCHE** (der Kern — gründlich, WebSearch im Modus "extended" + PubMed-Tools)
> über die Felder: AI (spezifische Nischen), Gesundheit/Longevity, B2B/Enterprise,
> Consumer-Verhalten, Kinder/Schwangerschaft/Fertilität. Wildcard außerhalb erlaubt, wenn
> global/EU-weit besonders groß.
> Maßstab "früh genug": so früh wie Longevity VOR Bryan Johnson (~2020) oder AI Agents VOR
> dem Hype (2022/23) — erste wissenschaftliche Signale, Startup-Frühphase, Nischen-
> Communities, aber noch keine große Medienwelle.
> Strenge Filter (jeder Trend muss ALLE bestehen): noch nicht als "nächster großer Trend"
> in FAZ/Spiegel/Bloomberg/TechCrunch; konkrete überprüfbare Frühsignale (Paper,
> Finanzierungsrunden, klinische/regulatorische Schritte, Patente); realistisch >500 Mio
> EUR Potenzial in 5 Jahren; spezifisch genug für Investitionsthesen. Verboten: zu breite/
> bekannte Themen. Jedes Signal an einer Primärquelle verifizieren. Jeden Monat möglichst
> NEUE Themen. GENAU 5 Trends wählen, sortiert nach Neuartigkeit × Wachstumspotenzial.
> PFLICHT: mind. 1 Trend B2B/Enterprise, mind. 1 Trend wirklich nischig (hochspezialisiert,
> sehr frühe Phase); die übrigen 3 möglichst über verschiedene Felder gestreut.
>
> **3. JSON SCHREIBEN** — Die 5 Trends als valides JSON exakt nach `TRENDS_SCHEMA` nach
> `/tmp/trends.json`. Textfelder auf Deutsch, echte Quell-URLs, realistische
> novelty_score/growth_score, edition/report_date = aktueller Monat.
>
> **4. VERSENDEN** — `python trends.py --send /tmp/trends.json` (braucht nur Standard-
> bibliothek + SMTP-Umgebungsvariablen). Schlägt der Versand mangels SMTP-Secrets fehl:
> JSON + Kurzzusammenfassung ausgeben und auf die fehlenden Secrets hinweisen.
> Am Ende kurz melden, welche 5 Trends gewählt wurden (inkl. B2B- und nischiger Pflicht-Slot)
> und ob die Mail verschickt wurde.
