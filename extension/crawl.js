// Läuft im fotbal.cz-Tab (eingefügt per chrome.scripting.executeScript).
// Muss in sich geschlossen sein: keine Verweise auf Variablen außerhalb der Funktion.
function crawlFotbalCz(cfg) {
  const CONCURRENCY = 3;
  const progress = text => { try { chrome.runtime.sendMessage({ type: 'fcz-progress', text }); } catch (e) {} };
  const done = (ok, text) => { try { chrome.runtime.sendMessage({ type: 'fcz-done', ok, text }); } catch (e) {} };

  (async () => {
    const sleep = ms => new Promise(r => setTimeout(r, ms));
    const errors = [];
    const getHtml = async (url, tries = 3) => {
      for (let i = 0; i < tries; i++) {
        try { const r = await fetch(url, { credentials: 'include' }); if (r.ok) return await r.text(); } catch (e) {}
        await sleep(2000 * (i + 1));
      }
      errors.push(url); return null;
    };
    const parse = async url => { const h = await getHtml(url); return h ? new DOMParser().parseFromString(h, 'text/html') : null; };
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

    // 1. Vereine mit Koordinaten (Vereinskarte)
    progress('Vereinskarte …');
    const mapHtml = await getHtml('/club/hledej');
    if (!mapHtml) throw new Error('Vereinskarte nicht erreichbar');
    const clubs = {};
    for (const m of mapHtml.matchAll(/L\.marker\(\[([\d.]+),\s*([\d.]+)\]\)[\s\S]{0,80}?createMarker\("([^"]*)",\s*[^,]*,\s*"([^"]*)"/g)) {
      const id = (m[4].match(/club\/club\/([0-9a-f-]{36})/) || [])[1]; if (!id) continue;
      clubs[id] = [m[3], +(+m[1]).toFixed(5), +(+m[2]).toFixed(5)];
    }
    if (Object.keys(clubs).length < 1000) throw new Error('Vereinskarte unvollständig (' + Object.keys(clubs).length + ' Vereine)');

    // 2. Verbände
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

    // 3. Wettbewerbe je Verband (Tabelle) und Řídící komise (Linkliste)
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

    // 4. Spiele
    const teams = [], teamIdx = new Map(), venues = [], venueIdx = new Map(), matches = [];
    const tIdx = (nm, c) => { const k = nm + '|' + c; if (!teamIdx.has(k)) { teamIdx.set(k, teams.length); teams.push([nm, c]); } return teamIdx.get(k); };
    const vIdx = v => { if (!v) return -1; if (!venueIdx.has(v)) { venueIdx.set(v, venues.length); venues.push(v); } return venueIdx.get(v); };
    n = 0;
    await pool(comps, async (c, ci) => {
      const d = await parse('/souteze/turnaje/zapas/' + c.id); if (++n % 50 === 0) progress('Wettbewerbe ' + n + '/' + comps.length); if (!d) return;
      for (const m of readMatches(d)) matches.push([ci, m.round, tIdx(m.hn, m.hc), tIdx(m.an, m.ac), m.score, m.dt, vIdx(m.venue), m.spec, m.mid]);
    });
    const extra = { comps: [], matches: [] };
    await pool(rk, async c => {
      const d = await parse('/souteze/turnaje/zapas/' + c.id); if (!d) return;
      const title = txt(d.querySelector('main h1')); const tm = title.match(/›\s*\d{4}\s+(\S+)\s+-\s+(.*)$/);
      const ci = extra.comps.length; extra.comps.push({ id: c.id, subj: c.subj, title, code: tm ? tm[1] : '', name: tm ? tm[2] : title });
      for (const m of readMatches(d)) extra.matches.push([ci, m.round, m.hn, m.hc, m.an, m.ac, m.score, m.dt, m.venue, m.spec, m.mid]);
    });
    if (matches.length < 20000) throw new Error('Nur ' + matches.length + ' Spiele gefunden');
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
    done(true, (matches.length + extra.matches.length).toLocaleString('de-DE') + ' Spiele hochgeladen, ' + now.toLocaleString('de-DE'));
  })().catch(e => done(false, String(e && e.message || e)));

  return 'gestartet';
}
