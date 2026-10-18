<?php require_once __DIR__ . '/config.php'; ?>
<?php
$status = $_GET['status'] ?? '';
$messages = [
    'ok'        => ['type' => 'success', 'text' => 'Geschafft! Du stehst jetzt auf der Vorregistrierungs-Liste. Wir melden uns, sobald es losgeht.'],
    'duplicate' => ['type' => 'info',    'text' => 'Diese E-Mail ist bereits registriert – du bist also schon dabei. 💚'],
    'invalid'   => ['type' => 'error',   'text' => 'Bitte gib eine gültige E-Mail-Adresse ein.'],
    'noconsent' => ['type' => 'error',   'text' => 'Bitte bestätige kurz die Einwilligung, damit wir dir schreiben dürfen.'],
    'error'     => ['type' => 'error',   'text' => 'Da ist etwas schiefgelaufen. Bitte versuch es gleich noch einmal.'],
];
$banner = $messages[$status] ?? null;
?>
<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title><?= htmlspecialchars(NAPTLY_BRAND) ?> – Das tragbare Babynest. Jetzt vorregistrieren.</title>
<meta name="description" content="naptly – ein tragbares, atmungsaktives Babynest für geborgenen Schlaf, überall. Registriere dich jetzt vor und sichere dir den Early-Bird-Zugang.">
<meta name="robots" content="index,follow">
<meta property="og:title" content="naptly – das tragbare Babynest">
<meta property="og:description" content="Geborgener Schlaf, überall. Jetzt kostenlos vorregistrieren.">
<meta property="og:type" content="website">
<meta property="og:image" content="assets/nest.webp">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Quicksand:wght@400;500;600;700&family=Nunito:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#37434f;
    --ink-soft:#5b6775;
    --sage:#8d9c7e;
    --sage-deep:#71815f;
    --sand:#e8ded3;
    --sand-soft:#f1ebe3;
    --blush:#d9c8bc;
    --lav:#c9c6de;
    --bg:#fbf9f6;
    --white:#ffffff;
    --radius:22px;
    --shadow:0 18px 50px -24px rgba(55,67,79,.35);
    --shadow-soft:0 10px 30px -18px rgba(55,67,79,.28);
  }
  *{box-sizing:border-box}
  html{scroll-behavior:smooth}
  body{
    margin:0;font-family:'Nunito',system-ui,sans-serif;color:var(--ink);
    background:var(--bg);line-height:1.6;-webkit-font-smoothing:antialiased;
  }
  h1,h2,h3,.brandmark{font-family:'Quicksand',sans-serif;letter-spacing:.2px}
  a{color:inherit}
  img{max-width:100%;display:block}
  .wrap{width:min(1120px,92%);margin-inline:auto}
  .btn{
    display:inline-flex;align-items:center;justify-content:center;gap:.5rem;
    border:0;cursor:pointer;font-family:'Quicksand',sans-serif;font-weight:600;
    font-size:1.02rem;padding:.95rem 1.6rem;border-radius:999px;
    background:var(--sage-deep);color:#fff;transition:transform .15s ease,box-shadow .2s ease,background .2s ease;
    box-shadow:var(--shadow-soft);text-decoration:none;
  }
  .btn:hover{background:#63724f;transform:translateY(-1px)}
  .btn:active{transform:translateY(0)}
  .btn--ghost{background:transparent;color:var(--ink);box-shadow:none;border:1.5px solid rgba(55,67,79,.18)}
  .btn--ghost:hover{background:rgba(55,67,79,.05);transform:none}

  /* Header */
  header.site{padding:1.4rem 0}
  .nav{display:flex;align-items:center;justify-content:space-between;gap:1rem}
  .logo{height:54px;width:auto}
  .nav .btn{padding:.65rem 1.2rem;font-size:.95rem}

  /* Hero */
  .hero{padding:1rem 0 3.5rem}
  .hero-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:3rem;align-items:center}
  .eyebrow{
    display:inline-flex;align-items:center;gap:.5rem;font-family:'Quicksand',sans-serif;
    font-weight:600;font-size:.82rem;letter-spacing:.14em;text-transform:uppercase;
    color:var(--sage-deep);background:rgba(141,156,126,.14);padding:.4rem .85rem;border-radius:999px;
  }
  .hero h1{font-size:clamp(2.1rem,4.6vw,3.4rem);line-height:1.08;margin:1.1rem 0 1rem;font-weight:700}
  .hero h1 .soft{color:var(--sage-deep)}
  .hero p.lead{font-size:1.15rem;color:var(--ink-soft);max-width:34ch;margin:0 0 1.6rem}
  .hero-media{position:relative}
  .hero-media .photo{border-radius:var(--radius);box-shadow:var(--shadow);background:var(--white)}
  .concept-note{
    position:absolute;left:14px;bottom:14px;background:rgba(255,255,255,.82);
    backdrop-filter:blur(4px);color:var(--ink-soft);font-size:.68rem;letter-spacing:.14em;
    text-transform:uppercase;padding:.35rem .7rem;border-radius:999px;font-weight:600;
  }

  /* Signup card */
  .signup{
    margin-top:1.3rem;background:var(--white);border-radius:var(--radius);
    padding:1.5rem;box-shadow:var(--shadow-soft);border:1px solid rgba(55,67,79,.06);
  }
  .signup h3{margin:0 0 .25rem;font-size:1.15rem}
  .signup .hint{margin:0 0 1rem;color:var(--ink-soft);font-size:.92rem}
  .field{display:flex;flex-direction:column;gap:.35rem;margin-bottom:.85rem}
  .field label{font-size:.82rem;font-weight:600;color:var(--ink-soft)}
  .field input[type=email],.field input[type=text]{
    font:inherit;padding:.85rem 1rem;border-radius:14px;border:1.5px solid rgba(55,67,79,.16);
    background:#fcfbf9;transition:border .15s ease,box-shadow .15s ease;
  }
  .field input:focus{outline:0;border-color:var(--sage);box-shadow:0 0 0 3px rgba(141,156,126,.18)}
  .consent{display:flex;align-items:flex-start;gap:.6rem;font-size:.86rem;color:var(--ink-soft);margin:.3rem 0 1rem}
  .consent input{margin-top:.25rem;width:1.05rem;height:1.05rem;accent-color:var(--sage-deep)}
  .signup .btn{width:100%}
  .hp{position:absolute;left:-9999px;width:1px;height:1px;overflow:hidden}

  .banner{padding:.85rem 1.1rem;border-radius:14px;margin-bottom:1rem;font-size:.92rem;font-weight:600}
  .banner.success{background:rgba(141,156,126,.16);color:var(--sage-deep)}
  .banner.info{background:rgba(201,198,222,.3);color:#5a5878}
  .banner.error{background:#fbe6e1;color:#b5503a}

  /* Trust row */
  .trust{display:flex;flex-wrap:wrap;gap:1.4rem 2rem;margin-top:1.4rem;color:var(--ink-soft);font-size:.92rem}
  .trust span{display:inline-flex;align-items:center;gap:.5rem;font-weight:600}
  .trust .dot{width:8px;height:8px;border-radius:50%;background:var(--sage)}

  /* Sections */
  section.block{padding:4rem 0}
  .section-head{text-align:center;max-width:46ch;margin:0 auto 2.6rem}
  .section-head h2{font-size:clamp(1.6rem,3vw,2.3rem);margin:0 0 .6rem}
  .section-head p{color:var(--ink-soft);margin:0;font-size:1.05rem}

  .features{display:grid;grid-template-columns:repeat(3,1fr);gap:1.4rem}
  .feature{background:var(--white);border-radius:var(--radius);padding:1.8rem 1.6rem;box-shadow:var(--shadow-soft);border:1px solid rgba(55,67,79,.05)}
  .feature .ic{width:48px;height:48px;border-radius:14px;display:grid;place-items:center;background:rgba(141,156,126,.16);margin-bottom:1rem}
  .feature .ic svg{width:26px;height:26px;stroke:var(--sage-deep)}
  .feature h3{margin:0 0 .4rem;font-size:1.15rem}
  .feature p{margin:0;color:var(--ink-soft);font-size:.96rem}

  /* How / why */
  .band{background:linear-gradient(180deg,var(--sand-soft),#f6f1ea)}
  .steps{display:grid;grid-template-columns:repeat(3,1fr);gap:1.4rem;counter-reset:s}
  .step{position:relative;padding:1.6rem;background:var(--white);border-radius:var(--radius);box-shadow:var(--shadow-soft)}
  .step::before{counter-increment:s;content:counter(s);font-family:'Quicksand',sans-serif;font-weight:700;
    color:#fff;background:var(--sage-deep);width:36px;height:36px;border-radius:50%;display:grid;place-items:center;margin-bottom:.9rem}
  .step h3{margin:0 0 .35rem;font-size:1.08rem}
  .step p{margin:0;color:var(--ink-soft);font-size:.95rem}

  /* CTA */
  .cta{text-align:center;background:var(--ink);color:#fff;border-radius:28px;padding:3rem 1.5rem;box-shadow:var(--shadow)}
  .cta h2{color:#fff;font-size:clamp(1.7rem,3vw,2.4rem);margin:0 0 .6rem}
  .cta p{color:rgba(255,255,255,.82);max-width:48ch;margin:0 auto 1.6rem;font-size:1.05rem}
  .cta .btn{background:#fff;color:var(--ink)}
  .cta .btn:hover{background:#f0ece6}

  /* FAQ */
  .faq{max-width:760px;margin-inline:auto}
  details{background:var(--white);border-radius:16px;padding:1rem 1.3rem;margin-bottom:.8rem;box-shadow:var(--shadow-soft);border:1px solid rgba(55,67,79,.05)}
  summary{cursor:pointer;font-family:'Quicksand',sans-serif;font-weight:600;list-style:none;display:flex;justify-content:space-between;align-items:center;gap:1rem}
  summary::-webkit-details-marker{display:none}
  summary::after{content:'+';font-size:1.3rem;color:var(--sage-deep);transition:transform .2s ease}
  details[open] summary::after{transform:rotate(45deg)}
  details p{margin:.8rem 0 0;color:var(--ink-soft);font-size:.96rem}

  /* Footer */
  footer.site{padding:2.5rem 0;border-top:1px solid rgba(55,67,79,.1);margin-top:1rem}
  .foot{display:flex;flex-wrap:wrap;gap:1rem;justify-content:space-between;align-items:center;color:var(--ink-soft);font-size:.9rem}
  .foot a{text-decoration:none;color:var(--ink-soft);font-weight:600}
  .foot a:hover{color:var(--ink)}
  .foot-links{display:flex;gap:1.4rem;flex-wrap:wrap}

  @media (max-width:860px){
    .hero-grid,.features,.steps{grid-template-columns:1fr}
    .hero-media{order:-1}
    .hero p.lead{max-width:none}
    section.block{padding:3rem 0}
  }
</style>
</head>
<body>

<header class="site">
  <div class="wrap nav">
    <img src="assets/logo.jpg" alt="naptly" class="logo">
    <a href="#anmelden" class="btn">Vorregistrieren</a>
  </div>
</header>

<main>
  <!-- HERO -->
  <section class="hero">
    <div class="wrap hero-grid">
      <div class="hero-copy">
        <span class="eyebrow">● Jetzt vorregistrieren · Early Access</span>
        <h1>Geborgener Schlaf.<br><span class="soft">Überall dabei.</span></h1>
        <p class="lead">naptly ist das tragbare, atmungsaktive Babynest – ein vertrauter, sicherer Rückzugsort für dein Baby, zu Hause und unterwegs.</p>

        <div class="signup" id="anmelden">
          <?php if ($banner): ?>
            <div class="banner <?= htmlspecialchars($banner['type']) ?>"><?= htmlspecialchars($banner['text']) ?></div>
          <?php endif; ?>
          <h3>Sei von Anfang an dabei</h3>
          <p class="hint">Trag dich unverbindlich ein und erfahre als Erstes, wann naptly verfügbar ist – plus Early-Bird-Vorteil zum Start.</p>
          <form method="post" action="signup.php" id="signupForm" novalidate>
            <div class="field">
              <label for="name">Vorname <span style="font-weight:400">(optional)</span></label>
              <input type="text" id="name" name="name" autocomplete="given-name" placeholder="Wie dürfen wir dich nennen?">
            </div>
            <div class="field">
              <label for="email">E-Mail-Adresse</label>
              <input type="email" id="email" name="email" required autocomplete="email" placeholder="du@beispiel.de">
            </div>
            <!-- Honeypot gegen Bots: bleibt für Menschen unsichtbar -->
            <div class="hp" aria-hidden="true"><label>Website<input type="text" name="website" tabindex="-1" autocomplete="off"></label></div>
            <label class="consent">
              <input type="checkbox" name="consent" value="1" required>
              <span>Ja, ich möchte per E-Mail über den Start von naptly informiert werden. Die Einwilligung kann ich jederzeit widerrufen. Mehr in der <a href="datenschutz.php" target="_blank" rel="noopener">Datenschutzerklärung</a>.</span>
            </label>
            <button type="submit" class="btn">Auf die Liste setzen</button>
          </form>
        </div>

        <div class="trust">
          <span><span class="dot"></span> Unverbindlich &amp; kostenlos</span>
          <span><span class="dot"></span> Kein Spam</span>
          <span><span class="dot"></span> Jederzeit abmeldbar</span>
        </div>
      </div>

      <div class="hero-media">
        <img src="assets/nest.webp" alt="naptly Babynest – tragbar mit atmungsaktiven Mesh-Seiten, Nackenrolle und Tragegriffen" class="photo" width="1980" height="820">
        <span class="concept-note">Produktvisualisierung · Konzept</span>
      </div>
    </div>
  </section>

  <!-- FEATURES -->
  <section class="block">
    <div class="wrap">
      <div class="section-head">
        <h2>Durchdacht bis ins Detail</h2>
        <p>Entwickelt für ruhigen Schlaf – und für Eltern, die flexibel bleiben wollen.</p>
      </div>
      <div class="features">
        <div class="feature">
          <div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12c3 0 3-4 6-4s3 4 6 4 3-4 6-4"/><path d="M3 18c3 0 3-4 6-4s3 4 6 4 3-4 6-4"/></svg></div>
          <h3>Atmungsaktiv</h3>
          <p>Umlaufende Mesh-Seiten sorgen für gute Luftzirkulation – angenehm an warmen wie an kühlen Tagen.</p>
        </div>
        <div class="feature">
          <div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8h12l-1 11a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L6 8z"/><path d="M9 8V6a3 3 0 0 1 6 0v2"/></svg></div>
          <h3>Tragbar</h3>
          <p>Mit integrierten Griffen schnell von Raum zu Raum oder mit – ein vertrauter Schlafplatz, wohin ihr auch geht.</p>
        </div>
        <div class="feature">
          <div class="ic"><svg viewBox="0 0 24 24" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3z"/></svg></div>
          <h3>Geborgen</h3>
          <p>Weiche, umschließende Form und gepolsterte Ränder geben deinem Baby ein kuscheliges Gefühl von Nähe.</p>
        </div>
      </div>
    </div>
  </section>

  <!-- HOW IT WORKS -->
  <section class="block band">
    <div class="wrap">
      <div class="section-head">
        <h2>So läuft die Vorregistrierung</h2>
        <p>In drei Schritten dabei – völlig unverbindlich.</p>
      </div>
      <div class="steps">
        <div class="step"><h3>Eintragen</h3><p>E-Mail eingeben und auf die Liste setzen lassen. Dauert keine 30 Sekunden.</p></div>
        <div class="step"><h3>Informiert bleiben</h3><p>Wir melden uns, sobald naptly in den Verkauf startet – ganz ohne Spam dazwischen.</p></div>
        <div class="step"><h3>Zuerst sichern</h3><p>Als Vorregistrierte:r bekommst du den Early-Bird-Zugang, bevor es alle anderen können.</p></div>
      </div>
    </div>
  </section>

  <!-- CTA -->
  <section class="block">
    <div class="wrap">
      <div class="cta">
        <h2>Bereit für ruhigere Nächte?</h2>
        <p>Sei unter den Ersten, die naptly bekommen. Trag dich jetzt kostenlos und unverbindlich ein.</p>
        <a href="#anmelden" class="btn">Jetzt vorregistrieren</a>
      </div>
    </div>
  </section>

  <!-- FAQ -->
  <section class="block band">
    <div class="wrap">
      <div class="section-head">
        <h2>Häufige Fragen</h2>
      </div>
      <div class="faq">
        <details>
          <summary>Was kostet die Vorregistrierung?</summary>
          <p>Nichts. Die Vorregistrierung ist komplett kostenlos und unverbindlich – du gehst keinerlei Kaufverpflichtung ein.</p>
        </details>
        <details>
          <summary>Wann ist naptly erhältlich?</summary>
          <p>naptly befindet sich aktuell in einer frühen Phase. Sobald ein Starttermin feststeht, informieren wir alle Vorregistrierten als Erstes per E-Mail.</p>
        </details>
        <details>
          <summary>Was passiert mit meiner E-Mail-Adresse?</summary>
          <p>Wir nutzen deine Adresse ausschließlich, um dich über den Start von naptly zu informieren. Keine Weitergabe an Dritte, kein Spam. Du kannst dich jederzeit wieder abmelden. Details in der <a href="datenschutz.php">Datenschutzerklärung</a>.</p>
        </details>
      </div>
    </div>
  </section>
</main>

<footer class="site">
  <div class="wrap foot">
    <div>© <?= date('Y') ?> <?= htmlspecialchars(NAPTLY_BRAND) ?></div>
    <div class="foot-links">
      <a href="#anmelden">Vorregistrieren</a>
      <a href="impressum.php">Impressum</a>
      <a href="datenschutz.php">Datenschutz</a>
    </div>
  </div>
</footer>

<script>
  // Progressive Enhancement: Formular per fetch absenden, ohne Seitenreload.
  (function () {
    var form = document.getElementById('signupForm');
    if (!form) return;
    var card = document.getElementById('anmelden');

    function showBanner(type, text) {
      var old = card.querySelector('.banner');
      if (old) old.remove();
      var b = document.createElement('div');
      b.className = 'banner ' + type;
      b.textContent = text;
      card.insertBefore(b, card.firstChild);
    }

    var MSG = {
      ok: ['success', 'Geschafft! Du stehst jetzt auf der Vorregistrierungs-Liste. Wir melden uns, sobald es losgeht.'],
      duplicate: ['info', 'Diese E-Mail ist bereits registriert – du bist also schon dabei. 💚'],
      invalid: ['error', 'Bitte gib eine gültige E-Mail-Adresse ein.'],
      noconsent: ['error', 'Bitte bestätige kurz die Einwilligung, damit wir dir schreiben dürfen.'],
      error: ['error', 'Da ist etwas schiefgelaufen. Bitte versuch es gleich noch einmal.']
    };

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var btn = form.querySelector('button[type=submit]');
      var orig = btn.textContent;
      btn.disabled = true; btn.textContent = 'Einen Moment …';

      fetch('signup.php', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
        body: new FormData(form)
      })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var m = MSG[d.status] || MSG.error;
        showBanner(m[0], m[1]);
        if (d.status === 'ok') { form.reset(); }
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      })
      .catch(function () { showBanner('error', MSG.error[1]); })
      .finally(function () { btn.disabled = false; btn.textContent = orig; });
    });
  })();
</script>
</body>
</html>
