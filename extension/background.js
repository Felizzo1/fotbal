// Fotbal CZ Spielfinder Updater
// Öffnet dreimal pro Woche (Mo, Mi, Fr) fotbal.cz in einem Hintergrund-Tab, liest dort alle Spielpläne aus
// (wie ein normaler Seitenbesuch, nur automatisch) und lädt die Rohdaten ins GitHub-Repo.
importScripts('crawl.js');

const START_URL = 'https://www.fotbal.cz/souteze/subjekty/';
const WEEKDAYS = [1, 3, 5]; // Wochentage des Abrufs: 0 = Sonntag, 1 = Montag, 3 = Mittwoch, 5 = Freitag, 6 = Samstag
const HOUR = 6;          // Uhrzeit (lokal)
const MAX_GAP = 3 * 24 * 60; // längster Abstand zwischen zwei Terminen in Minuten (Fr → Mo)
const MAX_RUN = 6 * 3600e3; // ein Lauf darf (mit Captcha-Pause) bis zu 6 Stunden dauern

function nextRun() {
  const d = new Date(); d.setHours(HOUR, 0, 0, 0);
  while (!WEEKDAYS.includes(d.getDay()) || d <= new Date()) d.setDate(d.getDate() + 1);
  return d.getTime();
}
// Ein Einmal-Alarm auf den nächsten Termin; nach jedem Auslösen wird der folgende gesetzt
const schedule = () => chrome.alarms.create('scheduled', { when: nextRun() });

chrome.runtime.onInstalled.addListener(async () => {
  await chrome.alarms.clear('daily');  // alter Tages-Alarm aus Version 1.0
  await chrome.alarms.clear('weekly'); // alter Wochen-Alarm bis Version 1.2
  schedule();
});
chrome.runtime.onStartup.addListener(async () => {
  if (!(await chrome.alarms.get('scheduled'))) schedule();
  // Verpassten Lauf nachholen, wenn der letzte Erfolg länger zurückliegt als der größte Abstand (plus Puffer)
  const { lastOk } = await chrome.storage.local.get('lastOk');
  if (!lastOk || Date.now() - lastOk > (MAX_GAP + 120) * 60e3) setTimeout(run, 60e3);
});
chrome.alarms.onAlarm.addListener(a => { if (a.name === 'scheduled') { schedule(); run(); } });
chrome.action.onClicked.addListener(() => run());
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg && msg.type === 'fcz-progress') setStatus(msg.text);
  if (msg && msg.type === 'fcz-done') finish(msg, sender.tab && sender.tab.id);
  if (msg && msg.type === 'fcz-run') run();
  if (msg && msg.type === 'fcz-captcha') askHuman(msg.url);
  if (msg && msg.type === 'fcz-captcha-solved') humanDone();
});

// fotbal.cz zeigt eine Prüfung (reCAPTCHA): Tab nach vorne holen und Bescheid geben.
// Der Lauf wartet, bis die Prüfung von Hand gelöst ist, und macht dann weiter.
async function askHuman(url) {
  const { captchaTab } = await chrome.storage.local.get('captchaTab');
  if (captchaTab) { try { await chrome.tabs.get(captchaTab); return; } catch (e) {} }
  const tab = await chrome.tabs.create({ url, active: true });
  await chrome.windows.update(tab.windowId, { focused: true }).catch(() => {});
  await chrome.storage.local.set({ captchaTab: tab.id });
  await setStatus('fotbal.cz möchte eine Captcha-Prüfung. Bitte im geöffneten Tab lösen, der Abruf läuft danach von selbst weiter.', '!');
  chrome.notifications.create('fcz-captcha', { type: 'basic', iconUrl: 'icon.png', title: 'Spielfinder: Captcha lösen',
    message: 'fotbal.cz verlangt eine Prüfung. Bitte im geöffneten Tab lösen, danach geht der Abruf weiter.', requireInteraction: true });
}
async function humanDone() {
  const { captchaTab } = await chrome.storage.local.get('captchaTab');
  await chrome.storage.local.remove('captchaTab');
  chrome.notifications.clear('fcz-captcha');
  if (captchaTab) chrome.tabs.remove(captchaTab).catch(() => {});
  await setStatus('Prüfung gelöst, Abruf läuft weiter …', '…');
}

async function setStatus(text, badge) {
  await chrome.storage.local.set({ status: text, statusAt: Date.now() });
  if (badge !== undefined) { chrome.action.setBadgeText({ text: badge }); chrome.action.setBadgeBackgroundColor({ color: badge === 'OK' ? '#1d6b4f' : '#c8322b' }); }
}

async function finish(msg, tabId) {
  await chrome.storage.local.set({ running: false });
  await humanDone().catch(() => {});
  if (msg.ok) { await chrome.storage.local.set({ lastOk: Date.now() }); await setStatus(msg.text, 'OK'); }
  else await setStatus('Fehler: ' + msg.text, 'ERR');
  if (tabId) chrome.tabs.remove(tabId).catch(() => {});
}

async function run() {
  const cfg = await chrome.storage.local.get(['token', 'repo', 'rawKey', 'running', 'runningSince']);
  if (!cfg.token || !cfg.repo || !cfg.rawKey) { await setStatus('Bitte in den Optionen Repo, GitHub-Token und Upload-Schlüssel eintragen.', 'ERR'); chrome.runtime.openOptionsPage(); return; }
  if (cfg.running && Date.now() - (cfg.runningSince || 0) < MAX_RUN) return; // läuft schon
  await chrome.storage.local.set({ running: true, runningSince: Date.now() });
  await setStatus('Starte …', '…');
  const tab = await chrome.tabs.create({ url: START_URL, active: false });
  // Warten, bis die Seite geladen ist und eine Prüfseite von selbst durch ist.
  // Hängt sie nach 90 Sekunden noch, den Tab nach vorne holen, damit du sie lösen kannst (bis zu 2 Stunden).
  let asked = false;
  const ready = await new Promise(resolve => {
    const t0 = Date.now();
    const iv = setInterval(async () => {
      try {
        const t = await chrome.tabs.get(tab.id);
        if (t.status === 'complete' && /fotbal\.cz/.test(t.url) && !/moment|Sicherheit|Just a|captcha|robot/i.test(t.title || '')) { clearInterval(iv); resolve(true); return; }
        if (!asked && Date.now() - t0 > 90e3) {
          asked = true;
          await chrome.tabs.update(tab.id, { active: true }); await chrome.windows.update(t.windowId, { focused: true }).catch(() => {});
          await setStatus('fotbal.cz zeigt eine Prüfseite. Bitte im Tab lösen, der Abruf startet danach von selbst.', '!');
          chrome.notifications.create('fcz-captcha', { type: 'basic', iconUrl: 'icon.png', title: 'Spielfinder: Captcha lösen',
            message: 'fotbal.cz zeigt eine Prüfseite. Bitte im Tab lösen.', requireInteraction: true });
        }
      } catch (e) { clearInterval(iv); resolve(false); }
      if (Date.now() - t0 > 2 * 3600e3) { clearInterval(iv); resolve(false); }
    }, 2000);
  });
  if (asked) chrome.notifications.clear('fcz-captcha');
  if (!ready) { await finish({ ok: false, text: 'fotbal.cz hat nicht geladen (Prüfseite?). Versuch es später noch einmal.' }, tab.id); return; }
  try {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: crawlFotbalCz, args: [{ token: cfg.token, repo: cfg.repo, rawKey: cfg.rawKey }] });
  } catch (e) {
    await finish({ ok: false, text: String(e) }, tab.id);
  }
}
