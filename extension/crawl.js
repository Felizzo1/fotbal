// Läuft im fotbal.cz-Tab (eingefügt per chrome.scripting.executeScript).
// Muss in sich geschlossen sein: keine Verweise auf Variablen außerhalb der Funktion.
function crawlFotbalCz(cfg) {
  // Bewusst langsam: eine Anfrage nach der anderen mit 1,5–3 Sekunden Pause.
  // Viele schnelle Anfragen lösen bei fotbal.cz die reCAPTCHA-Prüfung aus.
  const CONCURRENCY = 1;
  const DELAY_MIN = 1500, DELAY_MAX = 3000;
  const CAPTCHA_WAIT = 3 * 3600e3; // so lange wird auf das Lösen einer Prüfung gewartet
  // Zwischenspeicher: Vereine und Wettbewerbsliste ändern sich selten, abgeschlossene Wettbewerbe gar nicht mehr.
  const CLUBS_MAX_AGE = 28 * 86400e3;  // Vereinskarte höchstens alle 4 Wochen neu laden
  const INDEX_MAX_AGE = 7 * 86400e3;   // Verbände und Wettbewerbsliste wöchentlich (neue Pokalrunden erscheinen als neue Wettbewerbe)
  // Wann ein Wettbewerb neu geladen wird (Ziel: nur das Nötige abrufen):
  const SOON = 42 * 86400e3;           // nächstes Spiel binnen 6 Wochen: bei jedem Lauf
  const LATER_MAX_AGE = 14 * 86400e3;  // nächstes Spiel später: alle 2 Wochen
  const DONE_MAX_AGE = 30 * 86400e3;   // kein Spiel mehr offen: einmal im Monat (falls Termine nachgetragen werden)
  const progress = text => { try { chrome.runtime.sendMessage({ type: 'fcz-progress', text }); } catch (e) {} };
  const done = (ok, text) => { try { chrome.runtime.sendMessage({ type: 'fcz-done', ok, text }); } catch (e) {} };

  (async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const errors = [];
    // Erkennt eine Prüfseite statt des erwarteten Inhalts. expect: woran die richtige Seite zu erkennen ist.
    const MAIN = /<main[\s>]/i;
    const isBlocked = (status, html, expect = MAIN) => status === 403 || status === 429 ||
      (!!html && /captcha|cf-challenge/i.test(html) && !expect.test(html));
    let badInRow = 0; // Seiten in Folge ohne erwarteten Inhalt: ab 5 wird eine Sperre angenommen
    // Bei einer Prüfung: Background holt den Tab nach vorne, hier wird gewartet, bis sie gelöst ist.
    let humanWait = null;
    const waitForHuman = (url, expect = MAIN) => humanWait || (humanWait = (async () => {
      chrome.runtime.sendMessage({ type: 'fcz-captcha', url: new URL(url, location.href).href });
      const t0 = Date.now();
      while (Date.now() - t0 < CAPTCHA_WAIT) {
        await sleep(20e3);
        try { const r = await fetch(url, { credentials: 'include' }); const h = await r.text(); if (r.ok && expect.test(h)) { badInRow = 0; chrome.runtime.sendMessage({ type: 'fcz-captcha-solved' }); humanWait = null; return; } } catch (e) {}
      }
      throw new Error('Captcha-Prüfung wurde nicht gelöst');
    })());
    let last = 0;
    const throttle = async () => { const wait = last + DELAY_MIN + Math.random() * (DELAY_MAX - DELAY_MIN) - Date.now(); if (wait > 0) await sleep(wait); last = Date.now(); };
    let lastFail = null; // letzte fehlgeschlagene Anfrage, für die Diagnose
    const getHtml = async (url, expect = MAIN, tries = 3) => {
      for (let i = 0; i < tries; i++) {
        if (humanWait) await humanWait;
        await throttle();
        try {
          const r = await fetch(url, { credentials: 'include' }); const h = await r.text();
          if (isBlocked(r.status, h, expect)) { await waitForHuman(url, expect); i--; continue; }
          if (r.ok && expect.test(h)) { badInRow = 0; return h; }
          lastFail = { url, status: r.status, len: h.length, head: h.slice(0, 300) };
          if (++badInRow >= 5) { await waitForHuman(url, expect); i--; continue; }
        } catch (e) { if (/Captcha/.test(String(e))) throw e; lastFail = { url, error: String(e) }; }
        await sleep(5000 * (i + 1));
      }
      errors.push(url); return null;
    };
    const COMP_PAGE = /Rozpis a v|js-matchRoundSection/;
    const parse = async (url, expect = MAIN) => { const h = await getHtml(url, expect); return h ? new DOMParser().parseFromString(h, 'text/html') : null; };
    const pool = async (items, fn) => { let i = 0; await Promise.all([...Array(CONCURRENCY)].map(async () => { while (i < items.length) { const k = i++; await fn(items[k], k); } })); };
    const txt = e => (e && e.textContent || '').replace(/\s+/g, ' ').trim();
    const uuidFromSrc = s => { const m = (s || '').match(/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_crop/); return m ? m[1] : null; };
    const dateIso = s => { const m = (s || '').match(/(\d{1,2})\.\s*(\d{1,2})\.\s*(\d{4})(?:\s+(\d{1,2}):(\d{2}))?/); return m ? m[3] + '-' + m[2].padStart(2, '0') + '-' + m[1].padStart(2, '0') + (m[4] ? 'T' + m[4].padStart(2, '0') + ':' + m[5] : '') : null; };

    // Spiele einer Wettbewerbsseite auslesen
    const readMatches = d => {
      const out = [];
      for (const sec of d.querySelectorAll('.js-matchRoundSection')) {
        const round = (txt(sec.querySelector('h1,h2,h3,h4,h5,h6')).match(/(\d+)\.\s*kolo/) || [])[1];
        for (const li of sec.querySelectorAll('li.MatchRound')) {
          const mid = (((li.querySelector('a.MatchRound-match') || {}).getAttribute ? li.querySelector('a.MatchRound-match').getAttribute('href') : '') || '').match(/([0-9a-f-]{36})/);
          const sides = [...li.querySelectorAll('.MatchRound-mainInfoContainer ul > li')].slice(0, 2);
          if (sides.length < 2) continue;
          const meta = {};
          for (const p of li.querySelectorAll('.MatchRound-detailsContainer li p')) { const st = p.querySelector('strong'); if (st) meta[txt(st).replace(':', '')] = txt(p).replace(txt(st), '').trim(); }
          const img = s => { const i = s.querySelector('img'); return uuidFromSrc(i && i.getAttribute('src')); };
          out.push({ round: round ? +round : null, hn: txt(sides[0].querySelector('span') || sides[0]), hc: img(sides[0]), an: txt(sides[1].querySelector('span') || sides[1]), ac: img(sides[1]),
            score: txt(li.querySelector('.MatchRound-mainInfoContainer strong')), dt: dateIso(meta['Datum']), venue: meta['Hřiště'] || '', spec: meta['Diváků'] ? parseInt(meta['Diváků']) : null, mid: mid ? mid[1] : null });
        }
      }
      return out;
    };

    // Zwischenspeicher vom letzten Lauf (chrome.storage.local, nur auf diesem Rechner)
    const { cache: old } = await chrome.storage.local.get('cache');
    const cache = old && old.v === 2 ? old : { v: 2, comps: {} };
    const save = () => chrome.storage.local.set({ cache });
    const t0 = Date.now();
    let fetched = 0, reused = 0;

    // 1. Vereine mit Koordinaten (Vereinskarte)
    if (!cache.clubs || t0 - cache.clubs.at > CLUBS_MAX_AGE) {
      progress('Vereinskarte …');
      const mapHtml = await getHtml('/club/hledej', /L\.marker/);
      if (!mapHtml) throw new Error('Vereinskarte nicht erreichbar');
      const data = {};
      for (const m of mapHtml.matchAll(/L\.marker\(\[([\d.]+),\s*([\d.]+)\]\)[\s\S]{0,80}?createMarker\("([^"]*)",\s*[^,]*,\s*"([^"]*)"/g)) {
        const id = (m[4].match(/club\/club\/([0-9a-f-]{36})/) || [])[1]; if (!id) continue;
        data[id] = [m[3], +(+m[1]).toFixed(5), +(+m[2]).toFixed(5)];
      }
      if (Object.keys(data).length < 1000) throw new Error('Vereinskarte unvollständig (' + Object.keys(data).length + ' Vereine)');
      cache.clubs = { at: t0, data }; await save();
    }
    const clubs = cache.clubs.data;

    // 2. + 3. Verbände, ihre Wettbewerbe (Tabelle) und Řídící komise (Linkliste)
    if (!cache.index || t0 - cache.index.at > INDEX_MAX_AGE) {
      progress('Verbände …');
      const rz = await parse('/souteze/subjekty/');
      if (!rz) throw new Error('Rozcestník nicht erreichbar');
      const subjects = []; let kraj = null;
      for (const a of rz.querySelectorAll('main a')) {
        const m = (a.getAttribute('href') || '').match(/subjekt\/(\d+)/); if (!m) continue;
        const name = txt(a); const isKraj = /kraj$|^Hl\. město Praha/.test(name);
        if (isKraj) kraj = name;
        subjects.push({ id: +m[1], name, kraj: isKraj ? name : kraj, type: kraj === null ? 'national' : (isKraj ? 'KFS' : 'OFS') });
      }
      const comps = []; const seen = new Set(); const rk = [];
      let n = 0;
      await pool(subjects, async sj => {
        const d = await parse('/souteze/subjekty/subjekt/' + sj.id); progress('Verbände ' + (++n) + '/' + subjects.length); if (!d) return;
        for (const tr of d.querySelectorAll('main tr')) {
          const tds = [...tr.querySelectorAll('td')]; if (tds.length < 3) continue;
          const a = [...tr.querySelectorAll('a')].find(x => /turnaje\/zapas\//.test(x.getAttribute('href') || '')); if (!a) continue;
          const id = a.getAttribute('href').match(/zapas\/([0-9a-f-]{36})/)[1]; if (seen.has(id)) continue; seen.add(id);
          comps.push({ id, code: txt(tds[0]), name: txt(tds[1]), teams: parseInt(txt(tds[2])) || null, subj: sj.id });
        }
        if (!d.querySelector('main tr')) {
          for (const a of d.querySelectorAll('a')) { const m = (a.getAttribute('href') || '').match(/turnaje\/hlavni\/([0-9a-f-]{36})/); if (m && !seen.has(m[1])) { seen.add(m[1]); rk.push({ id: m[1], subj: sj.id }); } }
        }
      });
      if (comps.length < 500) throw new Error('Nur ' + comps.length + ' Wettbewerbe gefunden');
      cache.index = { at: t0, subjects, comps, rk }; await save();
    }
    // Nur Männer und Frauen abrufen: Jugend, Futsal und Alte Herren zeigt die Seite nicht an.
    // Gleiche Regeln wie classify() in scripts/preprocess.py (Name und erster Buchstabe des Wettbewerbscodes).
    const isAdult = (name, code) => {
      const n = (name || '').toLowerCase(), k = (code || '').charAt(0);
      if (/futsal|malá kopaná|veterán|old ?boys|stará garda|gentleman|u-?40|\+3[05]/.test(n)) return false;
      if (/přípravk|přípravek|bambin|minižá|\d-\d+ let/.test(n) || /(^|[^a-z0-9])u ?([6-9]|1[01])(?![0-9])/.test(n) || (k && 'GHŘ'.includes(k))) return false;
      if (/žák|žačk/.test(n) || /(^|[^a-z0-9])u ?1[2-5](?![0-9])/.test(n) || (k && 'EFŇŠ'.includes(k))) return false;
      if (/doros|junior/.test(n) || /(^|[^a-z0-9])u ?1[6-9](?![0-9])/.test(n) || (k && 'CDL'.includes(k))) return false;
      return true;
    };
    // Řídící komise: Name und Code erst nach dem ersten Laden bekannt (aus der Überschrift)
    const rkInfo = id => { const e = cache.comps[id]; const tm = e && e.title.match(/›\s*\d{4}\s+(\S+)\s+-\s+(.*)$/); return tm ? { code: tm[1], name: tm[2] } : null; };
    const { subjects } = cache.index;
    const comps = cache.index.comps.filter(c => isAdult(c.name, c.code));
    const rk = cache.index.rk.filter(c => { const i = rkInfo(c.id); return !i || isAdult(i.name, i.code); });
    // Zwischenspeicher von Jugendwettbewerben früherer Läufe aufräumen
    const keepIds = new Set([...comps, ...rk].map(c => c.id));
    for (const id of Object.keys(cache.comps)) if (!keepIds.has(id)) delete cache.comps[id];

    // 4. Spiele. Neu geladen wird je nach nächstem Spieltermin (siehe SOON, LATER_MAX_AGE, DONE_MAX_AGE oben).
    // Fortschritt wird laufend gespeichert, damit ein abgebrochener Lauf beim nächsten Mal nicht von vorn beginnt.
    const fresh = id => {
      const c = cache.comps[id]; if (!c) return false;
      if (!c.matches.length) return false; // leere Ergebnisse nie übernehmen (könnten von einer Prüfseite stammen)
      if (c.runStart === t0 || c.runStart === cache.runStart) return true; // in diesem bzw. dem abgebrochenen Lauf schon geladen
      const now = Date.now(), age = now - c.at;
      const upcoming = c.matches.map(m => m.dt ? Date.parse(m.dt) : Infinity).filter(t => t >= now - 86400e3);
      if (!upcoming.length) return age < DONE_MAX_AGE;           // nichts mehr offen
      if (Math.min(...upcoming) - now > SOON) return age < LATER_MAX_AGE; // nächstes Spiel erst in über 6 Wochen
      return false;                                              // Spiele in den nächsten 6 Wochen: immer neu
    };
    if (!cache.runStart || cache.runDone || t0 - cache.runStart > 2 * 86400e3) { cache.runStart = t0; cache.runDone = false; }
    let diag = null;
    const all = [...comps.map(c => ({ ...c, kind: 'comp' })), ...rk.map(c => ({ ...c, kind: 'rk' }))];
    let n = 0;
    await pool(all, async c => {
      if (++n % 50 === 0) progress('Wettbewerbe ' + n + '/' + all.length + ' (' + fetched + ' geladen, ' + reused + ' aus dem Speicher)');
      if (fresh(c.id)) { reused++; return; }
      // Eine echte Wettbewerbsseite heißt „Rozpis a výsledky“; eine Prüf- oder Fehlerseite mit <main> zählt so nicht als Erfolg.
      const d = await parse('/souteze/turnaje/zapas/' + c.id, COMP_PAGE); if (!d) return; // bei Fehler alten Stand behalten
      const ms = readMatches(d);
      if (!ms.length && !diag) { // erste Wettbewerbsseite ohne Spiele für die Diagnose merken
        diag = { url: '/souteze/turnaje/zapas/' + c.id, at: new Date().toISOString(), title: txt(d.querySelector('title')), h1: txt(d.querySelector('main h1')),
          sections: d.querySelectorAll('.js-matchRoundSection').length, items: d.querySelectorAll('li.MatchRound').length, len: d.documentElement.outerHTML.length };
        await chrome.storage.local.set({ diag: { ...diag, html: d.documentElement.outerHTML.slice(0, 2e6) } });
      }
      const prev = cache.comps[c.id];
      if (!ms.length && prev && prev.matches.length) { fetched++; return; } // nicht mit einem leeren Ergebnis überschreiben
      cache.comps[c.id] = { at: Date.now(), runStart: cache.runStart, title: txt(d.querySelector('main h1')), matches: ms };
      if (++fetched % 25 === 0) await save();
    });
    cache.runDone = true; await save();

    const teams = [], teamIdx = new Map(), venues = [], venueIdx = new Map(), matches = [];
    const tIdx = (nm, c) => { const k = nm + '|' + c; if (!teamIdx.has(k)) { teamIdx.set(k, teams.length); teams.push([nm, c]); } return teamIdx.get(k); };
    const vIdx = v => { if (!v) return -1; if (!venueIdx.has(v)) { venueIdx.set(v, venues.length); venues.push(v); } return venueIdx.get(v); };
    comps.forEach((c, ci) => { for (const m of (cache.comps[c.id] || { matches: [] }).matches) matches.push([ci, m.round, tIdx(m.hn, m.hc), tIdx(m.an, m.ac), m.score, m.dt, vIdx(m.venue), m.spec, m.mid]); });
    const extra = { comps: [], matches: [] };
    for (const c of rk) {
      const e = cache.comps[c.id]; if (!e) continue;
      const tm = e.title.match(/›\s*\d{4}\s+(\S+)\s+-\s+(.*)$/);
      const ci = extra.comps.length; extra.comps.push({ id: c.id, subj: c.subj, title: e.title, code: tm ? tm[1] : '', name: tm ? tm[2] : e.title });
      for (const m of e.matches) extra.matches.push([ci, m.round, m.hn, m.hc, m.an, m.ac, m.score, m.dt, m.venue, m.spec, m.mid]);
    }
    if (matches.length < 20000) {
      const parts = ['Nur ' + matches.length + ' Spiele gefunden', fetched + ' Wettbewerbe geladen, ' + reused + ' aus dem Speicher, ' + errors.length + ' Seiten nicht erreichbar'];
      if (diag) parts.push('Beispielseite ohne Spiele: „' + diag.title + '“, ' + diag.len + ' Zeichen, ' + diag.sections + ' Spieltag-Abschnitte, ' + diag.items + ' Spiel-Einträge (in den Optionen „Diagnose speichern“)');
      if (lastFail) parts.push('Letzter Fehler: ' + lastFail.url + ' → ' + (lastFail.error || 'Status ' + lastFail.status + ', ' + lastFail.len + ' Zeichen'));
      await chrome.storage.local.set({ diagSummary: parts.join(' · '), diagFail: lastFail });
      throw new Error(parts.join(' · '));
    }
    if (errors.length > comps.length * 0.05) throw new Error(errors.length + ' Seiten nicht erreichbar');

    // 5. Packen und nach GitHub hochladen
    progress('Hochladen …');
    const now = new Date(); const y = now.getMonth() >= 6 ? now.getFullYear() : now.getFullYear() - 1;
    const data = { generated: now.toISOString(), source: 'fotbal.cz', season: y + '/' + String(y + 1).slice(2), subjects, comps, clubs, teams, venues,
      matchFields: ['comp', 'round', 'home', 'away', 'score', 'datetime', 'venue', 'spectators', 'matchId'], matches, extra, errors: errors.length };
    const gz = await new Response(new Blob([JSON.stringify(data)]).stream().pipeThrough(new CompressionStream('gzip'))).blob();
    // Verschlüsseln (Format FCZ1: salt + iv + AES-256-GCM, Schlüssel per PBKDF2 aus dem Upload-Schlüssel)
    const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    const base = await crypto.subtle.importKey('raw', new TextEncoder().encode(cfg.rawKey), 'PBKDF2', false, ['deriveKey']);
    const key = await crypto.subtle.deriveKey({ name: 'PBKDF2', salt, iterations: 310000, hash: 'SHA-256' }, base, { name: 'AES-GCM', length: 256 }, false, ['encrypt']);
    const ct = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, await gz.arrayBuffer());
    const enc = new Blob([new TextEncoder().encode('FCZ1'), salt, iv, ct]);
    const b64 = await new Promise(res => { const fr = new FileReader(); fr.onload = () => res(String(fr.result).split(',')[1]); fr.readAsDataURL(enc); });
    const api = 'https://api.github.com/repos/' + cfg.repo + '/contents/raw/fotbal_cz.json.gz.enc';
    const H = { Authorization: 'Bearer ' + cfg.token, Accept: 'application/vnd.github.object', 'X-GitHub-Api-Version': '2022-11-28' };
    let sha; const g = await fetch(api, { headers: H, credentials: 'omit' }); if (g.ok) sha = (await g.json()).sha; else if (g.status !== 404) throw new Error('GitHub ' + g.status + ' beim Lesen (Token/Repo prüfen)');
    const p = await fetch(api, { method: 'PUT', headers: H, credentials: 'omit', body: JSON.stringify({ message: 'Daten ' + now.toISOString().slice(0, 16).replace('T', ' ') + ': ' + (matches.length + extra.matches.length) + ' Spiele', content: b64, sha }) });
    if (!p.ok) throw new Error('GitHub ' + p.status + ' beim Hochladen: ' + (await p.text()).slice(0, 200));
    done(true, (matches.length + extra.matches.length).toLocaleString('de-DE') + ' Spiele hochgeladen (' + fetched + ' Wettbewerbe neu geladen, ' + reused + ' aus dem Speicher), ' + now.toLocaleString('de-DE'));
  })().catch(e => done(false, String(e && e.message || e)));

  return 'gestartet';
}
