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
chrome.storage.onChanged.addListener(load);
load();
