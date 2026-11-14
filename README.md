# Fotbal CZ Spielfinder

Adresse: https://felizzo1.github.io/fotbal/ (passwortgeschützt)

Alle Spiele des tschechischen Fußballs auf einer Karte und in einer Liste, von der Chance Liga bis zur 10. Liga, dazu Frauen, Dorost, Žáci und Přípravka. Filter nach Zeitraum, Ort mit Umkreis, Kraj, Okres, Kategorie und Ligaebene.

Daten: [fotbal.cz](https://www.fotbal.cz) (FAČR). Bezirksgrenzen: ČÚZK über [siwekm/czech-geojson](https://github.com/siwekm/czech-geojson) (CC BY 4.0).

## Aufbau

| Ordner | Inhalt |
|---|---|
| `extension/` | Chrome-Erweiterung, die einmal pro Woche die Spielpläne auf fotbal.cz ausliest und verschlüsselt als `raw/fotbal_cz.json.gz.enc` hier hochlädt |
| `raw/` | verschlüsselte Rohdaten des letzten Abrufs |
| `scripts/fczcrypt.py` | Ver- und Entschlüsselung (AES-256-GCM, Schlüssel per PBKDF2) |
| `scripts/preprocess.py` | bereitet die Rohdaten zu `site/data.json` auf (Kategorie, Ligaebene, Okres, Koordinaten) |
| `site/` | die Webseite (Leaflet, OpenStreetMap) |
| `.github/workflows/build.yml` | baut bei jedem neuen Datenstand die Seite und veröffentlicht sie über GitHub Pages |

fotbal.cz lässt nur echte Browser zu. Deshalb läuft der Abruf in Chrome (auf einem Raspberry Pi) und nicht auf GitHub.

Die Seite ist passwortgeschützt: Im Repo und auf GitHub Pages liegen die Spieldaten nur verschlüsselt. Erst der Browser entschlüsselt sie nach Eingabe des Passworts.

## Einrichtung

1. **GitHub Pages einschalten:** Settings → Pages → Source: „GitHub Actions“.
2. **Secrets anlegen:** Settings → Secrets and variables → Actions → New repository secret:
   - `SITE_PASSWORD`: das Passwort für die Seite (zum Weitergeben)
   - `RAW_PASSWORD`: der Upload-Schlüssel aus den Optionen der Erweiterung (nicht weitergeben)
3. **Token anlegen:** Settings (Profil) → Developer settings → Personal access tokens → Fine-grained tokens → Generate. Repository access: nur dieses Repo. Permissions → Contents: Read and write.
4. **Erweiterung laden:** Ordner `extension/` herunterladen, in Chrome `chrome://extensions` öffnen, Entwicklermodus einschalten, „Entpackte Erweiterung laden“ und den Ordner wählen.
5. **Erweiterung einrichten:** Rechtsklick aufs Symbol → Optionen. Repo und Token eintragen, „Schlüssel erzeugen“, den Schlüssel als `RAW_PASSWORD` in GitHub eintragen, speichern, „Jetzt aktualisieren“.

Danach läuft der Abruf jeden Montag um 6 Uhr, sofern Chrome offen ist, sonst beim nächsten Chrome-Start. Ein Klick aufs Symbol startet ihn sofort. Wochentag und Uhrzeit stehen oben in `extension/background.js` (`WEEKDAY`, `HOUR`).

Die Abfrage ist absichtlich langsam (eine Seite nach der anderen, 1,5–3 Sekunden Pause) und dauert ein bis zwei Stunden, damit fotbal.cz keine Captcha-Prüfung auslöst. Kommt trotzdem eine, öffnet die Erweiterung den Tab im Vordergrund und zeigt eine Benachrichtigung. Nach dem Lösen läuft der Abruf von selbst weiter, gewartet wird bis zu drei Stunden. Auf dem Raspberry Pi geht das z. B. per VNC.

Passwort ändern: Secret `SITE_PASSWORD` ersetzen, dann unter Actions den Workflow „Seite bauen und veröffentlichen“ mit „Run workflow“ neu starten. Das alte Passwort funktioniert danach nicht mehr.
