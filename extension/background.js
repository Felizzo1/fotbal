// Fotbal CZ Spielfinder Updater
// Öffnet einmal täglich fotbal.cz in einem Hintergrund-Tab, liest dort alle Spielpläne aus
// (wie ein normaler Seitenbesuch, nur automatisch) und lädt die Rohdaten ins GitHub-Repo.
importScripts('crawl.js');

const START_URL = 'https://www.fotbal.cz/souteze/subjekty/';
const HOUR = 6; // tägliche Uhrzeit (lokal)

function nextRun() {
  const d = new Date(); d.setHours(HOUR, 0, 0, 0);
  if (d <= new Date()) d.setDate(d.getDate() + 1);
  return d.getTime();
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create('daily', { when: nextRun(), periodInMinutes: 24 * 60 });
});
chrome.runtime.onStartup.addListener(async () => {
  if (!(await chrome.alarms.get('daily'))) chrome.alarms.create('daily', { when: nextRun(), periodInMinutes: 24 * 60 });
  // Verpasste Läufe nachholen, wenn der letzte Erfolg älter als 26 Stunden ist
  const { lastOk } = await chrome.storage.local.get('lastOk');
  if (!lastOk || Date.now() - lastOk > 26 * 3600e3) setTimeout(run, 60e3);
});
chrome.alarms.onAlarm.addListener(a => { if (a.name === 'daily') run(); });
chrome.action.onClicked.addListener(() => run());
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.type === 'fcz-progress') setStatus(msg.text);
  if (msg && msg.type === 'fcz-done') finish(msg, sender.tab && sender.tab.id);
  if (msg && msg.type === 'fcz-run') run();
});

async function setStatus(text, badge) {
  await chrome.storage.local.set({ status: text, statusAt: Date.now() });
  if (badge !== undefined) { chrome.action.setBadgeText({ text: badge }); chrome.action.setBadgeBackgroundColor({ color: badge === 'OK' ? '#1d6b4f' : '#c8322b' }); }
}

async function finish(msg, tabId) {
  await chrome.storage.local.set({ running: false });
  if (msg.ok) { await chrome.storage.local.set({ lastOk: Date.now() }); await setStatus(msg.text, 'OK'); }
  else await setStatus('Fehler: ' + msg.text, 'ERR');
  if (tabId) chrome.tabs.remove(tabId).catch(() => {});
}

async function run() {
  const cfg = await chrome.storage.local.get(['token', 'repo', 'rawKey', 'running', 'runningSince']);
  if (!cfg.token || !cfg.repo || !cfg.rawKey) { await setStatus('Bitte in den Optionen Repo, GitHub-Token und Upload-Schlüssel eintragen.', 'ERR'); chrome.runtime.openOptionsPage(); return; }
  if (cfg.running && Date.now() - (cfg.runningSince || 0) < 30 * 60e3) return; // läuft schon
  await chrome.storage.local.set({ running: true, runningSince: Date.now() });
  await setStatus('Starte …', '…');
  const tab = await chrome.tabs.create({ url: START_URL, active: false });
  // Warten, bis die Seite geladen ist und die Cloudflare-Prüfung von selbst durch ist
  const ready = await new Promise(resolve => {
    const t0 = Date.now();
    const iv = setInterval(async () => {
      try {
        const t = await chrome.tabs.get(tab.id);
        if (t.status === 'complete' && /fotbal\.cz/.test(t.url) && !/moment|Sicherheit|Just a/i.test(t.title || '')) { clearInterval(iv); resolve(true); }
      } catch (e) { clearInterval(iv); resolve(false); }
      if (Date.now() - t0 > 90e3) { clearInterval(iv); resolve(false); }
    }, 2000);
  });
  if (!ready) { await finish({ ok: false, text: 'fotbal.cz hat nicht geladen (Prüfseite?). Versuch es später noch einmal.' }, tab.id); return; }
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: crawlFotbalCz, args: [{ token: cfg.token, repo: cfg.repo, rawKey: cfg.rawKey }] });
  } catch (e) {
    await finish({ ok: false, text: String(e) }, tab.id);
  }
}
