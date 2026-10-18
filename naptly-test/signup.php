<?php
/**
 * Naptly – Formular-Endpunkt für die Vorregistrierung.
 *
 * Verarbeitet das Anmeldeformular. Funktioniert mit und ohne JavaScript:
 *   - Normale Formularübermittlung  -> Redirect zurück auf index.php?status=...
 *   - AJAX (fetch, Accept: json)    -> JSON-Antwort { ok, status }
 */

require_once __DIR__ . '/lib.php';

$wantsJson = (
    (isset($_SERVER['HTTP_X_REQUESTED_WITH']) && strtolower($_SERVER['HTTP_X_REQUESTED_WITH']) === 'xmlhttprequest')
    || (isset($_SERVER['HTTP_ACCEPT']) && str_contains($_SERVER['HTTP_ACCEPT'], 'application/json'))
);

function naptly_respond(string $status, bool $wantsJson): void
{
    $ok = $status === 'ok';
    if ($wantsJson) {
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => $ok, 'status' => $status]);
    } else {
        header('Location: index.php?status=' . urlencode($status) . '#anmelden');
    }
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    naptly_respond('invalid', $wantsJson);
}

// Honeypot: echtes Feld ist für Menschen unsichtbar. Ist es gefüllt -> Bot.
if (!empty($_POST['website'] ?? '')) {
    // Wir tun so, als wäre alles ok, speichern aber nichts.
    naptly_respond('ok', $wantsJson);
}

// Einverständnis (DSGVO) muss gesetzt sein.
if (empty($_POST['consent'] ?? '')) {
    naptly_respond('noconsent', $wantsJson);
}

$email = (string) ($_POST['email'] ?? '');
$name  = (string) ($_POST['name'] ?? '');

if (!naptly_valid_email($email)) {
    naptly_respond('invalid', $wantsJson);
}

// Name defensiv begrenzen.
$name = mb_substr(trim($name), 0, 80);

$result = naptly_add_signup($email, $name, 'web');
naptly_respond($result, $wantsJson);
