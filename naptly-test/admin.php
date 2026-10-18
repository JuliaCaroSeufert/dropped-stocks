<?php
/**
 * Naptly – Admin-Ansicht
 * ------------------------------------------------------------------
 * Passwortgeschützte Übersicht aller Vorregistrierungen.
 * Login mit NAPTLY_ADMIN_PASSWORD (siehe config.php).
 *
 *   - Liste aller Anmeldungen (Zeitpunkt, E-Mail, Name)
 *   - Download als CSV: admin.php?download=csv
 *   - Logout: admin.php?logout=1
 */

session_start();
require_once __DIR__ . '/lib.php';

// --- Logout ---------------------------------------------------------
if (isset($_GET['logout'])) {
    $_SESSION = [];
    session_destroy();
    header('Location: admin.php');
    exit;
}

// --- Login ----------------------------------------------------------
$loginError = false;
if ($_SERVER['REQUEST_METHOD'] === 'POST' && isset($_POST['password'])) {
    if (hash_equals(NAPTLY_ADMIN_PASSWORD, (string) $_POST['password'])) {
        $_SESSION['naptly_admin'] = true;
        header('Location: admin.php');
        exit;
    }
    $loginError = true;
}

$isAuthed = !empty($_SESSION['naptly_admin']);

// --- CSV-Download (nur eingeloggt) ----------------------------------
if ($isAuthed && ($_GET['download'] ?? '') === 'csv') {
    $file = NAPTLY_DATA_FILE;
    header('Content-Type: text/csv; charset=utf-8');
    header('Content-Disposition: attachment; filename="naptly-anmeldungen-' . date('Y-m-d') . '.csv"');
    // UTF-8 BOM, damit Excel Umlaute korrekt anzeigt.
    echo "\xEF\xBB\xBF";
    if (file_exists($file)) {
        readfile($file);
    } else {
        echo "zeitpunkt,email,name,quelle\n";
    }
    exit;
}

// --- Login-Formular -------------------------------------------------
if (!$isAuthed):
?>
<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>naptly · Admin-Login</title>
<meta name="robots" content="noindex,nofollow">
<style>
  body{margin:0;font-family:system-ui,sans-serif;background:#fbf9f6;color:#37434f;display:grid;place-items:center;min-height:100vh}
  .box{background:#fff;padding:2.2rem;border-radius:20px;box-shadow:0 18px 50px -24px rgba(55,67,79,.35);width:min(380px,92%)}
  h1{font-size:1.3rem;margin:0 0 .3rem}
  p{color:#5b6775;margin:0 0 1.3rem;font-size:.92rem}
  label{font-size:.82rem;font-weight:600;color:#5b6775;display:block;margin-bottom:.35rem}
  input{width:100%;font:inherit;padding:.8rem 1rem;border-radius:12px;border:1.5px solid rgba(55,67,79,.16);background:#fcfbf9}
  input:focus{outline:0;border-color:#8d9c7e;box-shadow:0 0 0 3px rgba(141,156,126,.18)}
  button{margin-top:1rem;width:100%;border:0;cursor:pointer;font-weight:600;font-size:1rem;padding:.85rem;border-radius:999px;background:#71815f;color:#fff}
  button:hover{background:#63724f}
  .err{background:#fbe6e1;color:#b5503a;padding:.7rem 1rem;border-radius:12px;font-size:.9rem;font-weight:600;margin-bottom:1rem}
</style></head><body>
  <form class="box" method="post">
    <h1>naptly · Admin</h1>
    <p>Bitte mit dem Admin-Passwort anmelden.</p>
    <?php if ($loginError): ?><div class="err">Falsches Passwort.</div><?php endif; ?>
    <label for="pw">Passwort</label>
    <input type="password" id="pw" name="password" autofocus autocomplete="current-password">
    <button type="submit">Anmelden</button>
  </form>
</body></html>
<?php
exit;
endif;

// --- Eingeloggte Ansicht -------------------------------------------
$rows = naptly_read_signups();
$rows = array_reverse($rows); // neueste zuerst
$count = count($rows);
?>
<!DOCTYPE html>
<html lang="de"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>naptly · Anmeldungen (<?= $count ?>)</title>
<meta name="robots" content="noindex,nofollow">
<style>
  body{margin:0;font-family:system-ui,sans-serif;background:#fbf9f6;color:#37434f}
  .bar{background:#fff;border-bottom:1px solid rgba(55,67,79,.1);padding:1rem 1.5rem;display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap}
  .bar h1{font-size:1.15rem;margin:0}
  .bar .count{background:rgba(141,156,126,.16);color:#63724f;font-weight:700;padding:.2rem .7rem;border-radius:999px;font-size:.85rem;margin-left:.5rem}
  .actions{display:flex;gap:.6rem;flex-wrap:wrap}
  .btn{text-decoration:none;font-weight:600;font-size:.9rem;padding:.6rem 1.1rem;border-radius:999px;border:1.5px solid rgba(55,67,79,.18);color:#37434f}
  .btn:hover{background:rgba(55,67,79,.05)}
  .btn.primary{background:#71815f;color:#fff;border-color:#71815f}
  .btn.primary:hover{background:#63724f}
  .wrap{padding:1.5rem;max-width:1000px;margin-inline:auto}
  table{width:100%;border-collapse:collapse;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 10px 30px -18px rgba(55,67,79,.28)}
  th,td{text-align:left;padding:.85rem 1rem;font-size:.92rem;border-bottom:1px solid rgba(55,67,79,.07)}
  th{background:#f1ebe3;font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:#5b6775}
  tr:last-child td{border-bottom:0}
  td.mail{font-weight:600}
  .empty{text-align:center;color:#5b6775;padding:3rem 1rem;background:#fff;border-radius:16px}
  .muted{color:#8a95a1;font-size:.85rem}
</style></head><body>
  <div class="bar">
    <div><h1>Vorregistrierungen <span class="count"><?= $count ?></span></h1></div>
    <div class="actions">
      <a class="btn primary" href="admin.php?download=csv">CSV herunterladen</a>
      <a class="btn" href="index.php" target="_blank" rel="noopener">Seite ansehen</a>
      <a class="btn" href="admin.php?logout=1">Abmelden</a>
    </div>
  </div>
  <div class="wrap">
    <?php if ($count === 0): ?>
      <div class="empty">Noch keine Anmeldungen. Sobald sich jemand einträgt, erscheint es hier.</div>
    <?php else: ?>
      <table>
        <thead><tr><th>#</th><th>Zeitpunkt</th><th>E-Mail</th><th>Vorname</th></tr></thead>
        <tbody>
        <?php foreach ($rows as $i => $r):
            $ts = $r[0] ?? '';
            $email = $r[1] ?? '';
            $name = $r[2] ?? '';
            $tsNice = $ts ? date('d.m.Y H:i', strtotime($ts)) : '';
        ?>
          <tr>
            <td class="muted"><?= $count - $i ?></td>
            <td><?= htmlspecialchars($tsNice) ?></td>
            <td class="mail"><?= htmlspecialchars($email) ?></td>
            <td><?= htmlspecialchars($name) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    <?php endif; ?>
  </div>
</body></html>
