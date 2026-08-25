# QA-Konzept

## Ziel und Qualitätsversprechen

`main` ist jederzeit integrierbar. Jede Änderung erhält innerhalb von fünf Minuten einen ersten automatischen Befund; alle verpflichtenden PR-Gates laufen parallel und sollen innerhalb von zwölf Minuten abgeschlossen sein. Kein Merge darf einen fehlgeschlagenen Gate, eine sinkende Testabdeckung oder einen unreviewten sicherheitsrelevanten Pfad enthalten.

Der Geltungsbereich endet bei Pull Requests und `main`. Release-, Deployment- und Produktivfreigaben sind bewusst nicht Teil dieses Konzepts.

## Entwicklungs- und Branching-Strategie

Es gilt trunk-based development:

- `main` ist der einzige langlebige Branch und die Integrationsquelle.
- Arbeitsbranches heißen `feature/<ticket>-<kurztext>`, `fix/<ticket>-<kurztext>`, `chore/<kurztext>` oder `hotfix/<ticket>-<kurztext>`. Sie starten von aktuellem `main`, enthalten eine fachlich zusammenhängende Änderung und leben möglichst höchstens zwei Arbeitstage.
- Große Vorhaben werden vertikal in rückwärtskompatible, separat merge-bare Schritte geteilt. Unfertige Funktionen werden über Konfiguration oder Feature Flags verborgen, nicht über langlebige Integrationsbranches.
- Pull Requests zielen ausschließlich auf `main`, werden vor dem Merge gegen den aktuellen Stand von `main` geprüft und per Squash-Auto-merge integriert. Dadurch bleibt die Historie pro Änderung lesbar und `main` linear.

In GitHub wird für `main` eine strikte Branch-Regel eingerichtet: keine Direkt-Pushes, Force-Pushes oder Löschungen; ein Approval; Zurücksetzen veralteter Reviews; Auflösung aller Gespräche; erforderliche CODEOWNERS-Reviews für die in `.github/CODEOWNERS` markierten Sicherheits- und Integrationspfade. Als verpflichtende Checks werden exakt `Quality gates`, `Tests (Python 3.12)` und `Tests (Python 3.13)` ausgewählt.

Solange `mmikitz` der einzige Collaborator des Repositories ist, kann diese Person das eigene Approval nicht erteilen (GitHub verbietet Self-Approval) – ohne Ausnahme wäre `main` dauerhaft nicht mehr mergebar. Der Repository-Owner steht daher explizit auf der GitHub-Bypass-Liste der Regel und kann eigene PRs ohne fremdes Approval mergen; alle anderen Bestandteile der Regel (Status-Checks, kein Force-Push/Delete, Conversation-Resolution, CODEOWNERS-Pflicht für jeden anderen Beitragenden) gelten uneingeschränkt, auch für den Owner. Sobald ein zweiter Collaborator mit Review-Rechten hinzukommt, sollte dieser Bypass-Eintrag entfernt werden.

## Test- und Gate-Modell

Jeder Pull Request führt vollständig aus:

- Formatprüfung und Linting mit Ruff sowie statische Typprüfung mit mypy.
- Reproduzierbarkeitsprüfung des `uv.lock`, Paketbau und Vulnerability-Audit der gelockten Abhängigkeiten.
- Die vollständige pytest-Suite auf Ubuntu mit Python 3.12 und 3.13. Adaptertests bleiben deterministische Vertrags-/Mocktests; Broker-Lifecycle-Tests laufen nativ in der Matrix.
- Branch-Coverage ist aktiv. Der Startwert liegt bei mindestens **67,51 %** und darf nicht sinken. Nach einer nachweisbaren Verbesserung auf `main` wird der Floor gezielt angehoben, niemals abgesenkt.

Die lokale Entsprechung lautet `just qa`. Sie prüft Lockfile, Format, Lint, Typen, Tests und Coverage; die CI ergänzt Paketbau und Dependency-Audit.

Zusätzlich installiert `just install-hooks` einen lokalen, über [Lefthook](https://lefthook.dev) verwalteten `pre-commit`-Hook, der bei jedem Commit automatisch `just check-changed` aufruft. Dieser prüft ausschließlich die zum Commit gestagten Dateien (Ruff, mypy und die zugeordneten Tests) und dient als schnelles, freiwilliges Frühwarnsystem. Er ersetzt weder `just qa` noch die CI-Gates, läuft nicht in der Pipeline und lässt sich mit `git commit --no-verify` umgehen; verbindlich bleibt ausschließlich der PR-Gate in der CI.

Live-Tests gegen Jira, Bitbucket, Jenkins oder Confluence laufen nicht in gewöhnlichen PRs: Forks und Pull Requests erhalten keine Integrationssecrets. Bei Adapter- oder API-Änderungen führt ein Maintainer einen manuellen Smoke-Test gegen dedizierte Testressourcen in einem geschützten GitHub-Environment aus. Dieser wird erst aktiviert, wenn dafür getrennte Testressourcen, vier minimal berechtigte Tokens und erwartete Testdaten hinterlegt sind.

Ein fehlgeschlagener Gate blockiert den Merge. Flaky Tests werden nicht durch automatische Retries kaschiert: Sie erhalten ein Ticket, einen verantwortlichen Owner und ein Ablaufdatum; bis zur Reparatur ist nur ein klar begründetes, zeitlich begrenztes `xfail` zulässig.

## CI und Supply Chain

`.github/workflows/ci.yml` startet auf jedem Pull Request, jedem Push nach `main` und manuell. Es verwendet minimale Leserechte, gepinnte Actions, keinen Pfadfilter und bricht veraltete Läufe desselben PRs ab. Dadurch bleibt der erste statische Befund schnell, während die beiden Testversionen parallel laufen.

Dependabot erstellt wöchentlich getrennte PRs für `uv`-Abhängigkeiten und GitHub Actions. Diese PRs durchlaufen dieselben Pflichtgates und benötigen vor dem Merge ebenfalls das erforderliche Review.

Nach dem ersten erfolgreichen CI-Lauf konfiguriert ein Repository-Administrator die oben genannten Branch-Regeln in GitHub. Die Regeln sind eine Repository-Einstellung und können nicht allein durch die Workflow-Datei erzwungen werden.

## Betrieb und Messung

- Entwickler beheben einen roten PR-Gate vor dem Review oder markieren ihn als Draft. Reviewer bewerten fachliche Änderung, Regressionstest und Risiko statt CI-Ausgaben zu wiederholen.
- Bei einer Regression wird zuerst ein reproduzierender Test ergänzt, dann der Fehler behoben. Die betroffene Testebene und eine mögliche Guardrail-Lücke werden im Ticket dokumentiert.
- Monatlich werden Durchlaufzeit, Fehlerrate der Gates, flakige Tests, Coverage-Floor und offene Dependabot-PRs überprüft. Überschreitet ein regulärer PR-Lauf zwölf Minuten, werden Jobs parallelisiert, gecacht oder in schnellere und langsamere Checks zerlegt – ohne Pflichtgates zu entfernen.
