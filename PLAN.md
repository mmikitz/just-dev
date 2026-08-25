# Plan: Übertragbares `scripts/devtools`-Starterkit mit Verb–Objekt-Recipes

## Zusammenfassung

Alle Devtool-Artefakte – Just-Recipes, Python-Code, uv-Projekt, Konfiguration, Tests und Dokumentation – liegen geschlossen unter `scripts/devtools/` und können als ein Verzeichnis in andere Projekte kopiert werden.

Außerhalb bleibt nur die akzeptierte Integrationszeile im bestehenden oder neuen Root-`justfile`:

```just
import 'scripts/devtools/justfile'
```

Intern bleiben die Tools als `just`-Module organisiert. Flache Aliases bilden die bevorzugte Verb–Objekt-Oberfläche; Tool-Namespaces bleiben zusätzlich verfügbar. `just` unterstützt sowohl relative Imports als auch [Aliases auf Submodul-Recipes](https://just.systems/man/en/aliases.html).

## Verzeichnis- und Recipe-Struktur

```text
justfile                                  # nur Import-Zeile
scripts/devtools/
├── justfile                              # Module + flache Aliases
├── recipes/
│   ├── common.just
│   ├── auth.just
│   ├── jira.just
│   ├── bitbucket.just
│   ├── jenkins.just
│   ├── confluence.just
│   └── project.just                      # projektspezifischer Verify-/CI-Hook
├── config/
│   ├── project.example.toml
│   └── project.toml                      # nach Übernahme eingecheckt
├── pyproject.toml
├── uv.lock
├── src/just_dev/
├── tests/
└── README.md
```

- `scripts/devtools/justfile` enthält nur `mod`-Deklarationen und flache Aliases, damit keine globalen Settings mit einem vorhandenen Projekt-Justfile kollidieren.
- Jedes Modul importiert `common.just`, setzt sein Arbeitsverzeichnis auf `scripts/devtools/` und startet die CLI mit `uv run --locked just-dev`.
- Der Projektroot wird über `JUST_DEV_PROJECT_ROOT=justfile_directory()` an die CLI übergeben; dadurch funktionieren Git-Erkennung, Markdown-Dateien und Projektchecks unabhängig vom aktuellen Verzeichnis.
- Recipe-Parameter werden als exportierte `JUST_DEV_*`-Variablen weitergereicht. Benutzereingaben werden nicht in Shell-Befehle interpoliert, wodurch Linux, PowerShell und WSL gleich behandelt werden.
- Voraussetzung: Python 3.12+, uv und `just >= 1.55`. Die lokal vorhandene Version 1.21 muss aktualisiert werden.

## Öffentliche Befehle

Die flache Verb–Objekt-Form ist kanonisch. Die Tool-Variante ruft dasselbe Recipe auf und verhält sich identisch.

| Bevorzugter Aufruf                  | Tool-Namespace                               |
| ----------------------------------- | -------------------------------------------- |
| `just check-devtools`               | `just devtools check-devtools`               |
| `just configure-auth`               | `just auth configure-auth`                   |
| `just unlock-secrets`               | `just auth unlock-secrets`                   |
| `just show-auth-status`             | `just auth show-auth-status`                 |
| `just lock-secrets`                 | `just auth lock-secrets`                     |
| `just create-jira-issue PRESET SUMMARY` | `just jira create-jira-issue PRESET SUMMARY` |
| `just read-jira-isdue KEY`          | `just jira read-jira-isdue KEY`              |
| `just update-jira-issue KEY [JSON]` | `just jira update-jira-issue KEY [JSON]`     |
| `just delete-jira-issue KEY`        | `just jira delete-jira-issue KEY`            |
| `just create-pull-request "Title"`  | `just bitbucket create-pull-request "Title"` |
| `just show-pull-request [ID]`       | `just bitbucket show-pull-request [ID]`      |
| `just run-build PRESET`             | `just jenkins run-build PRESET`              |
| `just show-build-status PRESET REF` | `just jenkins show-build-status PRESET REF`  |
| `just preview-release-notes FILE`   | `just confluence preview-release-notes FILE` |
| `just publish-release-notes FILE`   | `just confluence publish-release-notes FILE` |
| `just verify-project`               | `just project verify-project`                |
| `just run-ci`                       | `just project run-ci`                        |

Das interne `scripts/devtools/justfile` definiert dafür beispielsweise:

```just
mod jira 'recipes/jira.just'
alias create-jira-issue := jira::create-jira-issue
alias read-jira-isdue := jira::read-jira-isdue
alias update-jira-issue := jira::update-jira-issue
alias delete-jira-issue := jira::delete-jira-issue
```

Mutierende Recipes besitzen die einheitlichen Flags `--dry-run` und `--yes`. Ohne `--yes` wird zuerst eine Vorschau angezeigt und anschließend interaktiv bestätigt; ohne TTY bricht der Befehl ab.

## Python- und Konfigurationsarchitektur

- Das isolierte uv-Paket verwendet `typer`, `pydantic`, `platformdirs`, `pykeepass`, `atlassian-python-api` und `python-jenkins`. Kompatible Versionsbereiche stehen in `pyproject.toml`, exakte plattformübergreifende Versionen im eingecheckten [uv-Lockfile](https://docs.astral.sh/uv/concepts/projects/layout/).
- `config/project.toml` enthält keine Secrets, sondern die Atlassian-Cloud-ID, Bitbucket-Workspace/Repository, Zielbranch, Reviewer, Jenkins-Jobpresets, Confluence-Seitenziele und Jira-Presets (`project`, `issue_type`, `labels`, `components`). `summary`/`description` werden pro Aufruf explizit übergeben, projektspezifische Custom Fields optional als JSON.
- Wrapper werden hinter eigenen Adaptern gekapselt. Wrapper-Objekte gelangen nicht in CLI oder Recipes; Ergebnisse werden als stabile `IssueResult`, `PullRequestResult`, `BuildResult` und `PageResult` ausgegeben.
- Menschenlesbare Ausgabe ist Standard; die direkte CLI unterstützt zusätzlich `--format json`.
- Konfigurations-, Broker-, Verify-, Berechtigungs-, Konflikt- und Netzwerkfehler erhalten stabile Exitcode-Kategorien und vollständig token-redigierte Meldungen.

## Credential-Broker

- `configure-auth` legt außerhalb des Repositories ein benutzerlokales Profil an, das KDBX-Pfad, optionales Keyfile und stabile KeePass-Entry-UUIDs enthält.
- `unlock-secrets` fragt das KeePass-Masterpasswort per `getpass` ab, liest getrennte scoped Tokens für Jira, Confluence und Bitbucket sowie das Jenkins-Token und übergibt sie über eine anonyme Pipe an einen abgekoppelten Broker.
- Secrets erscheinen weder in argv noch im Environment, in Metadaten, Logs oder temporären Dateien.
- IPC verwendet JSON-Bytes ohne Pickle: `AF_UNIX` unter Linux/WSL und `AF_PIPE` unter Windows, jeweils mit HMAC-Authentifizierung.
- Der Broker gibt keine Roh-Tokens zurück. Er führt ausschließlich die implementierten, in `project.toml` erlaubten Operationen aus.
- Die Session endet spätestens acht Stunden nach dem Unlock; `lock-secrets` beendet sie früher. Verwaiste PID-/Socket-Zustände werden automatisch erkannt.
- Windows, WSL und Linux besitzen jeweils einen eigenen Broker und benötigen einen separaten Unlock. Der KeePass-GUI-Status und SSH-Key-Forwarding werden nicht verwendet.
- Jira und Confluence verwenden getrennte scoped Tokens über `api.atlassian.com/ex/{product}/{cloudId}`. Bitbucket nutzt ein eigenes Bitbucket-scoped API-Token. [Atlassian-Tokenmodell](https://support.atlassian.com/atlassian-account/docs/manage-api-tokens-for-your-atlassian-account/), [Bitbucket-Authentifizierung](https://developer.atlassian.com/cloud/bitbucket/rest/).
- In Jenkins/CI werden Credentials ausschließlich pro Prozess aus dem Jenkins Credentials Store injiziert; dort läuft kein Broker.

## Tool-Workflows

- Jira besitzt ausschließlich `create-jira-issue`, `read-jira-isdue`, `update-jira-issue` und `delete-jira-issue`; der Broker erlaubt keine anderen Jira-Endpunkte. `create-jira-issue` nimmt einen benannten Preset (`project`, `issue_type`, `labels`, `components`) plus `summary` und optional `--description`/`--fields`-JSON für Custom Fields entgegen; der Broker baut `fields` selbst aus dem Preset auf, sodass `--fields` die Preset-Werte nicht überschreiben kann. `read-jira-isdue` exponiert die Get-issue-Query-Parameter `fields`/`expand`/`properties` als Flags, `delete-jira-issue` `deleteSubtasks` als Flag. `update-jira-issue` behält ein volles JSON-Request-Objekt (für Array-Add/Remove-Operationen) mit `--summary`/`--description` als Kurzformen.
- `create-pull-request` verwendet den aktuellen Git-Branch, den konfigurierten Zielbranch und Reviewer. Vor dem API-Aufruf läuft zwingend `verify-project`. Ein bestehender offener PR für denselben Branch wird angezeigt und nicht stillschweigend verändert. `--no-verify` benötigt eine zusätzliche Bestätigung beziehungsweise `--yes`.
- `project.just` ist der einzige projektspezifisch anzupassende Recipe-Baustein. Er enthält die kanonischen Test-, Lint- und Buildbefehle des Zielprojekts; das Starterkit markiert den unveränderten Beispiel-Hook in `check-devtools` als Konfigurationsfehler.
- `run-build` akzeptiert nur benannte Jenkins-Presets und explizit erlaubte Parameterkeys. Beliebige Jobs, Deploy-Jobs und administrative Aktionen sind ausgeschlossen. Das Ergebnis enthält Queue-ID und URL; `show-build-status` löst die Queue später zum Build auf. Grundlage ist die [Jenkins Remote Access API](https://www.jenkins.io/doc/book/using/remote-access-api/).
- `preview-release-notes` wandelt Markdown deterministisch in einen sicheren Confluence-Storage-Subset um; Raw HTML ist deaktiviert.
- `publish-release-notes` liest unmittelbar vor dem Schreiben Seite und Version, zeigt die Änderung und schreibt Version+1. Ein Versionskonflikt bricht ohne automatisches Überschreiben ab. [Confluence Page Update](https://developer.atlassian.com/cloud/confluence/rest/v2/api-group-page/).

## Tests und Abnahme

- Unit-Tests für Konfigurationsmodelle, Presets, Markdown-Konvertierung, Ergebnisobjekte, Fehlerübersetzung, Bestätigungslogik und Token-Redaktion.
- Broker-Tests für Unlock/Status/Lock, Acht-Stunden-Ablauf, parallele Unlocks, falsche IPC-Authentifizierung, Prozessabstürze und Secret-Leak-Prüfungen.
- Adapter-Vertragstests mit SDK-Client-Mocks für Gateway-Konfiguration, Authentifizierung, Payloads, Pagination, 401/403/409/429 und unklare Timeout-Ausgänge.
- Just-Tests prüfen sowohl jeden flachen Alias als auch die äquivalente Tool-Namespace-Variante, einschließlich Argumenten mit Leerzeichen und Sonderzeichen.
- Plattformmatrix: Linux, natives Windows und WSL. Alle drei führen `just run-ci` aus; WSL wird über einen Windows-Agenten mit `wsl.exe` gestartet.
- Schreibende Smoke-Tests laufen nur gegen dedizierte Testressourcen und mit explizitem Opt-in.
- Abnahme: Nach dem Kopieren von `scripts/devtools/` und dem Ergänzen einer Import-Zeile funktionieren beide Aufrufformen, neue Herdr-Panes verwenden den laufenden Broker ohne erneutes KeePass-Prompt, und alle vier Tool-Integrationen erfüllen ihren vertikalen Slice.

## Annahmen und Abgrenzung

- Atlassian Cloud mit scoped Tokens; kein Data Center, kein klassisches unscoped Token und kein OAuth 3LO in v1.
- Keine Merge-, Deploy-, Bulk- oder administrativen Aktionen außerhalb des expliziten Jira-Issue-Delete-Targets.
- Abgesehen von der Root-Import-Zeile liegen sämtliche übertragbaren Dateien unter `scripts/devtools/`.
- Benutzerlokale Auth-Profile liegen absichtlich außerhalb des Projekts und werden nicht mitkopiert.
- Keine `.env`-Dateien oder globalen Shellvariablen für lokale Secrets.
