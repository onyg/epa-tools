# epatools

`epatools` ist ein Python-Kommandozeilenwerkzeug zur Verarbeitung von FHIR-CapabilityStatements im ePA-Umfeld. Es führt importierte CapabilityStatements zusammen und erzeugt daraus OpenAPI-Dokumente in Version 3.0.3 als JSON oder YAML.

## Installation

Vorausgesetzt werden Python 3 und `pip`. Die CLI wurde für diese Anleitung mit Python 3.12 geprüft; eine Mindestversion ist im Projekt derzeit nicht festgelegt.

Im Hauptverzeichnis des ausgecheckten Projekts:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Unter Windows (PowerShell) wird die Umgebung mit `.venv\Scripts\Activate.ps1` aktiviert. Die Python-Abhängigkeiten `PyYAML` und `requests` werden bei der Installation automatisch installiert.

Anschließend stehen folgende Befehle zur Verfügung:

```bash
epatools --help
epatools --version
epatools merge --help
epatools openapi --help
```

## Schnellstart mit den Beispieldaten

Alle folgenden Befehle werden im Projektverzeichnis ausgeführt. Relative Pfade werden relativ zum aktuellen Arbeitsverzeichnis aufgelöst, auch wenn mit `--config` eine Konfiguration aus einem anderen Verzeichnis geladen wird.

```bash
# CapabilityStatements zusammenführen; Quelldateien beibehalten
epatools merge --extra

# OpenAPI-Dokumente erzeugen
epatools openapi
```

Standardmäßig liest das Werkzeug die Datei [epatools.yaml](epatools.yaml). Die mitgelieferte Konfiguration verarbeitet die Dienste Patient, Medication, Audit Event und MHD Document Responder aus `data/` und schreibt jeweils eine JSON- und YAML-Datei nach `output/`.

`--extra` erzeugt beim Zusammenführen Dateien wie `data/CapabilityStatement-epa-patient-server-merged.json`. Genau diese Dateien sind in der mitgelieferten OpenAPI-Konfiguration als Eingaben eingetragen. Ohne `--extra` überschreibt `merge` die jeweiligen Quelldateien. Bereits vorhandene Ausgabedateien werden bei erneuter Ausführung überschrieben.

## CapabilityStatements zusammenführen

```bash
epatools merge --config epatools.yaml --dependencies sushi-config.yaml --extra
```

| Option | Bedeutung | Standard |
| --- | --- | --- |
| `--config` | Pfad zur Werkzeugkonfiguration | `epatools.yaml` |
| `--dependencies` | YAML-Datei mit FHIR-Paketabhängigkeiten | `sushi-config.yaml` |
| `--extra` | Ergebnis zusätzlich mit dem Dateisuffix `-merged.json` speichern | Aus; Quelldatei wird überschrieben |

Der Abschnitt `merger` legt die Eingaben fest:

```yaml
merger:
  path-resource: data
  resource:
    - CapabilityStatement/epa-patient-server
```

Ohne `path-resource` wird `fsh-generated/resources` verwendet. Ressourcen werden als `Ressourcentyp/ID` angegeben. Beispielsweise wird `CapabilityStatement/epa-patient-server` als `CapabilityStatement-epa-patient-server.json` im Ressourcenverzeichnis gefunden.

Für jeden Eintrag in `imports` sucht das Werkzeug das referenzierte CapabilityStatement anhand seiner kanonischen URL zunächst im Ressourcenverzeichnis und anschließend in den konfigurierten FHIR-Paketen. Das lokale CapabilityStatement überlagert die importierten Inhalte: einfache Werte werden überschrieben, verschachtelte Objekte rekursiv zusammengeführt und Listen um nicht identische Einträge ergänzt. `rest`-Einträge werden anhand ihres `mode` zusammengeführt.

Eine Ergebnisdatei wird nur geschrieben, wenn mindestens ein Import gefunden und zusammengeführt wurde. Das Werkzeug löst Importketten nicht automatisch rekursiv auf.

### FHIR-Paketabhängigkeiten

Wenn importierte CapabilityStatements nicht lokal vorliegen, können Paketnamen und Versionen in einer Abhängigkeitsdatei angegeben werden. Das folgende Beispiel enthält Platzhalter:

```yaml
dependencies:
  mein.fhir.paket: "1.0.0"
```

Für diese Importauflösung müssen die Pakete bereits unter `~/.fhir/packages/<paketname>#<version>/package/` vorhanden sein. `epatools` lädt sie nicht selbst herunter. Die mitgelieferte `sushi-config.yaml` ist derzeit leer; lokal verfügbare Imports benötigen keine Paketabhängigkeiten.

## OpenAPI erzeugen

```bash
epatools openapi --config epatools.yaml
```

Eine kompakte Konfiguration für die mitgelieferten Patient-Daten:

```yaml
openapi:
  path-resource: data
  path-output: output
  with-metadata: true
  with-format-parameter: true
  with-accept-header: true
  with-pagination: true
  capability-statement:
    - input: CapabilityStatement/epa-patient-server-merged
      output: epa-patient-server.openapi.yaml
      additional-openapi: openapis/manual-operations.yaml
      post-search: true
```

| Einstellung unter `openapi` | Bedeutung | Standard |
| --- | --- | --- |
| `path-resource` | Verzeichnis der FHIR-Eingabedateien | `fsh-generated/resources` |
| `path-output` | Verzeichnis für erzeugte OpenAPI-Dateien | `openapi` |
| `with-metadata` | Endpunkt zum Abrufen des CapabilityStatements ergänzen | `false` |
| `with-format-parameter` | Query-Parameter `_format` ergänzen | `false` |
| `with-accept-header` | HTTP-Header `Accept` ergänzen | `false` |
| `with-pagination` | Paginierungsparameter `_count`, `_offset` und `_total` an den vorgesehenen Interaktionen ergänzen | `true` |
| `capability-statement` | Liste der Konvertierungsaufträge | Leere Liste |

Jeder Konvertierungsauftrag unterstützt:

| Einstellung | Bedeutung |
| --- | --- |
| `input` | Eingaberessource als `CapabilityStatement/ID` |
| `output` | Ausgabedateiname; unterstützte Endungen: `.json`, `.yaml`, `.yml` |
| `additional-openapi` | Optionaler Pfad zu einer Datei mit zusätzlichen OpenAPI-Pfaden |
| `post-search` | Zusätzlich POST-Suche für Ressourcen mit `search-type` erzeugen; Standard: `false` |

Für mehrere Ausgabeformate wird dieselbe Eingabe mehrfach mit unterschiedlichen Ausgabedateinamen aufgeführt. Das Ausgabeverzeichnis wird automatisch angelegt.

Der Konverter berücksichtigt Ressourceninteraktionen, Suchparameter und lokal verfügbare `OperationDefinition`-Ressourcen. Bereits als Suchparameter deklarierte Paginierungsparameter werden nicht nochmals durch die automatische Paginierung ergänzt.

### Manuelle OpenAPI-Ergänzungen

Mit `additional-openapi` lassen sich beispielsweise eigene Endpunkte ergänzen:

```yaml
paths:
  /health:
    get:
      summary: Erreichbarkeit prüfen
      responses:
        "200":
          description: Dienst erreichbar
```

Übernommen wird ausschließlich der Abschnitt `paths`. Bei einer bereits vorhandenen Kombination aus Pfad und HTTP-Methode ersetzt die manuelle Definition die generierte Operation. Andere Abschnitte wie `components`, `info` oder `servers` werden aus dieser Datei nicht übernommen.

## Hinweise zur Fehlersuche

- **Konfiguration fehlt:** Das Werkzeug meldet `Config file missing. Skipping execution.` und beendet sich mit Exit-Code `0`. Bei automatisierten Abläufen deshalb auch die erwarteten Ausgabedateien prüfen.
- **Keine neue Merge-Datei:** Ressourcenpfad, Ressourcen-ID und `imports` prüfen. Ohne erfolgreich aufgelösten Import wird keine Datei geschrieben.
- **FHIR-Paket nicht gefunden:** Paketname, Version und den lokalen Cache unter `~/.fhir/packages/` prüfen.
- **OpenAPI-Eingabe fehlt:** Zuerst `epatools merge --extra` ausführen und prüfen, ob die in `input` angegebene Datei existiert.
- **Eigene Operation fehlt:** Prüfen, ob die passende `OperationDefinition` lokal vorliegt und ihre URL beziehungsweise ID zur Referenz im CapabilityStatement passt.

## Entwicklung und Build

Der Quellcode liegt unter `src/epatools/`. Mit der oben beschriebenen editierbaren Installation werden Änderungen direkt beim nächsten Aufruf verwendet. Alternativ lässt sich die CLI aus dem Quellverzeichnis starten:

```bash
PYTHONPATH=src python -m epatools.main --help
```

Das Build-Skript installiert `build` und `shiv` und erzeugt die Python-Distributionen sowie ein ausführbares Python-Ziparchiv in `dist/`:

```bash
bash build.sh
python dist/epatools.pyz --help
```

## Lizenz

Das Projekt steht unter der [MIT-Lizenz](LICENSE).
