<?php
/**
 * Naptly – Zentrale Konfiguration
 * ------------------------------------------------------------------
 * Vor dem Hochladen anpassen:
 *   1. ADMIN_PASSWORD auf ein eigenes, sicheres Passwort setzen.
 *   2. Optional: Absender-/Projektname anpassen.
 *
 * Dieses Setup braucht KEINE Datenbank. Alle Anmeldungen landen in
 * data/signups.csv und sind über admin.php einsehbar / als CSV
 * herunterladbar.
 */

// Mit diesem Passwort loggst du dich auf admin.php ein, um die
// gesammelten Mails zu sehen. (Für die Testphase bewusst einfach.)
define('NAPTLY_ADMIN_PASSWORD', 'naptly2025');

// Projektname (erscheint u. a. im Seitentitel)
define('NAPTLY_BRAND', 'naptly');

// Ablageort der Anmeldungen (relativ zu diesem Verzeichnis).
// Der Ordner data/ ist per .htaccess vor direktem Zugriff geschützt.
define('NAPTLY_DATA_FILE', __DIR__ . '/data/signups.csv');
