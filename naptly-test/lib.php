<?php
/**
 * Naptly – Hilfsfunktionen für das Speichern/Lesen der Anmeldungen.
 */

require_once __DIR__ . '/config.php';

/** Stellt sicher, dass die CSV-Datei inkl. Kopfzeile existiert. */
function naptly_ensure_store(): void
{
    $file = NAPTLY_DATA_FILE;
    $dir  = dirname($file);
    if (!is_dir($dir)) {
        @mkdir($dir, 0775, true);
    }
    if (!file_exists($file)) {
        $fh = fopen($file, 'w');
        if ($fh) {
            fputcsv($fh, ['zeitpunkt', 'email', 'name', 'quelle']);
            fclose($fh);
        }
    }
}

/** Einfache, robuste E-Mail-Validierung. */
function naptly_valid_email(string $email): bool
{
    $email = trim($email);
    return $email !== '' && strlen($email) <= 254
        && filter_var($email, FILTER_VALIDATE_EMAIL) !== false;
}

/**
 * Fügt eine Anmeldung hinzu.
 * Rückgabe: 'ok' | 'duplicate' | 'invalid' | 'error'
 */
function naptly_add_signup(string $email, string $name = '', string $source = 'web'): string
{
    $email = trim(mb_strtolower($email));
    $name  = trim($name);

    if (!naptly_valid_email($email)) {
        return 'invalid';
    }

    naptly_ensure_store();
    $file = NAPTLY_DATA_FILE;

    $fh = fopen($file, 'c+');
    if (!$fh) {
        return 'error';
    }

    // Exklusiver Lock: verhindert parallele Schreibkonflikte.
    if (!flock($fh, LOCK_EX)) {
        fclose($fh);
        return 'error';
    }

    // Auf doppelte Mail prüfen.
    rewind($fh);
    while (($row = fgetcsv($fh)) !== false) {
        if (isset($row[1]) && mb_strtolower(trim($row[1])) === $email) {
            flock($fh, LOCK_UN);
            fclose($fh);
            return 'duplicate';
        }
    }

    // Ans Ende springen und anhängen.
    fseek($fh, 0, SEEK_END);
    $written = fputcsv($fh, [date('c'), $email, $name, $source]);
    fflush($fh);
    flock($fh, LOCK_UN);
    fclose($fh);

    return $written === false ? 'error' : 'ok';
}

/** Liest alle Anmeldungen als Array von Zeilen (ohne Kopfzeile). */
function naptly_read_signups(): array
{
    $file = NAPTLY_DATA_FILE;
    if (!file_exists($file)) {
        return [];
    }
    $rows = [];
    $fh = fopen($file, 'r');
    if (!$fh) {
        return [];
    }
    $isHeader = true;
    while (($row = fgetcsv($fh)) !== false) {
        if ($isHeader) {
            $isHeader = false;
            continue;
        }
        if (count(array_filter($row, fn($c) => $c !== '' && $c !== null)) === 0) {
            continue; // leere Zeile überspringen
        }
        $rows[] = $row;
    }
    fclose($fh);
    return $rows;
}
