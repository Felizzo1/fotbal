const $ = id => document.getElementById(id);
async function load() {
  const s = await chrome.storage.local.get(['repo', 'token', 'rawKey', 'status', 'statusAt', 'lastOk']);
  $('repo').value = s.repo || 'Felizzo1/fotbal';
  $('token').value = s.token || '';
  $('rawKey').value = s.rawKey || '';
  $('status').textContent = s.status || 'noch kein Lauf';
  $('when').textContent = (s.statusAt ? 'Meldung vom ' + new Date(s.statusAt).toLocaleString('de-DE') : '') + (s.lastOk ? ' · letzter Erfolg ' + new Date(s.lastOk).toLocaleString('de-DE') : '');
}
const vals = () => ({ repo: $('repo').value.trim(), token: $('token').value.trim(), rawKey: $('rawKey').value.trim() });
$('gen').onclick = () => {
  if ($('rawKey').value && !window.confirmed) { $('status').textContent = 'Es gibt schon einen Schlüssel. Ein neuer muss auch in GitHub ersetzt werden. Zum Erzeugen nochmal klicken.'; window.confirmed = true; return; }
  const b = crypto.getRandomValues(new Uint8Array(24));
  $('rawKey').value = btoa(String.fromCharCode(...b)).replace(/[+/=]/g, c => ({ '+': 'x', '/': 'y', '=': '' }[c]));
  $('rawKey').select();
  $('status').textContent = 'Neuer Schlüssel erzeugt. Kopieren, in GitHub als RAW_PASSWORD eintragen, dann hier speichern.';
};
$('save').onclick = async () => {
  await chrome.storage.local.set(vals());
  $('status').textContent = 'Gespeichert.';
};
$('run').onclick = async () => {
  await chrome.storage.local.set(vals());
  chrome.runtime.sendMessage({ type: 'fcz-run' });
  $('status').textContent = 'Läuft …';
};
$('clear').onclick = async () => {
  await chrome.storage.local.remove('cache');
  $('status').textContent = 'Speicher geleert. Der nächste Lauf lädt alles neu.';
};
$('diag').onclick = async () => {
  const s = await chrome.storage.local.get(['diag', 'diagSummary', 'diagFail', 'status']);
  const info = { version: chrome.runtime.getManifest().version, status: s.status, summary: s.diagSummary, lastFail: s.diagFail,
    sample: s.diag ? { ...s.diag, html: undefined } : null };
  // Kopf mit Infos, danach die gespeicherte Beispielseite (ohne Token oder Schlüssel)
  const text = '<!-- Spielfinder-Diagnose\n' + JSON.stringify(info, null, 2).replace(/--/g, '- -') + '\n-->\n' + (s.diag ? s.diag.html : '<p>Keine Beispielseite gespeichert.</p>');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([text], { type: 'text/html' }));
  a.download = 'spielfinder-diagnose.html'; a.click();
  $('status').textContent = 'Diagnose gespeichert (spielfinder-diagnose.html im Download-Ordner).';
};
chrome.storage.onChanged.addListener(load);
$('ver').textContent = 'Version ' + chrome.runtime.getManifest().version;
load();
