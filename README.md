# Paperclip Plugins

Sammel-Repo fuer lokal gebaute Paperclip-Plugins auf dem Melchinger/Paperclip-Host.

Lizenz: [MIT](./LICENSE)

## Layout

```text
paperclip-plugins/
  plugins/
    image-issue-analyzer/
    paperclip-issue-archiver/
    zip-issue-expander/
```

## Zweck

- ein gemeinsamer Ort fuer host-lokale Paperclip-Plugin-Entwicklung
- sauberere Ablage als mehrere Einzel-Repos fuer kleine Plugin-Artefakte
- einfaches gemeinsames Backup, Review und spaeteres Aufraeumen
- Quellablage fuer Plugins; die laufende Instanz nutzt weiter die gepackten Runtime-Installationen

## Enthaltene Plugins

- `image-issue-analyzer`
  analysiert Bild-Attachments und kommentiert die Auswertung zurueck ins Issue
- `paperclip-issue-archiver`
  UI-Plugin fuer Bulk-Archivierung von Issues; nutzt dafuer den separaten Session-API-Endpunkt `/session-api/v1/issues/archive` aus `paperclip-session-api`:
  <https://github.com/melchinger/paperclip-session-api>
- `zip-issue-expander`
  entpackt Archiv-Attachments (`.zip`, `.tar`, `.tar.gz`, `.tgz`, `.tar.bz2`) in einen stabilen Company-Binary-Pfad und kommentiert lokale Dateipfade zurueck ins Issue

## Voraussetzungen

Diese Ablage ist derzeit nicht generisch. Die Skripte und Plugins erwarten einen
Paperclip-Host mit den folgenden Annahmen:

- Paperclip-Home unter `/var/lib/paperclip`
- Instanz `default`
- Instanz-Config unter `/var/lib/paperclip/instances/default/config.json`
- Runtime-Plugin-Umgebung unter `/var/lib/paperclip/.paperclip/plugins`
- lokale PostgreSQL-Verbindung aus der Instanz-Config
- lokale Disk-Storage-Provider-Konfiguration

System-Dependencies fuer Build und Installation:

- `node`
- `npm`
- `python3`
- `psql`
- `systemctl`

## Hinweis zur Runtime

Die laufende Paperclip-Instanz laedt Plugins derzeit aus:

```text
/var/lib/paperclip/.paperclip/plugins/node_modules/
```

Dieses Repo ist die Quellablage. Aenderungen hier werden nicht automatisch live,
bis das jeweilige Plugin erneut in die Runtime-Plugin-Umgebung paketiert und
installiert wurde.

## Installationsmodell

Die Skripte in `scripts/` tun bewusst mehr als nur `npm install`:

- bauen bzw. packen das Plugin als `.tgz`
- installieren das Paket in die Runtime-Plugin-Umgebung
- aktualisieren oder erzeugen den passenden Record in `public.plugins`
- setzen den Plugin-Status auf `ready`
- starten optional `paperclip.service` neu

Plugins werden absichtlich als gepackte `.tgz`-Artefakte installiert, nicht als
Symlink-Installationen. So bleibt die Node-Module-Aufloesung fuer Worker stabil.

## Runtime-Refresh

Ein einzelnes Plugin neu bauen, in die Runtime installieren, den DB-Record auf
`ready` setzen und optional `paperclip.service` neu starten:

```bash
./scripts/install-plugin.sh zip-issue-expander
./scripts/install-plugin.sh paperclip-issue-archiver --no-restart
```

Alle Plugins aus `plugins/` neu bauen und in einem Schritt refreshen:

```bash
./scripts/refresh-all-plugins.sh
```

## Betrieb und Verifikation

Nach einer Installation laesst sich der Zustand an drei Stellen pruefen:

1. DB-Record:

```bash
psql "$DATABASE_URL" -At -F $'\t' \
  -c "select plugin_key, status from public.plugins order by plugin_key"
```

2. systemd / Journal:

```bash
journalctl -u paperclip -n 100 --no-pager
```

3. Runtime-Dateien:

```bash
find /var/lib/paperclip/.paperclip/plugins/node_modules -maxdepth 2 -mindepth 1 -type d | sort
```

## Debugging

Typische Fehlerbilder:

- Plugin wird nicht geladen:
  DB-Record in `public.plugins` pruefen, danach Journal anschauen
- Worker startet, findet aber Abhaengigkeiten nicht:
  keine Symlink-Installation verwenden, sondern erneut per `./scripts/install-plugin.sh ...` installieren
- Aenderung ist gebaut, aber nicht live:
  Plugin neu installieren oder `./scripts/refresh-all-plugins.sh` ausfuehren
- Plugin reagiert nicht:
  Event-Trigger des konkreten Plugins im jeweiligen README gegenpruefen
