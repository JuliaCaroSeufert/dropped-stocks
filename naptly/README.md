# naptly – Vorregistrierungs-Seite

Schnelle Landingpage, auf der sich Interessent:innen für den Kauf des naptly-Babynests
vorregistrieren. Keine Datenbank nötig: Alle Anmeldungen landen in `data/signups.csv`
und sind über eine passwortgeschützte Admin-Seite einsehbar und als CSV herunterladbar.

## Dateien

| Datei | Zweck |
|-------|-------|
| `index.php` | Die öffentliche Landingpage mit Anmeldeformular |
| `signup.php` | Nimmt das Formular entgegen und speichert die Anmeldung |
| `admin.php` | Passwortgeschützte Übersicht + CSV-Download |
| `config.php` | **Passwort und Einstellungen – vor dem Upload anpassen** |
| `lib.php` | Interne Hilfsfunktionen |
| `impressum.php`, `datenschutz.php` | Rechtstexte (Platzhalter – bitte ausfüllen) |
| `data/` | Ablage der Anmeldungen (per `.htaccess` geschützt) |
| `assets/` | Logo + Produktbild |

## Vor dem Hochladen: 1 Sache ändern

Öffne **`config.php`** und setze ein eigenes Admin-Passwort:

```php
define('NAPTLY_ADMIN_PASSWORD', 'DEIN-SICHERES-PASSWORT');
```

Optional kannst du in `impressum.php` und `datenschutz.php` deine echten Angaben eintragen
(für den Livegang in Deutschland empfohlen/erforderlich).

## Hochladen zu IONOS

1. In IONOS einloggen → **Hosting** → dein Webhosting-Paket → **SFTP/FTP-Zugang** (Zugangsdaten anlegen/ansehen).
2. Mit einem FTP-Programm (z. B. [FileZilla](https://filezilla-project.org/)) verbinden.
3. Den **gesamten Inhalt** des Ordners `naptly/` in das Webroot-Verzeichnis deiner Domain
   hochladen (bei IONOS oft `/` bzw. der Ordner, der mit deiner Domain verknüpft ist).
   Wichtig: Die Dateien kommen direkt ins Webroot, **nicht** in einen Unterordner `naptly/`,
   damit die Seite unter `https://naptly.<deine-endung>/` erscheint.
4. Sicherstellen, dass der Ordner `data/` mit hochgeladen wurde und **beschreibbar** ist
   (Schreibrechte, meist `755`/`775` – IONOS setzt das i. d. R. automatisch korrekt).

### Läuft bei IONOS PHP?

Bei den klassischen **IONOS-Webhosting-Paketen ist PHP enthalten** – dann läuft alles
sofort. So prüfst du es im Zweifel: Lade eine Datei `test.php` mit dem Inhalt
`<?php phpinfo();` hoch und rufe sie im Browser auf. Erscheint eine PHP-Infoseite,
passt alles (Datei danach wieder löschen). Zeigt der Browser stattdessen den Quelltext,
ist auf dem Paket kein PHP aktiv – dann in den IONOS-Einstellungen eine PHP-Version
(z. B. 8.x) für die Domain aktivieren oder bei IONOS-Support nachfragen.

## Mails ansehen (während/nach der Testphase)

Rufe im Browser auf:

```
https://naptly.<deine-endung>/admin.php
```

Mit dem in `config.php` gesetzten Passwort einloggen. Dort siehst du alle Anmeldungen
und kannst sie oben rechts über **„CSV herunterladen“** als Datei (Excel-kompatibel)
exportieren.

## Lokal testen (optional)

Mit installiertem PHP:

```bash
cd naptly
php -S localhost:8000
# Seite:  http://localhost:8000/
# Admin:  http://localhost:8000/admin.php
```

## Datenschutz-Hinweis

Es werden E-Mail-Adressen erhoben. Das Formular enthält eine DSGVO-Einwilligungs-Checkbox,
und es liegen Platzhalter-Texte für Impressum und Datenschutz bei. Für den echten Livegang
bitte diese Texte mit deinen Angaben vervollständigen.
